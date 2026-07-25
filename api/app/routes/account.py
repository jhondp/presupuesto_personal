from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.core.auth import Principal, get_current_principal
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.repositories.supabase import FinanceGateway, count_exported_rows, get_gateway

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/export")
async def export_account(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    exported = gateway.export_account(principal.user_id)
    # Row-count enforcement is deliberately post-fetch: the installed
    # supabase-py/postgrest version has no count-only/head request, so a
    # true pre-fetch count would cost a second full data fetch anyway. See
    # count_exported_rows() for the full rationale.
    if count_exported_rows(exported) > settings.max_export_rows:
        raise ApiError(429, "usage_limit_reached", "Configured export limit reached")
    return exported


@router.delete("", status_code=204)
async def delete_account(
    principal: Annotated[Principal, Depends(get_current_principal)],
    gateway: Annotated[FinanceGateway, Depends(get_gateway)],
) -> Response:
    gateway.delete_account(principal.user_id)
    return Response(status_code=204)
