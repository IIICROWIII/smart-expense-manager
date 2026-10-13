import csv
import io
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.database import Database
from backend.main import create_app
from backend.services import ExpenseService
from backend.validation import ValidationError


@pytest.fixture
def service(tmp_path):
    db = Database(tmp_path / "expenses.db")
    db.initialize()
    return ExpenseService(db)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as client:
        yield client


def add(service, amount="10.00", **kwargs):
    return service.add_transaction(**{"amount": amount, "kind": "expense", "category_id": 1, "date": "2026-10-13", **kwargs})


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "0.001", "1000000001", "abc", True, None])
def test_invalid_money_cannot_be_saved(service, amount):
    with pytest.raises(ValidationError):
        add(service, amount)
    assert service.list_transactions()["total"] == 0


@pytest.mark.parametrize("value", ["2026-02-30", "2026-2-01", "not-a-date", "0000-01-01"])
def test_invalid_date(service, value):
    with pytest.raises(ValidationError):
        add(service, date=value)


def test_exact_money_and_income_separation(service):
    add(service, "0.10")
    add(service, "0.20")
    add(service, "100", kind="income", category_id=11)
    result = service.summary("2026-10", today=date(2026, 10, 13))
    assert result["expense_cents"] == 30
    assert result["income_cents"] == 10000
    assert result["balance_cents"] == 9970


def test_budget_alerts_once_per_threshold_and_category(service):
    service.set_budget("2026-10", "100")
    service.set_budget("2026-10", "100", 2)
    add(service, "80")
    add(service, "20")
    add(service, "1")
    alerts = service.alerts()
    assert sorted(a["threshold"] for a in alerts) == [80, 100]
    assert service.budgets("2026-10")[0]["remaining_cents"] == -100
    assert service.budgets("2026-10")[1]["spent_cents"] == 0
    service.set_budget("2026-10", "100")
    assert len(service.alerts()) == 2
    assert service.read_alert(alerts[0]["id"])["is_read"] == 1


def test_unusual_same_day_previous_data_and_minimum_sample(service):
    add(service)
    add(service)
    result = add(service, "100")
    assert not result["alerts"]  # Only two baseline samples.
    service.delete_transaction(result["transaction"]["id"])
    add(service)
    result = add(service, "30")
    assert "3.0x" in result["alerts"][0]["message"]
    assert "10.00" in result["alerts"][0]["message"]
    assert service.list_transactions(unusual=True)["total"] == 1
    service.update_transaction(result["transaction"]["id"], amount="10")
    assert service.list_transactions(unusual=True)["total"] == 0


def test_future_dated_baseline_excluded(service):
    for _ in range(3):
        add(service, date="2026-12-01")
    assert not add(service, "100", date="2026-10-01")["alerts"]


def test_invalid_updates_rollback_and_category_kind(service):
    identifier = add(service)["transaction"]["id"]
    with pytest.raises(ValidationError):
        service.update_transaction(identifier, kind="income")
    assert service.get_transaction(identifier)["kind"] == "expense"
    with pytest.raises(ValidationError):
        service.set_budget("2026-13", "100")
    with pytest.raises(ValidationError):
        service.set_budget("2026-10", "100", 11)


def test_sql_injection_search_is_literal(service):
    note = "'); DROP TABLE transactions; --"
    add(service, description=note)
    assert service.list_transactions(search=note)["total"] == 1
    assert service.list_transactions(search="%_")["total"] == 0
    assert service.list_transactions()["total"] == 1


def test_csv_unicode_formula_and_month_filter(service):
    add(service, description="=HYPERLINK(\"bad\")")
    add(service, description="İstanbul alışverişi")
    add(service, date="2026-09-13")
    content = service.export_csv("2026-10")
    assert content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 2
    assert rows[0]["description"].startswith("'=")
    assert rows[1]["description"] == "İstanbul alışverişi"


def test_forecast_excludes_future_transactions(service):
    add(service, "130", date="2026-10-13")
    add(service, "900", date="2026-10-30")
    result = service.summary("2026-10", today=date(2026, 10, 13))
    assert result["forecast_cents"] == 31000
    assert result["expense_cents"] == 103000
    assert service.summary("2026-11", today=date(2026, 10, 13))["forecast_cents"] is None
    assert service.summary("2024-02", today=date(2026, 10, 13))["days_in_month"] == 29


def test_concurrent_writes(service):
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: add(service, "0.10"), range(20)))
    assert service.list_transactions()["total"] == 20
    assert service.summary("2026-10")["expense_cents"] == 200


def test_database_enforces_money_constraint(service):
    with pytest.raises(sqlite3.IntegrityError), service.db.connect() as conn:
        conn.execute("INSERT INTO transactions(amount_cents,kind,category_id,date,payment_method) VALUES (-1,'expense',1,'2026-10-13','Card')")


def test_api_crud_and_validation(client):
    data = {"amount": "125.50", "kind": "expense", "category_id": 1, "date": "2026-10-13"}
    response = client.post("/transactions", json=data)
    assert response.status_code == 201
    identifier = response.json()["transaction"]["id"]
    assert client.get(f"/transactions/{identifier}").json()["amount_cents"] == 12550
    assert client.patch(f"/transactions/{identifier}", json={"amount": "50"}).status_code == 200
    for bad in ({"amount": "NaN"}, {"date": "2026-02-30"}, {"category_id": 11}, {"unknown": "bad"}, {"amount": 4}, {"amount": None}):
        assert client.post("/transactions", json={**data, **bad}).status_code == 422
    assert client.patch(f"/transactions/{identifier}", json={}).status_code == 422
    assert client.patch(f"/transactions/{identifier}", json={"amount": None}).status_code == 422
    assert client.get("/transactions?limit=101").status_code == 422
    assert client.get("/transactions?month=2026-99").status_code == 422
    assert client.delete(f"/transactions/{identifier}").status_code == 204
    assert client.get(f"/transactions/{identifier}").status_code == 404


def test_api_budgets_reports_alerts_and_cors(client):
    assert client.put("/budgets", json={"month": "2026-10", "amount": "100"}).status_code == 200
    client.post("/transactions", json={"amount": "100", "kind": "expense", "category_id": 1, "date": "2026-10-13"})
    assert len(client.get("/alerts").json()) == 2
    assert client.patch("/alerts/1").json()["is_read"] == 1
    assert client.get("/reports/summary?month=2026-10").json()["expense_cents"] == 10000
    response = client.get("/reports/export?month=2026-10")
    assert response.status_code == 200 and response.content.startswith(b"\xef\xbb\xbf")
    assert client.get("/reports/export?month=bad").status_code == 422
    response = client.options("/transactions", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert client.delete("/budgets/1").status_code == 204
    assert client.get("/alerts").json() == []


def test_cli_persistence_and_error_exit(tmp_path):
    common = [sys.executable, "cli.py", "--db", str(tmp_path / "cli.db")]
    result = subprocess.run(common + ["add", "--amount", "12.50", "--category-id", "1", "--date", "2026-10-13"], capture_output=True, text=True)
    assert result.returncode == 0 and '"amount_cents": 1250' in result.stdout
    result = subprocess.run(common + ["summary", "--month", "2026-10"], capture_output=True, text=True)
    assert result.returncode == 0 and '"expense_cents": 1250' in result.stdout
    result = subprocess.run(common + ["add", "--amount", "NaN", "--category-id", "1", "--date", "2026-10-13"], capture_output=True, text=True)
    assert result.returncode == 2


def test_copy_budgets_preserves_existing_and_handles_january(service):
    service.set_budget("2025-12", "1000")
    service.set_budget("2025-12", "200", 1)
    service.set_budget("2026-01", "500")
    assert service.copy_budgets("2026-01")["copied"] == 1
    limits = service.budgets("2026-01")
    assert limits[0]["limit_cents"] == 50000
    assert service.copy_budgets("2026-01")["copied"] == 0
    with pytest.raises(ValidationError):
        service.copy_budgets("0001-01")


def test_suggestion_is_explained_and_word_bounded(service):
    assert service.suggest_category("Uber to Taksim")["category"] == "Transport"
    assert "uber" in service.suggest_category("UBER to Taksim")["reason"]
    assert service.suggest_category("Discovery")["category"] == "Other"
    assert service.suggest_category("Monthly salary", "income")["category"] == "Salary"


def test_history_crosses_year_boundary(service):
    add(service, "15", date="2025-12-10")
    result = service.history("2026-02")
    assert len(result) == 6
    assert result[0]["month"] == "2025-09"
    assert next(r for r in result if r["month"] == "2025-12")["expense_cents"] == 1500
    assert len(service.history("0001-01")) == 1


def test_frontend_and_new_endpoints(client):
    assert client.get("/").status_code == 200
    assert "olive ledger" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.post("/categories/suggest", json={"description": "Lunch"}).json()["category"] == "Food & Dining"
    assert client.post("/budgets/copy-previous", json={"month": "2026-10"}).json()["copied"] == 0
    assert len(client.get("/reports/history?month=2026-10").json()) == 6
