"""Pure debt-schedule rules: no I/O, no framework dependencies.

Mirrors the SQL `generate_debt_schedule` RPC (see
`supabase/migrations/0006_debt_schedule_and_alerts.sql`) so both sides can be
compared in a differential test, and so `installment_total_below_principal`
can be rejected before any row is written. The live `SupabaseGateway` path
never calls `build_schedule` directly — it delegates to the server-
authoritative RPC (see design.md's "Where the math lives" decision);
`InMemorySupabaseGateway` uses it as its schedule engine.
"""

import calendar
from datetime import date
from typing import Any


class DebtScheduleError(Exception):
    """Raised when a debt cannot be created or scheduled.

    `code` is a stable machine-readable reason; routes map it to an HTTP
    status and `ApiError` code so the domain layer stays HTTP-agnostic.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_installments(principal_minor: int, installment_minor: int, installment_count: int) -> None:
    """Reject a schedule whose installments could never cover the principal.

    Excess over principal (interest/fees) is legitimate; a shortfall is not
    — see design.md's "Installment amount" decision.
    """
    if installment_minor * installment_count < principal_minor:
        raise DebtScheduleError(
            "installment_total_below_principal",
            "installment_minor * installment_count must be at least principal_minor",
        )


def add_months(base: date, months: int) -> date:
    """Add whole calendar months to `base`, clamping the day to the target
    month's length (Jan 31 + 1 month -> Feb 28, or Feb 29 on a leap year).
    """
    total_months = base.year * 12 + (base.month - 1) + months
    year, month = divmod(total_months, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(base.day, last_day)
    return date(year, month, day)


def resolve_schedule_start(periods: list[dict[str, Any]], created_on: date) -> date:
    """The first installment is dated at the start of the earliest budget
    period beginning strictly after the debt was created; if none exists,
    the caller must define one first.
    """
    later = [period["starts_on"] for period in periods if period["starts_on"] > created_on]
    if not later:
        raise DebtScheduleError("no_later_period", "No later budget period exists to anchor the schedule")
    return min(later)


def build_schedule(debt: dict[str, Any], periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure mirror of the SQL RPC: installment `ordinal` 1 lands on the
    resolved start date, and each following ordinal adds one clamped
    calendar month from that same start (not from the previous installment,
    which would compound clamping drift across a schedule).
    """
    start = resolve_schedule_start(periods, debt["created_on"])
    return [
        {"ordinal": ordinal, "due_on": add_months(start, ordinal - 1), "amount_minor": debt["installment_minor"]}
        for ordinal in range(1, debt["installment_count"] + 1)
    ]
