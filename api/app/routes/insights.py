from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.auth import Principal, get_current_principal
from app.core.errors import ApiError
from app.domain.alerts import category_breakdown, evaluate, sum_amounts, sum_debt_due
from app.repositories.supabase import FinanceGateway, get_gateway

router = APIRouter(prefix="/insights", tags=["insights"])


class CategoryTotal(BaseModel):
    category_id: str
    name: str | None = None
    kind: str | None = None
    total_minor: int


class TriggeredAlert(BaseModel):
    rule_id: str
    label: str
    kind: str
    threshold_minor: int
    actual_minor: int


class InsightsResponse(BaseModel):
    period_id: str
    income_minor: int
    expense_minor: int
    balance_minor: int
    debt_due_minor: int
    by_category: list[CategoryTotal]
    alerts: list[TriggeredAlert]


@router.get("", response_model=InsightsResponse)
async def get_insights(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
    period_id: Annotated[str, Query()],
) -> InsightsResponse:
    # Owner-only period: missing or foreign both 404, matching every other
    # owner-scoped resource in this API.
    period = gateway.get_period(principal.user_id, period_id)
    if period is None:
        raise ApiError(404, "resource_not_found", "Resource not found")

    income_entries = gateway.list_entries(principal.user_id, "income_entries", period_id)
    expense_entries = gateway.list_entries(principal.user_id, "expense_entries", period_id)
    installments = gateway.list_installments(principal.user_id)
    categories_by_id = {category["id"]: category for category in gateway.list_categories(principal.user_id)}

    income_minor = sum_amounts(income_entries)
    expense_minor = sum_amounts(expense_entries)
    debt_due_minor = sum_debt_due(installments, period["starts_on"], period["ends_on"])
    by_category = category_breakdown(income_entries + expense_entries, categories_by_id)

    # This endpoint only reads: it never mutates a rule or records that it
    # fired (see design.md's "Alert rule shape" decision).
    rules = gateway.list_alert_rules(principal.user_id)
    alerts = evaluate(
        rules,
        expense_entries=expense_entries,
        debt_installments=installments,
        starts_on=period["starts_on"],
        ends_on=period["ends_on"],
    )

    return InsightsResponse(
        period_id=period_id,
        income_minor=income_minor,
        expense_minor=expense_minor,
        balance_minor=income_minor - expense_minor,
        debt_due_minor=debt_due_minor,
        by_category=[CategoryTotal(**row) for row in by_category],
        alerts=[TriggeredAlert(**alert) for alert in alerts],
    )
