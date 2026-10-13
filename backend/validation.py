"""Validation shared by the API and CLI."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation


class ValidationError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


def money(value):
    if isinstance(value, bool):
        raise ValidationError("Amount must be a positive monetary value.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError("Amount must be a number.") from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000000"):
        raise ValidationError("Amount must be greater than 0 and at most 1,000,000,000.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError("Amount must have at most two decimal places.")
    return int(amount * 100)


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValidationError("Date must use YYYY-MM-DD.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValidationError("Date must be a valid calendar date.") from None
    return value


def month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValidationError("Month must use YYYY-MM.")
    day(value + "-01")
    return value


def text(value, label, maximum, allow_empty=False):
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text.")
    value = value.strip()
    if (not value and not allow_empty) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValidationError(f"{label} must contain {'0' if allow_empty else '1'} to {maximum} characters without control characters.")
    return value
