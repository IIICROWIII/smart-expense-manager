"""Shared business rules, independent of FastAPI and frontend libraries."""
import calendar
import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from . import repository
from .validation import NotFoundError, ValidationError, day, money, month, text

PAYMENT_METHODS = ("Card", "Cash", "Istanbulkart", "Bank Transfer", "Other")


class ExpenseService:
    def __init__(self, database):
        self.db = database

    def categories(self):
        with self.db.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM categories ORDER BY id")]

    def _category(self, conn, identifier, kind):
        if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
            raise ValidationError("Category ID must be a positive integer.")
        row = conn.execute("SELECT * FROM categories WHERE id=?", (identifier,)).fetchone()
        if not row or row["kind"] != kind:
            raise ValidationError("Category must exist and match the transaction type.")

    def _payload(self, conn, data):
        allowed = {"amount", "kind", "category_id", "date", "description", "payment_method"}
        if set(data) - allowed or not {"amount", "kind", "category_id", "date"} <= set(data):
            raise ValidationError("Supply amount, kind, category_id and date; unknown fields are rejected.")
        kind = data["kind"]
        if kind not in ("expense", "income"):
            raise ValidationError("Kind must be expense or income.")
        identifier = data["category_id"]
        if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
            raise ValidationError("Category ID must be a positive integer.")
        self._category(conn, identifier, kind)
        method = data.get("payment_method", "Card")
        if method not in PAYMENT_METHODS:
            raise ValidationError("Unsupported payment method.")
        return {"amount_cents": money(data["amount"]), "kind": kind, "category_id": identifier,
                "date": day(data["date"]), "description": text(data.get("description", ""), "Description", 500, True), "payment_method": method}

    def add_transaction(self, **data):
        with self.db.connect() as conn:
            payload = self._payload(conn, data)
            cursor = conn.execute("INSERT INTO transactions(amount_cents,kind,category_id,date,description,payment_method) VALUES (:amount_cents,:kind,:category_id,:date,:description,:payment_method)", payload)
            identifier = cursor.lastrowid
            item = repository.transaction(conn, identifier)
            self._unusual(conn, item)
            self._budget_alerts(conn, item["date"][:7])
            return {"transaction": item, "alerts": self._alerts(conn, transaction_id=identifier)}

    def get_transaction(self, identifier):
        with self.db.connect() as conn:
            item = repository.transaction(conn, identifier)
            if not item:
                raise NotFoundError("Transaction not found.")
            return item

    def update_transaction(self, identifier, **changes):
        with self.db.connect() as conn:
            old = repository.transaction(conn, identifier)
            if not old:
                raise NotFoundError("Transaction not found.")
            if not changes:
                raise ValidationError("Provide at least one field to update.")
            data = {"amount": str(Decimal(old["amount_cents"]) / 100), **{key: old[key] for key in ("kind", "category_id", "date", "description", "payment_method")}}
            data.update(changes)
            payload = self._payload(conn, data)
            payload["id"] = identifier
            conn.execute("UPDATE transactions SET amount_cents=:amount_cents,kind=:kind,category_id=:category_id,date=:date,description=:description,payment_method=:payment_method WHERE id=:id", payload)
            conn.execute("DELETE FROM alerts WHERE transaction_id=? AND kind='unusual'", (identifier,))
            item = repository.transaction(conn, identifier)
            self._unusual(conn, item)
            self._budget_alerts(conn, item["date"][:7])
            return {"transaction": item, "alerts": self._alerts(conn, transaction_id=identifier)}

    def delete_transaction(self, identifier):
        with self.db.connect() as conn:
            if conn.execute("DELETE FROM transactions WHERE id=?", (identifier,)).rowcount == 0:
                raise NotFoundError("Transaction not found.")

    def list_transactions(self, month_value=None, kind=None, category_id=None, search=None, unusual=False, limit=15, offset=0):
        if month_value is not None:
            month(month_value)
        if kind is not None and kind not in ("expense", "income"):
            raise ValidationError("Kind must be expense or income.")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100 or not isinstance(offset, int) or offset < 0:
            raise ValidationError("Limit must be 1–100 and offset nonnegative.")
        if search is not None:
            search = text(search, "Search", 200, True)
        with self.db.connect() as conn:
            if category_id is not None and not conn.execute("SELECT 1 FROM categories WHERE id=?", (category_id,)).fetchone():
                raise ValidationError("Unknown category.")
            return repository.transactions(conn, month_value, kind, category_id, search, unusual, limit, offset)

    def _unusual(self, conn, item):
        if item["kind"] != "expense":
            return
        baseline = conn.execute("SELECT COUNT(*),COALESCE(SUM(amount_cents),0) FROM transactions WHERE kind='expense' AND category_id=? AND id!=? AND date<=? AND id<?", (item["category_id"], item["id"], item["date"], item["id"])).fetchone()
        count, total = baseline
        if count >= 3 and item["amount_cents"] * count > total * 2:
            average = Decimal(total) / count / 100
            ratio = Decimal(item["amount_cents"] * count) / total
            message = f"{ratio:.1f}x your previous {item['category']} average (TRY {average:.2f}, {count} previous expenses)."
            conn.execute("INSERT OR IGNORE INTO alerts(month,kind,transaction_id,message) VALUES (?,'unusual',?,?)", (item["date"][:7], item["id"], message))

    def _budget_alerts(self, conn, month_value):
        for budget in self._budgets(conn, month_value):
            for threshold in (80, 100):
                if budget["spent_cents"] * 100 >= budget["limit_cents"] * threshold:
                    label = budget["category"] or "Monthly budget"
                    message = f"{label} reached {threshold}% for {month_value}: TRY {budget['spent_cents']/100:.2f} spent of TRY {budget['limit_cents']/100:.2f}."
                    conn.execute("INSERT OR IGNORE INTO alerts(month,kind,budget_id,threshold,message) VALUES (?,'budget',?,?,?)", (month_value, budget["id"], threshold, message))

    def set_budget(self, month_value, amount, category_id=None):
        month(month_value)
        cents = money(amount)
        with self.db.connect() as conn:
            if category_id is not None:
                self._category(conn, category_id, "expense")
            existing = conn.execute("SELECT id FROM budgets WHERE month=? AND category_id IS ?", (month_value, category_id)).fetchone()
            if existing:
                conn.execute("UPDATE budgets SET limit_cents=? WHERE id=?", (cents, existing["id"]))
                identifier = existing["id"]
            else:
                identifier = conn.execute("INSERT INTO budgets(month,category_id,limit_cents) VALUES (?,?,?)", (month_value, category_id, cents)).lastrowid
            self._budget_alerts(conn, month_value)
            return next(b for b in self._budgets(conn, month_value) if b["id"] == identifier)

    def _budgets(self, conn, month_value):
        rows = conn.execute("""SELECT b.*,c.name AS category,
            COALESCE((SELECT SUM(t.amount_cents) FROM transactions t WHERE t.kind='expense' AND substr(t.date,1,7)=b.month AND (b.category_id IS NULL OR t.category_id=b.category_id)),0) AS spent_cents
            FROM budgets b LEFT JOIN categories c ON b.category_id=c.id WHERE b.month=? ORDER BY b.id""", (month_value,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item.update(remaining_cents=item["limit_cents"]-item["spent_cents"], percentage=round(item["spent_cents"] * 100 / item["limit_cents"], 2), status="over" if item["spent_cents"] >= item["limit_cents"] else "warning" if item["spent_cents"]*100 >= item["limit_cents"]*80 else "on_track")
            result.append(item)
        return result

    def budgets(self, month_value):
        month(month_value)
        with self.db.connect() as conn:
            return self._budgets(conn, month_value)

    def delete_budget(self, identifier):
        with self.db.connect() as conn:
            if conn.execute("DELETE FROM budgets WHERE id=?", (identifier,)).rowcount == 0:
                raise NotFoundError("Budget not found.")

    def _alerts(self, conn, month_value=None, transaction_id=None):
        conditions, values = [], []
        if month_value:
            conditions.append("month=?")
            values.append(month_value)
        if transaction_id:
            conditions.append("(transaction_id=? OR budget_id IN (SELECT id FROM budgets WHERE month=(SELECT substr(date,1,7) FROM transactions WHERE id=?)))")
            values.extend([transaction_id, transaction_id])
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return [dict(row) for row in conn.execute("SELECT * FROM alerts" + where + " ORDER BY id DESC", values)]

    def alerts(self, month_value=None):
        if month_value is not None:
            month(month_value)
        with self.db.connect() as conn:
            return self._alerts(conn, month_value)

    def read_alert(self, identifier):
        with self.db.connect() as conn:
            if conn.execute("UPDATE alerts SET is_read=1 WHERE id=?", (identifier,)).rowcount == 0:
                raise NotFoundError("Alert not found.")
            return dict(conn.execute("SELECT * FROM alerts WHERE id=?", (identifier,)).fetchone())

    def summary(self, month_value, today=None):
        month(month_value)
        today = today or datetime.now(timezone(timedelta(hours=3))).date()
        year, number = map(int, month_value.split("-"))
        days = calendar.monthrange(year, number)[1]
        elapsed = days if month_value < today.strftime("%Y-%m") else today.day if month_value == today.strftime("%Y-%m") else 0
        with self.db.connect() as conn:
            totals = {row["kind"]: row["total"] for row in conn.execute("SELECT kind,SUM(amount_cents) AS total FROM transactions WHERE substr(date,1,7)=? GROUP BY kind", (month_value,))}
            expenses, income = totals.get("expense", 0), totals.get("income", 0)
            categories = [dict(r) for r in conn.execute("SELECT c.id,c.name,SUM(t.amount_cents) AS amount_cents FROM transactions t JOIN categories c ON c.id=t.category_id WHERE t.kind='expense' AND substr(t.date,1,7)=? GROUP BY c.id ORDER BY amount_cents DESC", (month_value,))]
            daily = [dict(r) for r in conn.execute("SELECT date,SUM(amount_cents) AS amount_cents FROM transactions WHERE kind='expense' AND substr(date,1,7)=? GROUP BY date ORDER BY date", (month_value,))]
            methods = [dict(r) for r in conn.execute("SELECT payment_method,SUM(amount_cents) AS amount_cents FROM transactions WHERE kind='expense' AND substr(date,1,7)=? GROUP BY payment_method", (month_value,))]
            biggest = [dict(r) for r in conn.execute(repository.TRANSACTION_SELECT + " WHERE t.kind='expense' AND substr(t.date,1,7)=? ORDER BY t.amount_cents DESC,t.id DESC LIMIT 5", (month_value,))]
            unusual = conn.execute("SELECT COUNT(*) FROM alerts WHERE kind='unusual' AND month=?", (month_value,)).fetchone()[0]
            # Forecast uses expenses dated on or before today, not future-dated entries.
            to_date = conn.execute("SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE kind='expense' AND substr(date,1,7)=? AND date<=?", (month_value, today.isoformat())).fetchone()[0]
            def rounded(value):
                return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            return {"month": month_value, "currency": "TRY", "income_cents": income, "expense_cents": expenses, "balance_cents": income-expenses, "days_in_month": days, "elapsed_days": elapsed,
                    "average_daily_cents": rounded(Decimal(to_date)/elapsed) if elapsed else None,
                    "forecast_cents": rounded(Decimal(to_date)*days/elapsed) if elapsed else None,
                    "forecast_explanation": "Expenses through today / elapsed calendar days * days in month; future-dated expenses excluded.",
                    "unusual_count": unusual, "by_category": categories, "by_day": daily, "by_payment_method": methods, "biggest_expenses": biggest, "budgets": self._budgets(conn, month_value)}

    def export_csv(self, month_value):
        month(month_value)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["id", "type", "amount", "currency", "category", "date", "description", "payment_method"])
        def safe(value):
            return "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
        with self.db.connect() as conn:
            for row in conn.execute(repository.TRANSACTION_SELECT + " WHERE substr(t.date,1,7)=? ORDER BY t.date,t.id", (month_value,)):
                writer.writerow([row["id"], row["kind"], f"{Decimal(row['amount_cents'])/100:.2f}", "TRY", safe(row["category"]), row["date"], safe(row["description"]), row["payment_method"]])
        return output.getvalue().encode("utf-8-sig")

    def suggest_category(self, description, kind="expense"):
        description = text(description, "Description", 500, True)
        if kind not in ("expense", "income"):
            raise ValidationError("Kind must be expense or income.")
        rules = {"Food & Dining": ("lunch", "dinner", "coffee", "restaurant", "breakfast"),
                 "Groceries": ("migros", "bim", "market", "groceries"),
                 "Transport": ("uber", "taxi", "metro", "bus", "istanbulkart"),
                 "Rent & Bills": ("rent", "electricity", "water bill", "internet"),
                 "Shopping": ("clothes", "shoes", "shopping"),
                 "Education": ("book", "course", "tuition"), "Health": ("pharmacy", "doctor", "medicine"),
                 "Entertainment": ("cinema", "movie", "concert"), "Subscriptions": ("netflix", "spotify", "subscription")}
        if kind == "income":
            rules = {"Allowance": ("allowance",), "Salary": ("salary",), "Freelance": ("freelance",)}
        import re
        for category, words in rules.items():
            for word in words:
                if re.search(r"\b" + re.escape(word) + r"\b", description.casefold()):
                    item = next(c for c in self.categories() if c["name"] == category)
                    return {"category_id": item["id"], "category": category, "reason": f"Matched the word '{word}'."}
        name = "Other" if kind == "expense" else "Other Income"
        item = next(c for c in self.categories() if c["name"] == name)
        return {"category_id": item["id"], "category": name, "reason": "No keyword matched. Choose a category to override."}

    def copy_budgets(self, month_value):
        month(month_value)
        year, number = map(int, month_value.split("-"))
        if year == 1 and number == 1:
            raise ValidationError("There is no previous supported month.")
        previous = f"{year-1:04d}-12" if number == 1 else f"{year:04d}-{number-1:02d}"
        with self.db.connect() as conn:
            copied = 0
            for row in conn.execute("SELECT * FROM budgets WHERE month=?", (previous,)).fetchall():
                cursor = conn.execute("INSERT OR IGNORE INTO budgets(month,category_id,limit_cents) VALUES (?,?,?)", (month_value, row["category_id"], row["limit_cents"]))
                copied += cursor.rowcount
            self._budget_alerts(conn, month_value)
            return {"copied": copied, "source_month": previous, "budgets": self._budgets(conn, month_value)}

    def history(self, month_value):
        month(month_value)
        year, number = map(int, month_value.split("-"))
        index = (year - 1) * 12 + number - 1
        result = []
        with self.db.connect() as conn:
            for value in range(max(0, index-5), index+1):
                y, m = divmod(value, 12)
                label = f"{y+1:04d}-{m+1:02d}"
                totals = {r["kind"]: r["total"] for r in conn.execute("SELECT kind,SUM(amount_cents) AS total FROM transactions WHERE substr(date,1,7)=? GROUP BY kind", (label,))}
                result.append({"month": label, "income_cents": totals.get("income",0), "expense_cents": totals.get("expense",0)})
        return result
