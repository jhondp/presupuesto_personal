from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.core.auth import Principal, get_current_principal
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.repositories.supabase import CURRENCY_SCALES, FinanceGateway, get_gateway

router = APIRouter(tags=["profile"])


class ProfileResponse(BaseModel):
    currency_code: str
    decimal_scale: int


class UpdateProfileRequest(BaseModel):
    currency_code: str

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


def profile_response(profile: dict) -> ProfileResponse:
    return ProfileResponse(currency_code=profile["currency_code"], decimal_scale=profile["decimal_scale"])


@router.get("/profile", response_model=ProfileResponse)
async def get_my_profile(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> ProfileResponse:
    return profile_response(gateway.ensure_profile(principal.user_id))


@router.put("/profile", response_model=ProfileResponse)
async def update_my_profile(
    body: UpdateProfileRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProfileResponse:
    if body.currency_code not in settings.supported_currencies or body.currency_code not in CURRENCY_SCALES:
        raise ApiError(422, "unsupported_currency", "Currency is not supported", {"currency_code": "unsupported"})
    return profile_response(gateway.update_profile(principal.user_id, body.currency_code))


@router.get("/profiles/{user_id}", response_model=ProfileResponse)
async def get_profile_by_id(
    user_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> ProfileResponse:
    # Intentional non-disclosure: foreign and missing profiles are indistinguishable.
    if user_id != principal.user_id:
        raise ApiError(404, "resource_not_found", "Resource not found")
    profile = gateway.get_profile(user_id)
    if profile is None:
        raise ApiError(404, "resource_not_found", "Resource not found")
    return profile_response(profile)
