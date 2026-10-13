"""SQLite schema and short-lived, transactional connections."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

EXPENSE_CATEGORIES = ("Food & Dining", "Groceries", "Transport", "Rent & Bills", "Shopping", "Entertainment", "Education", "Health", "Subscriptions", "Other")
INCOME_CATEGORIES = ("Allowance", "Salary", "Freelance", "Other Income")


class Database:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL CHECK(kind IN ('expense', 'income')),
                    UNIQUE(id, kind)
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0 AND amount_cents <= 100000000000),
                    kind TEXT NOT NULL CHECK(kind IN ('expense', 'income')),
                    category_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    payment_method TEXT NOT NULL CHECK(payment_method IN ('Card','Cash','Istanbulkart','Bank Transfer','Other')),
                    FOREIGN KEY(category_id, kind) REFERENCES categories(id, kind)
                );
                CREATE INDEX IF NOT EXISTS transactions_date ON transactions(date);
                CREATE INDEX IF NOT EXISTS transactions_category ON transactions(category_id, date);
                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month TEXT NOT NULL,
                    category_id INTEGER REFERENCES categories(id),
                    limit_cents INTEGER NOT NULL CHECK(limit_cents > 0 AND limit_cents <= 100000000000)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS budgets_scope ON budgets(month, IFNULL(category_id, 0));
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('budget','unusual')),
                    budget_id INTEGER REFERENCES budgets(id) ON DELETE CASCADE,
                    transaction_id INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
                    threshold INTEGER,
                    message TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0,1)),
                    UNIQUE(budget_id, threshold),
                    UNIQUE(transaction_id, kind)
                );
            """)
            conn.executemany("INSERT OR IGNORE INTO categories(name,kind) VALUES (?,?)", [(name, "expense") for name in EXPENSE_CATEGORIES] + [(name, "income") for name in INCOME_CATEGORIES])
