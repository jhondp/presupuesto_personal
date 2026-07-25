from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.core.auth import Principal, get_current_principal
from app.core.errors import ApiError
from app.repositories.supabase import FinanceGateway, get_gateway

router = APIRouter(prefix="/categories", tags=["categories"])


class CreateCategoryRequest(BaseModel):
    name: str
    kind: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= 100):
            raise ValueError("name must be between 1 and 100 characters")
        return trimmed

    @field_validator("kind")
    @classmethod
    def kind_supported(cls, value: str) -> str:
        if value not in ("income", "expense"):
            raise ValueError("kind must be 'income' or 'expense'")
        return value


class CategoryResponse(BaseModel):
    id: str
    name: str
    kind: str
    status: str


def _response(category: dict) -> CategoryResponse:
    return CategoryResponse(id=category["id"], name=category["name"], kind=category["kind"], status=category["status"])


@router.post("", response_model=CategoryResponse, status_code=201)
async def create_category(
    body: CreateCategoryRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> CategoryResponse:
    return _response(gateway.create_category(principal.user_id, body.name, body.kind))


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> list[CategoryResponse]:
    return [_response(category) for category in gateway.list_categories(principal.user_id)]


@router.post("/{category_id}/archive", response_model=CategoryResponse)
async def archive_category(
    category_id: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> CategoryResponse:
    # Owner-only by construction: archive_category filters by user_id and
    # returns None for a missing OR foreign category, so both cases produce
    # the same 404 (no existence disclosure), matching the profile routes'
    # pattern.
    archived = gateway.archive_category(principal.user_id, category_id)
    if archived is None:
        raise ApiError(404, "resource_not_found", "Resource not found")
    return _response(archived)
