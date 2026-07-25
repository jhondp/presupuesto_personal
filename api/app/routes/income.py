from app.routes._ledger_router import build_ledger_router

router = build_ledger_router(kind="income", table="income_entries", prefix="/income")
