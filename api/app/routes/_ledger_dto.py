"""Shared DTOs for the income and expense ledger routes.

Both ledgers store identical fields (category, date, amount, optional note)
in separate tables (see design.md's "Ledger model" decision). Sharing these
Pydantic models keeps validation and response shape identical for
`routes/income.py` and `routes/expenses.py` instead of duplicating them.
"""

from datetime import date

from pydantic import BaseModel, Field


class LedgerEntryRequest(BaseModel):
    category_id: str
    occurred_on: date
    amount_minor: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=1000)


class LedgerEntryUpdateRequest(BaseModel):
    category_id: str | None = None
    occurred_on: date | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=1000)


class LedgerEntryResponse(BaseModel):
    id: str
    category_id: str
    period_id: str
    occurred_on: date
    amount_minor: int
    note: str | None = None


def ledger_entry_response(entry: dict) -> LedgerEntryResponse:
    return LedgerEntryResponse(
        id=entry["id"],
        category_id=entry["category_id"],
        period_id=entry["period_id"],
        occurred_on=entry["occurred_on"],
        amount_minor=entry["amount_minor"],
        note=entry.get("note"),
    )
