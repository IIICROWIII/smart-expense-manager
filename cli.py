"""Argument-based CLI using the same service as the REST API."""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from backend.database import Database
from backend.services import ExpenseService, PAYMENT_METHODS
from backend.validation import NotFoundError, ValidationError


def parser():
    p = argparse.ArgumentParser(description="Smart Expense Manager (TRY)")
    p.add_argument("--db", default=os.getenv("EXPENSE_DB_PATH", str(Path(__file__).resolve().parent / "data" / "expenses.db")))
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("categories", help="List category IDs")
    add = commands.add_parser("add", help="Record an expense or income")
    add.add_argument("--amount", required=True)
    add.add_argument("--kind", choices=["expense", "income"], default="expense")
    add.add_argument("--category-id", type=int, required=True)
    add.add_argument("--date", required=True)
    add.add_argument("--description", default="")
    add.add_argument("--payment-method", choices=PAYMENT_METHODS, default="Card")
    listing = commands.add_parser("list", help="Search and filter transactions")
    listing.add_argument("--month")
    listing.add_argument("--kind", choices=["expense", "income"])
    listing.add_argument("--category-id", type=int)
    listing.add_argument("--search")
    listing.add_argument("--unusual", action="store_true")
    listing.add_argument("--limit", type=int, default=15)
    listing.add_argument("--offset", type=int, default=0)
    update = commands.add_parser("update", help="Change a transaction")
    update.add_argument("id", type=int)
    for field in ("amount", "date", "description"):
        update.add_argument("--" + field)
    update.add_argument("--category-id", type=int)
    update.add_argument("--kind", choices=["expense", "income"])
    update.add_argument("--payment-method", choices=PAYMENT_METHODS)
    delete = commands.add_parser("delete", help="Delete a transaction")
    delete.add_argument("id", type=int)
    budget = commands.add_parser("budget", help="Set a monthly or category budget")
    budget.add_argument("--month", required=True)
    budget.add_argument("--amount", required=True)
    budget.add_argument("--category-id", type=int)
    for name in ("budgets", "summary", "export"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--month", required=True)
    commands.add_parser("alerts")
    read = commands.add_parser("read-alert")
    read.add_argument("id", type=int)
    remove = commands.add_parser("delete-budget")
    remove.add_argument("id", type=int)
    return p


def main(argv=None):
    args = vars(parser().parse_args(argv))
    command = args.pop("command")
    db = Database(args.pop("db"))
    try:
        db.initialize()
        service = ExpenseService(db)
        if command == "categories":
            result = service.categories()
        elif command == "add":
            result = service.add_transaction(**args)
        elif command == "update":
            identifier = args.pop("id")
            result = service.update_transaction(identifier, **{k: v for k, v in args.items() if v is not None})
        elif command == "delete":
            service.delete_transaction(args["id"])
            result = {"deleted": args["id"]}
        elif command == "list":
            args["month_value"] = args.pop("month")
            result = service.list_transactions(**args)
        elif command == "budget":
            result = service.set_budget(args["month"], args["amount"], args["category_id"])
        elif command == "budgets":
            result = service.budgets(args["month"])
        elif command == "summary":
            result = service.summary(args["month"])
        elif command == "export":
            sys.stdout.buffer.write(service.export_csv(args["month"]))
            return 0
        elif command == "alerts":
            result = service.alerts()
        elif command == "read-alert":
            result = service.read_alert(args["id"])
        elif command == "delete-budget":
            service.delete_budget(args["id"])
            result = {"deleted": args["id"]}
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValidationError, NotFoundError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError):
        print("Storage operation failed. Check database access.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
