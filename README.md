# Smart Expense Manager

Python backend for a student's monthly spending and allowance in Istanbul. It records expenses and income, manages monthly and category budgets, generates reports, and explains unusually large expenses. The REST API and argument-based CLI share the same business rules and SQLite database.

This version is a local, single-user application using TRY. It has no login or tenant isolation. Run the API on localhost. A public multi-user service would require authentication, per-user records and authorization before deployment.

## Setup and run

Python 3.12 is recommended. From the project directory on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

The project already has a local `.venv` with the required packages installed. Open `http://127.0.0.1:8000/docs` for interactive API documentation. `http://127.0.0.1:8000/openapi.json` provides the frontend contract. Database tables and categories are created on startup, not on import.

The default database is `data/expenses.db`, resolved relative to the project rather than the current shell directory. Override it with `EXPENSE_DB_PATH`; the CLI also supports `--db PATH`. This schema does not import or migrate the earlier Streamlit sample database.

## Architecture and ownership

```text
Frontend -> REST routes -> ExpenseService -> repository / Database -> SQLite
CLI --------------------> ExpenseService
```

| Path | Purpose |
| --- | --- |
| `backend/main.py` | Application factory, startup, CORS and HTTP error handling |
| `backend/routes.py` | REST endpoints, request parsing and response transport |
| `backend/schemas.py` | Strict API request contracts; unknown fields rejected |
| `backend/validation.py` | Shared money, date and text validation; domain errors |
| `backend/services.py` | Transaction workflows, budgets, alerts, reports and CSV |
| `backend/repository.py` | Transaction lookup, filtering, search and pagination SQL |
| `backend/database.py` | Connection lifecycle, transactions, schema, indexes and seeded categories |
| `backend/__init__.py` | Python package marker |
| `cli.py` | Argument-based commands using the service directly |
| `tests/test_backend.py` | Business rules, API, persistence, concurrency and invalid input tests |
| `requirements.txt` | Tested API/server dependency versions |
| `requirements-dev.txt` | Runtime requirements plus testing dependencies |
| `contributions/` | Real, individually authored team contribution records |
| `.gitignore` | Excludes environments, local financial data, secrets and caches |

The backend owner maintains routes and business rules. The database teammate can extend `database.py` and `repository.py` with agreed service changes. The frontend teammate consumes the HTTP contract without writing SQL. The UI/UX teammate defines screen behavior. The presentation teammate prepares the demonstration with technical input from the team.

## Frontend contract

Amounts in write requests are decimal **strings**, for example `"125.50"`. This avoids binary floating-point ambiguity. Responses use integer `amount_cents`, `limit_cents`, `spent_cents`, etc. Display these values divided by 100 with two decimal places. The currency is always TRY, including exported files. Do not mix currencies in one database.

Transaction types are `expense` and `income`. Fetch IDs from `/categories` rather than assuming them. Categories must match the transaction type. Payment methods are `Card`, `Cash`, `Istanbulkart`, `Bank Transfer`, and `Other`.

```json
{
  "amount": "125.50",
  "kind": "expense",
  "category_id": 1,
  "date": "2026-10-13",
  "description": "Lunch",
  "payment_method": "Card"
}
```

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/health` | Health status and currency |
| GET | `/categories` | Category IDs, names and transaction type |
| POST | `/transactions` | Create transaction; returns `{transaction, alerts}`; status 201 |
| GET | `/transactions` | Filters: `month`, `kind`, `category_id`, `search`, `unusual`; pagination: `limit`, `offset` |
| GET | `/transactions/{id}` | One transaction |
| PATCH | `/transactions/{id}` | Partial edit with the same field names; returns `{transaction, alerts}` |
| DELETE | `/transactions/{id}` | Delete transaction and its associated anomaly alert; status 204 |
| PUT | `/budgets` | Upsert `{month, amount, category_id?}`; omitted/null category means overall monthly budget |
| GET | `/budgets?month=YYYY-MM` | Limits, spending, remaining money, percentage and status |
| DELETE | `/budgets/{id}` | Remove limit and related budget alert history; status 204 |
| GET | `/reports/summary?month=YYYY-MM` | Income, expenses, balance, daily/category/payment totals, five largest expenses, forecast and budgets |
| GET | `/reports/export?month=YYYY-MM` | Download every transaction in selected month as CSV |
| GET | `/alerts?month=YYYY-MM` | Saved alerts, newest first; month is optional |
| PATCH | `/alerts/{id}` | Mark an alert as read; no body required |

Transaction lists return `{items, total, limit, offset}`, ordered by date then ID descending. Default page size is 15 and maximum is 100. Search is literal text, not an SQL wildcard expression. An empty result is an empty array, not an error.

`404` means a requested record does not exist. `422` means input failed validation, with details in `detail`. `503` indicates a storage failure. The frontend should handle both text domain errors and FastAPI's structured request-validation errors. Explicit null fields are rejected for transaction edits; an omitted field is unchanged.

After writes, reload relevant transactions, summary, budgets and alerts. The alerts returned alongside a saved transaction include saved budget alerts for its month, so deduplicate by alert ID before displaying toasts.

Allowed local browser origins include `http://localhost:3000`, `http://localhost:5173`, `http://localhost:8501`, and `http://127.0.0.1:5173`. Configure the comma-separated `EXPENSE_CORS_ORIGINS` environment variable for a different frontend origin.

## Business rules

- Money must be positive, finite, at most TRY 1,000,000,000, and have no more than two decimal places. SQLite stores integer cents.
- Dates use valid `YYYY-MM-DD`; months use valid `YYYY-MM`. Future-dated records are allowed, but excluded from current spending forecasts.
- Descriptions have up to 500 characters and no control characters. SQL uses bound parameters. Multi-step saves and alert creation commit together or roll back together.
- Overall and category budgets are independent limits. Each scope has only one budget per month. Income never consumes a budget.
- Budget alerts fire at 80% and 100%, once per threshold per budget. Alerts record an event snapshot; editing/deleting transactions or increasing a budget does not erase historical budget alerts. Current budget status is calculated from current transactions. Deleting and recreating a budget resets its alert history.
- An unusual expense is strictly greater than twice the mean of at least three previously entered expenses in the same category, dated on or before the target transaction. Same-day previous records are included, future records and the target itself are excluded. This is an explainable heuristic, not machine learning. Editing a transaction recalculates its own anomaly alert; other saved anomaly alerts remain historical snapshots.
- At 100% budget status is `over`, at 80% it is `warning`, otherwise `on_track`.
- Reports aggregate every transaction in the selected month. Average/day and forecast use expenses through today and elapsed calendar days. Past months use all days, future months have no forecast. Today follows Istanbul time (UTC+3). Forecasts are estimates, not financial advice.
- CSV includes a UTF-8 BOM for Turkish text in Excel, standard quoting, and apostrophe-prefixed text starting with spreadsheet formula characters.

## CLI examples

Run from the project directory. Use `--help` for the full command list and per-command arguments. The CLI needs only Python's standard library, without FastAPI installed.

```powershell
.\.venv\Scripts\python.exe cli.py categories
.\.venv\Scripts\python.exe cli.py budget --month 2026-10 --amount 3000
.\.venv\Scripts\python.exe cli.py add --amount 125.50 --category-id 1 --date 2026-10-13 --description "Lunch"
.\.venv\Scripts\python.exe cli.py list --month 2026-10 --limit 15
.\.venv\Scripts\python.exe cli.py update 1 --amount 120
.\.venv\Scripts\python.exe cli.py summary --month 2026-10
.\.venv\Scripts\python.exe cli.py alerts
.\.venv\Scripts\python.exe cli.py read-alert 1
.\.venv\Scripts\python.exe cli.py delete 1
```

CLI output is JSON except CSV export. Exit codes: 0 success, 2 invalid input/not found, 3 storage failure. To write a CSV byte-for-byte across PowerShell versions:

```powershell
.\.venv\Scripts\python.exe -c "import subprocess,sys; from pathlib import Path; r=subprocess.run([sys.executable,'cli.py','export','--month','2026-10'],capture_output=True,check=True); Path('expenses-october.csv').write_bytes(r.stdout)"
```

Keep generated exports outside the submitted implementation repository.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use disposable databases and never modify the real database. They cover integer monetary accuracy, invalid amounts/dates, category mismatches, rollback, budget thresholds, anomaly baselines, concurrent saves, CSV formula handling, API validation and CLI persistence.

## Team submission

Each member must author `contributions/<STUDENT_NAME>_<STUDENT_ID>_<GITHUB_USERNAME>.md` describing actual work and linking relevant commits. Do not invent contributions or commit ownership. Publish a clean public GitHub repository and submit its URL with the PPTX. Names, IDs, contribution records and the presentation are still required from the team.

## Deferred features

This backend does not implement the frontend, conversational assistant, automatic categorization, duplicate detection, copying last month's budgets, or a dedicated six-month comparison endpoint. The frontend can request individual monthly summaries for a six-month view. These additions can follow the tested core.

Implementation follows the official [FastAPI lifespan guide](https://fastapi.tiangolo.com/advanced/events/) and [testing guide](https://fastapi.tiangolo.com/tutorial/testing/).
