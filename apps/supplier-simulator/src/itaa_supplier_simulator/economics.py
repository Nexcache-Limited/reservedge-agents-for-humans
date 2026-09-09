"""Integer-only simulated commercial arithmetic. No binary floats."""

from __future__ import annotations

from datetime import datetime

from itaa_application.errors import ApplicationError

SCALE = 1_000_000
DAY_SECONDS = 86_400
JS_SAFE_MAX = 9007199254740991


def billable_days(start: datetime, end: datetime) -> int:
    seconds = int((end - start).total_seconds())
    if seconds <= 0:
        raise ApplicationError("service_window", "invalid")
    return (seconds + DAY_SECONDS - 1) // DAY_SECONDS


def scale_amount(amount: int, micros: int) -> int:
    if amount < 0 or micros < 0:
        raise ApplicationError("amount", "must_be_non_negative")
    product = amount * micros
    if product > JS_SAFE_MAX:
        raise ApplicationError("amount", "overflow")
    return (product + 500_000) // SCALE


def require_minor(amount: int, field: str) -> int:
    if type(amount) is not int or isinstance(amount, bool):
        raise ApplicationError(field, "must_be_integer")
    if amount < 0 or amount > JS_SAFE_MAX:
        raise ApplicationError(field, "out_of_range")
    return amount
