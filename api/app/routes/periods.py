from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, field_validator

from app.core.auth import Principal, get_current_principal
from app.core.errors import ApiError
from app.domain.periods import PeriodConflictError, assert_no_overlap, assert_transition, assert_version_matches
from app.repositories.supabase import FinanceGateway, get_gateway

router = APIRouter(prefix="/periods", tags=["periods"])

# Maps a domain-layer PeriodConflictError.code to its HTTP status. Kept
# here (not in app.domain.periods) so the domain layer stays HTTP-agnostic.
_ERROR_STATUS = {
    "period_overlap": 409,
    "version_conflict": 409,
    "invalid_transition": 409,
}


def _raise(error: PeriodConflictError) -> None:
    raise ApiError(_ERROR_STATUS.get(error.code, 409), error.code, error.message)


class CreatePeriodRequest(BaseModel):
    starts_on: date
    ends_on: date

    @field_validator("ends_on")
    @classmethod
    def ends_not_before_start(cls, value: date, info) -> date:
        starts_on = info.data.get("starts_on")
        if starts_on is not None and value < starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return value


class PeriodResponse(BaseModel):
    id: str
    starts_on: date
    ends_on: date
    status: str
    version: int


def _response(period: dict) -> PeriodResponse:
    return PeriodResponse(
        id=period["id"], starts_on=period["starts_on"], ends_on=period["ends_on"], status=period["status"], version=period["version"]
    )


def _get_or_404(gateway: FinanceGateway, user_id: str, period_id: str) -> dict:
    period = gateway.get_period(user_id, period_id)
    if period is None:
        raise ApiError(404, "resource_not_found", "Resource not found")
    return period


@router.post("", response_model=PeriodResponse, status_code=201)
async def create_period(
    body: CreatePeriodRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> PeriodResponse:
    existing = gateway.list_periods(principal.user_id)
    try:
        assert_no_overlap(existing, body.starts_on, body.ends_on)
    except PeriodConflictError as error:
        _raise(error)
    return _response(gateway.create_period(principal.user_id, body.starts_on, body.ends_on))


@router.get("", response_model=list[PeriodResponse])
async def list_periods(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> list[PeriodResponse]:
    return [_response(period) for period in gateway.list_periods(principal.user_id)]


async def _transition(
    period_id: str,
    target_status: str,
    if_match: str | None,
    principal: Principal,
    gateway: FinanceGateway,
) -> PeriodResponse:
    if if_match is None:
        raise ApiError(428, "if_match_required", "If-Match header is required", {"if_match": "required"})
    try:
        expected_version = int(if_match)
    except ValueError:
        raise ApiError(400, "invalid_if_match", "If-Match must be an integer version", {"if_match": "invalid"}) from None

    period = _get_or_404(gateway, principal.user_id, period_id)
    try:
        assert_transition(period, target_status)
        assert_version_matches(period, expected_version)
    except PeriodConflictError as error:
        _raise(error)

    mutate = gateway.close_period if target_status == "closed" else gateway.reopen_period
    try:
        updated = mutate(principal.user_id, period_id, expected_version)
    except PeriodConflictError as error:
        # The live SupabaseGateway path raises this directly from the RPC
        # (see repositories/supabase.py._transition_period) rather than
        # returning None — must be caught here too, or it falls through to
        # the generic 500 handler instead of the 409 this endpoint promises.
        _raise(error)
    if updated is None:
        # The pre-check above passed but the atomic mutation still lost the
        # race (concurrent request already changed the version) or the
        # period was removed in between; either way this is a conflict.
        raise ApiError(409, "version_conflict", "The period was modified by another request")
    return _response(updated)


@router.post("/{period_id}/close", response_model=PeriodResponse)
async def close_period(
    period_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> PeriodResponse:
    return await _transition(period_id, "closed", if_match, principal, gateway)


@router.post("/{period_id}/reopen", response_model=PeriodResponse)
async def reopen_period(
    period_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> PeriodResponse:
    return await _transition(period_id, "open", if_match, principal, gateway)
