"""Factory for the income/expense ledger routers.

`routes/income.py` and `routes/expenses.py` are identical except for the
target table and category kind, so the actual route logic (period
resolution, category ownership/kind/status checks, closed-period rejection)
lives here once and both thin modules just call `build_ledger_router`.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.core.auth import Principal, get_current_principal
from app.core.errors import ApiError
from app.domain.periods import PeriodConflictError, assert_period_writable, resolve_open_period
from app.repositories.supabase import FinanceGateway, get_gateway
from app.routes._ledger_dto import LedgerEntryRequest, LedgerEntryResponse, LedgerEntryUpdateRequest, ledger_entry_response

_ERROR_STATUS = {"no_open_period": 422, "period_closed": 409}


def _raise(error: PeriodConflictError) -> None:
    raise ApiError(_ERROR_STATUS.get(error.code, 409), error.code, error.message)


def _validate_category_for_write(gateway: FinanceGateway, user_id: str, category_id: str, kind: str) -> None:
    category = gateway.get_category(user_id, category_id)
    if category is None:
        # Owner-only categories: missing and foreign both 404, no disclosure.
        raise ApiError(404, "resource_not_found", "Resource not found")
    if category["kind"] != kind:
        raise ApiError(
            422, "category_kind_mismatch", "Category kind does not match this ledger", {"category_id": "kind_mismatch"}
        )
    if category["status"] != "active":
        raise ApiError(
            422, "category_not_assignable", "Archived categories cannot be assigned to new entries", {"category_id": "archived"}
        )


def build_ledger_router(*, kind: str, table: str, prefix: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[kind])

    @router.post("", response_model=LedgerEntryResponse, status_code=201)
    async def create_entry(
        body: LedgerEntryRequest,
        principal: Annotated[Principal, Depends(get_current_principal)],
        gateway: Annotated[FinanceGateway, Depends(get_gateway)],
    ) -> LedgerEntryResponse:
        _validate_category_for_write(gateway, principal.user_id, body.category_id, kind)
        try:
            period = resolve_open_period(gateway.list_periods(principal.user_id), body.occurred_on)
        except PeriodConflictError as error:
            _raise(error)
        entry = gateway.create_entry(
            principal.user_id, table, body.category_id, period["id"], body.occurred_on, body.amount_minor, body.note
        )
        return ledger_entry_response(entry)

    @router.get("", response_model=list[LedgerEntryResponse])
    async def list_entries(
        principal: Annotated[Principal, Depends(get_current_principal)],
        gateway: Annotated[FinanceGateway, Depends(get_gateway)],
        period_id: Annotated[str | None, Query()] = None,
    ) -> list[LedgerEntryResponse]:
        return [ledger_entry_response(entry) for entry in gateway.list_entries(principal.user_id, table, period_id)]

    @router.put("/{entry_id}", response_model=LedgerEntryResponse)
    async def update_entry(
        entry_id: str,
        body: LedgerEntryUpdateRequest,
        principal: Annotated[Principal, Depends(get_current_principal)],
        gateway: Annotated[FinanceGateway, Depends(get_gateway)],
    ) -> LedgerEntryResponse:
        entry = gateway.get_entry(principal.user_id, table, entry_id)
        if entry is None:
            raise ApiError(404, "resource_not_found", "Resource not found")

        period = gateway.get_period(principal.user_id, entry["period_id"])
        if period is not None:
            try:
                assert_period_writable(period)
            except PeriodConflictError as error:
                _raise(error)

        # Only fields explicitly present in the request body are applied —
        # `model_fields_set` (not an `is not None` check) is what lets a
        # caller send `"note": null` to clear it, distinct from omitting
        # `note` entirely to leave it unchanged.
        provided = body.model_fields_set
        fields: dict[str, Any] = {}

        if "category_id" in provided:
            _validate_category_for_write(gateway, principal.user_id, body.category_id, kind)
            fields["category_id"] = body.category_id

        if "occurred_on" in provided:
            # Changing the date can move the entry into a different period
            # (or a closed one) — re-resolve and re-validate exactly like
            # create_entry does, rather than trusting the entry's existing
            # period_id to still be correct.
            try:
                new_period = resolve_open_period(gateway.list_periods(principal.user_id), body.occurred_on)
            except PeriodConflictError as error:
                _raise(error)
            fields["occurred_on"] = body.occurred_on
            fields["period_id"] = new_period["id"]

        if "amount_minor" in provided:
            fields["amount_minor"] = body.amount_minor

        if "note" in provided:
            fields["note"] = body.note

        updated = gateway.update_entry(principal.user_id, table, entry_id, fields)
        if updated is None:
            raise ApiError(404, "resource_not_found", "Resource not found")
        return ledger_entry_response(updated)

    return router
