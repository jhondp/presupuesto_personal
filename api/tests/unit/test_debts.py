import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.debts import (
    DebtScheduleError,
    add_months,
    build_schedule,
    resolve_schedule_start,
    validate_installments,
)


def _period(**overrides) -> dict:
    base = {"id": "p1", "starts_on": date(2026, 2, 1), "ends_on": date(2026, 2, 28), "status": "open", "version": 1}
    base.update(overrides)
    return base


def _debt(**overrides) -> dict:
    base = {
        "id": "d1",
        "created_on": date(2026, 1, 10),
        "installment_minor": 100_000,
        "installment_count": 3,
    }
    base.update(overrides)
    return base


# --- add_months clamping ---


def test_add_months_clamps_january_31_to_february_28_on_a_non_leap_year():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_add_months_clamps_january_31_to_february_29_on_a_leap_year():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_does_not_clamp_when_the_target_month_has_enough_days():
    assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)


def test_add_months_rolls_over_the_year_boundary():
    assert add_months(date(2026, 12, 5), 1) == date(2027, 1, 5)


def test_add_months_zero_is_a_no_op():
    assert add_months(date(2026, 3, 20), 0) == date(2026, 3, 20)


# --- next-period resolution ---


def test_resolve_schedule_start_returns_the_earliest_period_starting_after_creation():
    periods = [_period(id="p1", starts_on=date(2026, 3, 1)), _period(id="p2", starts_on=date(2026, 2, 1))]
    assert resolve_schedule_start(periods, date(2026, 1, 10)) == date(2026, 2, 1)


def test_resolve_schedule_start_ignores_periods_starting_on_or_before_creation():
    periods = [_period(starts_on=date(2026, 1, 1))]
    with pytest.raises(DebtScheduleError) as exc_info:
        resolve_schedule_start(periods, date(2026, 1, 10))
    assert exc_info.value.code == "no_later_period"


def test_resolve_schedule_start_rejects_when_no_period_exists():
    with pytest.raises(DebtScheduleError) as exc_info:
        resolve_schedule_start([], date(2026, 1, 10))
    assert exc_info.value.code == "no_later_period"


# --- installment validation ---


def test_installment_total_below_principal_is_rejected():
    with pytest.raises(DebtScheduleError) as exc_info:
        validate_installments(principal_minor=1_000_000, installment_minor=100_000, installment_count=5)
    assert exc_info.value.code == "installment_total_below_principal"


def test_installment_total_exactly_matching_principal_is_accepted():
    validate_installments(principal_minor=1_000_000, installment_minor=100_000, installment_count=10)  # must not raise


def test_installment_total_exceeding_principal_is_accepted():
    validate_installments(principal_minor=1_000_000, installment_minor=100_000, installment_count=11)  # must not raise


# --- full schedule build ---


def test_build_schedule_anchors_installment_one_at_the_next_period_start():
    schedule = build_schedule(_debt(installment_count=1), [_period(starts_on=date(2026, 2, 1))])
    assert schedule == [{"ordinal": 1, "due_on": date(2026, 2, 1), "amount_minor": 100_000}]


def test_build_schedule_advances_one_calendar_month_per_ordinal_from_the_start():
    schedule = build_schedule(_debt(installment_count=3), [_period(starts_on=date(2026, 1, 31))])
    assert [item["due_on"] for item in schedule] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


def test_build_schedule_rejects_when_no_later_period_exists():
    with pytest.raises(DebtScheduleError) as exc_info:
        build_schedule(_debt(created_on=date(2026, 3, 1)), [_period(starts_on=date(2026, 1, 1))])
    assert exc_info.value.code == "no_later_period"
