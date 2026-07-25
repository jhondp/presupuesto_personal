from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.core.auth import Principal, get_current_principal
from app.core.errors import ApiError
from app.domain.debts import DebtScheduleError, validate_installments
from app.repositories.supabase import FinanceGateway, get_gateway

router = APIRouter(prefix="/debts", tags=["debts"])

# Maps a domain-layer DebtScheduleError.code to its HTTP status. Kept here
# (not in app.domain.debts) so the domain layer stays HTTP-agnostic.
_ERROR_STATUS = {
    "no_later_period": 409,
    "installment_total_below_principal": 422,
}


def _raise(error: DebtScheduleError) -> None:
    raise ApiError(_ERROR_STATUS.get(error.code, 409), error.code, error.message)


class CreateDebtRequest(BaseModel):
    bank: str
    principal_minor: int = Field(gt=0)
    installment_minor: int = Field(gt=0)
    installment_count: int = Field(gt=0)

    @field_validator("bank")
    @classmethod
    def bank_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= 100):
            raise ValueError("bank must be between 1 and 100 characters")
        return trimmed


class DebtResponse(BaseModel):
    id: str
    bank: str
    principal_minor: int
    installment_minor: int
    installment_count: int


class InstallmentResponse(BaseModel):
    id: str
    debt_id: str
    ordinal: int
    due_on: date
    amount_minor: int


def _debt_response(debt: dict) -> DebtResponse:
    return DebtResponse(
        id=debt["id"],
        bank=debt["bank"],
        principal_minor=debt["principal_minor"],
        installment_minor=debt["installment_minor"],
        installment_count=debt["installment_count"],
    )


def _installment_response(installment: dict) -> InstallmentResponse:
    return InstallmentResponse(
        id=installment["id"],
        debt_id=installment["debt_id"],
        ordinal=installment["ordinal"],
        due_on=installment["due_on"],
        amount_minor=installment["amount_minor"],
    )


def _get_or_404(gateway: FinanceGateway, user_id: str, debt_id: str) -> dict:
    debt = gateway.get_debt(user_id, debt_id)
    if debt is None:
        raise ApiError(404, "resource_not_found", "Resource not found")
    return debt


@router.post("", response_model=DebtResponse, status_code=201)
async def create_debt(
    body: CreateDebtRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> DebtResponse:
    try:
        validate_installments(body.principal_minor, body.installment_minor, body.installment_count)
    except DebtScheduleError as error:
        _raise(error)
    return _debt_response(
        gateway.create_debt(principal.user_id, body.bank, body.principal_minor, body.installment_minor, body.installment_count)
    )


@router.get("", response_model=list[DebtResponse])
async def list_debts(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> list[DebtResponse]:
    return [_debt_response(debt) for debt in gateway.list_debts(principal.user_id)]


@router.get("/{debt_id}", response_model=DebtResponse)
async def get_debt(
    debt_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> DebtResponse:
    return _debt_response(_get_or_404(gateway, principal.user_id, debt_id))


@router.post("/{debt_id}/schedule", response_model=list[InstallmentResponse])
async def generate_schedule(
    debt_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> list[InstallmentResponse]:
    # generate_debt_schedule re-checks ownership itself (mirrors the RPC's
    # locked `for update ... where user_id = auth.uid()`) rather than trusting
    # a separate pre-check, exactly like periods._transition's mutate step.
    try:
        installments = gateway.generate_debt_schedule(principal.user_id, debt_id)
    except DebtScheduleError as error:
        _raise(error)
    if installments is None:
        raise ApiError(404, "resource_not_found", "Resource not found")
    return [_installment_response(installment) for installment in installments]
