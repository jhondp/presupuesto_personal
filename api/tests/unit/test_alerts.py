import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.alerts import category_breakdown, evaluate, sum_amounts, sum_debt_due


def _entry(**overrides) -> dict:
    base = {"category_id": "cat-1", "amount_minor": 10_000}
    base.update(overrides)
    return base


def _installment(**overrides) -> dict:
    base = {"due_on": date(2026, 1, 15), "amount_minor": 50_000}
    base.update(overrides)
    return base


def _rule(**overrides) -> dict:
    base = {"id": "rule-1", "label": "Big spend", "kind": "expense_total", "threshold_minor": 100_000, "category_id": None}
    base.update(overrides)
    return base


# --- sum_amounts ---


def test_sum_amounts_totals_every_entry_when_no_category_is_given():
    entries = [_entry(amount_minor=10_000), _entry(amount_minor=25_000, category_id="cat-2")]
    assert sum_amounts(entries) == 35_000


def test_sum_amounts_scopes_to_a_single_category():
    entries = [_entry(amount_minor=10_000, category_id="cat-1"), _entry(amount_minor=25_000, category_id="cat-2")]
    assert sum_amounts(entries, category_id="cat-1") == 10_000


def test_sum_amounts_of_an_empty_list_is_zero():
    assert sum_amounts([]) == 0


# --- sum_debt_due ---


def test_sum_debt_due_only_counts_installments_within_the_range():
    installments = [
        _installment(due_on=date(2026, 1, 5), amount_minor=50_000),
        _installment(due_on=date(2026, 2, 5), amount_minor=70_000),
    ]
    assert sum_debt_due(installments, date(2026, 1, 1), date(2026, 1, 31)) == 50_000


def test_sum_debt_due_is_inclusive_of_the_range_boundaries():
    installments = [_installment(due_on=date(2026, 1, 1)), _installment(due_on=date(2026, 1, 31))]
    assert sum_debt_due(installments, date(2026, 1, 1), date(2026, 1, 31)) == 100_000


# --- category_breakdown ---


def test_category_breakdown_groups_and_totals_by_category():
    entries = [_entry(amount_minor=10_000, category_id="cat-1"), _entry(amount_minor=5_000, category_id="cat-1")]
    categories_by_id = {"cat-1": {"name": "Groceries", "kind": "expense"}}
    breakdown = category_breakdown(entries, categories_by_id)
    assert breakdown == [{"category_id": "cat-1", "name": "Groceries", "kind": "expense", "total_minor": 15_000}]


def test_category_breakdown_ignores_entries_with_no_category():
    entries = [_entry(category_id=None, amount_minor=10_000)]
    assert category_breakdown(entries, {}) == []


# --- evaluate ---


def test_expense_total_rule_fires_when_threshold_is_met():
    rules = [_rule(kind="expense_total", threshold_minor=100_000)]
    triggered = evaluate(
        rules,
        expense_entries=[_entry(amount_minor=100_000)],
        debt_installments=[],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
    )
    assert triggered == [{"rule_id": "rule-1", "label": "Big spend", "kind": "expense_total", "threshold_minor": 100_000, "actual_minor": 100_000}]


def test_expense_total_rule_does_not_fire_below_threshold():
    rules = [_rule(threshold_minor=100_000)]
    triggered = evaluate(
        rules,
        expense_entries=[_entry(amount_minor=99_999)],
        debt_installments=[],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
    )
    assert triggered == []


def test_expense_total_rule_is_scoped_to_its_category():
    rules = [_rule(threshold_minor=10_000, category_id="cat-1")]
    triggered = evaluate(
        rules,
        expense_entries=[_entry(amount_minor=10_000, category_id="cat-2")],
        debt_installments=[],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
    )
    assert triggered == []  # the matching amount is in a different category


def test_debt_due_rule_fires_from_installments_in_range():
    rules = [_rule(kind="debt_due", threshold_minor=50_000, category_id=None)]
    triggered = evaluate(
        rules,
        expense_entries=[],
        debt_installments=[_installment(due_on=date(2026, 1, 10), amount_minor=50_000)],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
    )
    assert triggered[0]["kind"] == "debt_due"
    assert triggered[0]["actual_minor"] == 50_000


def test_evaluate_returns_only_the_rules_that_fired():
    rules = [_rule(id="fires", threshold_minor=1), _rule(id="does-not-fire", threshold_minor=1_000_000)]
    triggered = evaluate(
        rules,
        expense_entries=[_entry(amount_minor=5_000)],
        debt_installments=[],
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
    )
    assert [rule["rule_id"] for rule in triggered] == ["fires"]
