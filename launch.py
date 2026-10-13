"""Run the complete local application, optionally using isolated demo data."""
import argparse
from pathlib import Path

import uvicorn

from backend.main import create_app
from backend.database import Database
from backend.services import ExpenseService


def demo_database():
    path = Path(__file__).resolve().parent / "data" / "demo.db"
    db = Database(path)
    db.initialize()
    service = ExpenseService(db)
    if service.list_transactions()["total"]:
        return path
    records = [
        ("2026-05-03", "income", 11, "30000", "Monthly allowance", "Bank Transfer"),
        ("2026-05-08", "expense", 4, "12500", "Rent and utilities", "Bank Transfer"),
        ("2026-06-03", "income", 11, "30000", "Monthly allowance", "Bank Transfer"),
        ("2026-06-08", "expense", 4, "16000", "Rent and utilities", "Bank Transfer"),
        ("2026-07-03", "income", 11, "30000", "Monthly allowance", "Bank Transfer"),
        ("2026-07-08", "expense", 4, "14500", "Rent and utilities", "Bank Transfer"),
        ("2026-08-03", "income", 11, "30000", "Monthly allowance", "Bank Transfer"),
        ("2026-08-08", "expense", 4, "17000", "Rent and utilities", "Bank Transfer"),
        ("2026-09-03", "income", 11, "30000", "Monthly allowance", "Bank Transfer"),
        ("2026-09-08", "expense", 4, "15200", "Rent and utilities", "Bank Transfer"),
        ("2026-10-01", "income", 11, "30000", "Monthly allowance", "Bank Transfer"),
        ("2026-10-02", "expense", 4, "11500", "October rent", "Bank Transfer"),
        ("2026-10-03", "expense", 1, "180", "Lunch after class", "Card"),
        ("2026-10-04", "expense", 1, "160", "Coffee and breakfast", "Card"),
        ("2026-10-05", "expense", 1, "200", "Dinner with friends", "Cash"),
        ("2026-10-06", "expense", 2, "850", "Migros groceries", "Card"),
        ("2026-10-07", "expense", 3, "500", "Istanbulkart top-up", "Istanbulkart"),
        ("2026-10-08", "expense", 2, "680", "Weekly groceries", "Card"),
        ("2026-10-09", "expense", 9, "150", "Music subscription", "Card"),
        ("2026-10-10", "expense", 5, "1250", "Winter shoes", "Card"),
        ("2026-10-11", "expense", 7, "460", "Python course books", "Card"),
        ("2026-10-12", "expense", 1, "950", "Celebration dinner", "Card"),
        ("2026-10-13", "expense", 2, "920", "Groceries for the week", "Card"),
        ("2026-10-13", "expense", 3, "420", "Uber to Taksim", "Card"),
    ]
    for day, kind, category, amount, description, method in records:
        service.add_transaction(date=day, kind=kind, category_id=category, amount=amount, description=description, payment_method=method)
    service.set_budget("2026-10", "20000")
    service.set_budget("2026-10", "3000", 2)
    service.set_budget("2026-10", "1500", 1)
    service.set_budget("2026-10", "1500", 3)
    service.set_budget("2026-09", "20000")
    service.set_budget("2026-09", "3000", 2)
    return path


def main():
    parser = argparse.ArgumentParser(description="Run Olive Ledger locally")
    parser.add_argument("--demo", action="store_true", help="Use isolated fictional data for October 2026")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app = create_app(demo_database() if args.demo else None)
    app.state.demo = args.demo
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
