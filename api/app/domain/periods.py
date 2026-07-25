"""Pure budget-period rules: no I/O, no framework dependencies.

Every function here operates on plain dicts (as returned by `FinanceGateway`)
so it can be unit-tested without a database and reused identically by the
`periods`, `income`, and `expenses` routes.
"""

from datetime import date
from typing import Any


class PeriodConflictError(Exception):
    """Raised when a period cannot be created, resolved, or transitioned.

    `code` is a stable machine-readable reason; routes map it to an HTTP
    status and `ApiError` code so the domain layer stays HTTP-agnostic.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _periods_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def assert_no_overlap(
    existing: list[dict[str, Any]], starts_on: date, ends_on: date, *, exclude_id: str | None = None
) -> None:
    """A user's periods may never overlap, regardless of open/closed status.

    This keeps `resolve_open_period` unambiguous: at most one of a user's
    periods can ever cover a given date.
    """
    for period in existing:
        if exclude_id is not None and period["id"] == exclude_id:
            continue
        if _periods_overlap(period["starts_on"], period["ends_on"], starts_on, ends_on):
            raise PeriodConflictError("period_overlap", "Period overlaps an existing period")


def resolve_open_period(periods: list[dict[str, Any]], occurred_on: date) -> dict[str, Any]:
    """Resolve the single open period covering `occurred_on`, or reject the write.

    Relies on the non-overlap invariant enforced by `assert_no_overlap`: at
    most one period (open or closed) can cover any given date, so filtering
    to `status == "open"` yields at most one match.
    """
    matches = [period for period in periods if period["status"] == "open" and period["starts_on"] <= occurred_on <= period["ends_on"]]
    if not matches:
        raise PeriodConflictError("no_open_period", "No open budget period covers this date")
    return matches[0]


def assert_period_writable(period: dict[str, Any]) -> None:
    if period["status"] != "open":
        raise PeriodConflictError("period_closed", "This period is closed; reopen it to make changes")


def assert_version_matches(period: dict[str, Any], expected_version: int) -> None:
    if period["version"] != expected_version:
        raise PeriodConflictError("version_conflict", "The period was modified by another request")


def assert_transition(period: dict[str, Any], target_status: str) -> None:
    if target_status == "closed" and period["status"] != "open":
        raise PeriodConflictError("invalid_transition", "Only an open period can be closed")
    if target_status == "open" and period["status"] != "closed":
        raise PeriodConflictError("invalid_transition", "Only a closed period can be reopened")
