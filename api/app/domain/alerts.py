"""Pure period-aggregate and alert-rule evaluation: no I/O.

Both rule kinds compare one minor-unit aggregate with `>=` against
`threshold_minor` (see design.md's Phase 3 addendum): `expense_total` sums
`expense_entries` in the period (optionally scoped to one category),
`debt_due` sums `debt_installments` whose `due_on` falls inside the period.
Evaluation is query-time only — it never mutates a rule or records that it
fired (payment tracking, `last_triggered_at`, and multi-operator rules are
out of scope).
"""

from datetime import date
from typing import Any


def sum_amounts(entries: list[dict[str, Any]], *, category_id: str | None = None) -> int:
    """Sum `amount_minor` across entries, optionally scoped to one category."""
    return sum(entry["amount_minor"] for entry in entries if category_id is None or entry.get("category_id") == category_id)


def sum_debt_due(installments: list[dict[str, Any]], starts_on: date, ends_on: date) -> int:
    """Sum installment amounts whose `due_on` falls within `[starts_on, ends_on]`."""
    return sum(installment["amount_minor"] for installment in installments if starts_on <= installment["due_on"] <= ends_on)


def category_breakdown(entries: list[dict[str, Any]], categories_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Group entries by `category_id`, returning one row per category present
    in the entries (not every category the user owns)."""
    totals: dict[str, int] = {}
    for entry in entries:
        category_id = entry.get("category_id")
        if category_id is None:
            continue
        totals[category_id] = totals.get(category_id, 0) + entry["amount_minor"]
    breakdown = []
    for category_id, total in totals.items():
        category = categories_by_id.get(category_id)
        breakdown.append(
            {
                "category_id": category_id,
                "name": category["name"] if category else None,
                "kind": category["kind"] if category else None,
                "total_minor": total,
            }
        )
    return breakdown


def evaluate(
    rules: list[dict[str, Any]],
    *,
    expense_entries: list[dict[str, Any]],
    debt_installments: list[dict[str, Any]],
    starts_on: date,
    ends_on: date,
) -> list[dict[str, Any]]:
    """Evaluate each rule against the viewed period's current aggregates.
    A rule that doesn't fire is simply absent from the result — there is no
    "not triggered" entry.
    """
    triggered = []
    for rule in rules:
        if rule["kind"] == "expense_total":
            actual = sum_amounts(expense_entries, category_id=rule.get("category_id"))
        elif rule["kind"] == "debt_due":
            actual = sum_debt_due(debt_installments, starts_on, ends_on)
        else:
            continue
        if actual >= rule["threshold_minor"]:
            triggered.append(
                {
                    "rule_id": rule["id"],
                    "label": rule["label"],
                    "kind": rule["kind"],
                    "threshold_minor": rule["threshold_minor"],
                    "actual_minor": actual,
                }
            )
    return triggered
