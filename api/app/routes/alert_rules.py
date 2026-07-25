from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator

from app.core.auth import Principal, get_current_principal
from app.core.errors import ApiError
from app.repositories.supabase import FinanceGateway, get_gateway

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


class CreateAlertRuleRequest(BaseModel):
    label: str
    kind: str
    threshold_minor: int = Field(gt=0)
    category_id: str | None = None

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= 100):
            raise ValueError("label must be between 1 and 100 characters")
        return trimmed

    @field_validator("kind")
    @classmethod
    def kind_supported(cls, value: str) -> str:
        if value not in ("expense_total", "debt_due"):
            raise ValueError("kind must be 'expense_total' or 'debt_due'")
        return value


class AlertRuleResponse(BaseModel):
    id: str
    label: str
    kind: str
    threshold_minor: int
    category_id: str | None = None


def _response(rule: dict) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule["id"],
        label=rule["label"],
        kind=rule["kind"],
        threshold_minor=rule["threshold_minor"],
        category_id=rule.get("category_id"),
    )


@router.post("", response_model=AlertRuleResponse, status_code=201)
async def create_alert_rule(
    body: CreateAlertRuleRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> AlertRuleResponse:
    if body.category_id is not None:
        # Owner-only categories: a missing or foreign category_id both 404,
        # matching the ledger routes' category-write validation.
        category = gateway.get_category(principal.user_id, body.category_id)
        if category is None:
            raise ApiError(404, "resource_not_found", "Resource not found")
    return _response(
        gateway.create_alert_rule(principal.user_id, body.label, body.kind, body.threshold_minor, body.category_id)
    )


@router.get("", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> list[AlertRuleResponse]:
    return [_response(rule) for rule in gateway.list_alert_rules(principal.user_id)]


@router.delete("/{rule_id}", status_code=204)
async def delete_alert_rule(
    rule_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> Response:
    deleted = gateway.delete_alert_rule(principal.user_id, rule_id)
    if not deleted:
        raise ApiError(404, "resource_not_found", "Resource not found")
    return Response(status_code=204)
