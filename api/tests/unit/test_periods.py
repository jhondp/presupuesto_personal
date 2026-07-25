import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.periods import (
    PeriodConflictError,
    assert_no_overlap,
    assert_period_writable,
    assert_transition,
    assert_version_matches,
    resolve_open_period,
)


def _period(**overrides) -> dict:
    base = {"id": "p1", "starts_on": date(2026, 1, 1), "ends_on": date(2026, 1, 31), "status": "open", "version": 1}
    base.update(overrides)
    return base


def test_overlapping_period_is_rejected():
    existing = [_period()]
    with pytest.raises(PeriodConflictError) as exc_info:
        assert_no_overlap(existing, date(2026, 1, 15), date(2026, 2, 15))
    assert exc_info.value.code == "period_overlap"


def test_adjacent_non_overlapping_periods_are_accepted():
    existing = [_period(ends_on=date(2026, 1, 31))]
    assert_no_overlap(existing, date(2026, 2, 1), date(2026, 2, 28))  # must not raise


def test_overlap_check_ignores_the_period_being_updated():
    existing = [_period(id="p1")]
    assert_no_overlap(existing, date(2026, 1, 1), date(2026, 1, 31), exclude_id="p1")  # must not raise


def test_resolving_open_period_with_no_match_is_rejected():
    existing = [_period(starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 31))]
    with pytest.raises(PeriodConflictError) as exc_info:
        resolve_open_period(existing, date(2026, 2, 5))
    assert exc_info.value.code == "no_open_period"


def test_resolving_open_period_skips_closed_periods_covering_the_date():
    existing = [_period(id="p1", status="closed")]
    with pytest.raises(PeriodConflictError) as exc_info:
        resolve_open_period(existing, date(2026, 1, 10))
    assert exc_info.value.code == "no_open_period"


def test_resolving_open_period_returns_the_covering_period():
    existing = [_period(id="p1"), _period(id="p2", starts_on=date(2026, 2, 1), ends_on=date(2026, 2, 28))]
    resolved = resolve_open_period(existing, date(2026, 1, 10))
    assert resolved["id"] == "p1"


def test_closed_period_is_not_writable():
    with pytest.raises(PeriodConflictError) as exc_info:
        assert_period_writable(_period(status="closed"))
    assert exc_info.value.code == "period_closed"


def test_open_period_is_writable():
    assert_period_writable(_period(status="open"))  # must not raise


def test_stale_version_is_rejected():
    with pytest.raises(PeriodConflictError) as exc_info:
        assert_version_matches(_period(version=3), expected_version=2)
    assert exc_info.value.code == "version_conflict"


def test_matching_version_is_accepted():
    assert_version_matches(_period(version=2), expected_version=2)  # must not raise


def test_closing_requires_open_status():
    with pytest.raises(PeriodConflictError) as exc_info:
        assert_transition(_period(status="closed"), "closed")
    assert exc_info.value.code == "invalid_transition"


def test_reopening_requires_closed_status():
    with pytest.raises(PeriodConflictError) as exc_info:
        assert_transition(_period(status="open"), "open")
    assert exc_info.value.code == "invalid_transition"


def test_closing_an_open_period_is_a_valid_transition():
    assert_transition(_period(status="open"), "closed")  # must not raise


def test_reopening_a_closed_period_is_a_valid_transition():
    assert_transition(_period(status="closed"), "open")  # must not raise
