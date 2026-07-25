from collections.abc import Mapping
from typing import Any, Protocol

from fastapi import Depends

from app.core.auth import Principal, get_current_principal
from app.core.config import Settings, get_settings
from app.core.errors import ApiError


DEFAULT_PROFILE = {"currency_code": "CLP", "decimal_scale": 0}
CURRENCY_SCALES = {"CLP": 0, "USD": 2, "EUR": 2}

# Every table that belongs to a user's exported account snapshot. Kept as a
# module constant so InMemorySupabaseGateway and SupabaseGateway return the
# same key set (test-fixture parity).
EXPORT_TABLES = (
    "categories",
    "income_entries",
    "expense_entries",
    "budget_periods",
    "debts",
    "debt_installments",
    "alert_rules",
)


class FinanceGateway(Protocol):
    def get_profile(self, user_id: str) -> dict[str, Any] | None: ...
    def ensure_profile(self, user_id: str) -> dict[str, Any]: ...
    def update_profile(self, user_id: str, currency_code: str) -> dict[str, Any]: ...
    def export_account(self, user_id: str) -> dict[str, Any]: ...
    def delete_account(self, user_id: str) -> None: ...


def count_exported_rows(exported: dict[str, Any]) -> int:
    """Row count for an already-fetched export payload.

    Deliberately operates on data already in hand rather than issuing a
    separate count query: the installed supabase-py/postgrest version
    (2.31.0) does not expose a count-only/head request via `.select()`
    (its `count` kwarg is hardcoded to `None` at that call site), so a true
    pre-fetch count would require a second full data fetch anyway. Callers
    fetch once via `export_account` and enforce the limit on the result.
    """
    return sum(len(value) if isinstance(value, list) else 1 for value in exported.values())


class InMemorySupabaseGateway:
    """Test-only gateway with the same ownership semantics as RLS-backed storage."""

    def __init__(self):
        self._profiles: dict[str, dict[str, Any]] = {}

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        profile = self._profiles.get(user_id)
        return dict(profile) if profile else None

    def ensure_profile(self, user_id: str) -> dict[str, Any]:
        self._profiles.setdefault(user_id, {"user_id": user_id, **DEFAULT_PROFILE})
        return self.get_profile(user_id)  # type: ignore[return-value]

    def update_profile(self, user_id: str, currency_code: str) -> dict[str, Any]:
        profile = self.ensure_profile(user_id)
        profile.update(currency_code=currency_code, decimal_scale=CURRENCY_SCALES[currency_code])
        self._profiles[user_id] = profile
        return self.get_profile(user_id)  # type: ignore[return-value]

    def export_account(self, user_id: str) -> dict[str, Any]:
        profile = self.ensure_profile(user_id)
        return {"profile": profile, **{table: [] for table in EXPORT_TABLES}}

    def delete_account(self, user_id: str) -> None:
        self._profiles.pop(user_id, None)


class SupabaseGateway:
    """Request-scoped Supabase client carrying exactly the verified user JWT."""

    def __init__(self, settings: Settings, access_token: str):
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise ApiError(503, "backend_not_configured", "Supabase is not configured")
        from supabase import create_client

        self._settings = settings
        self.client = create_client(settings.supabase_url, settings.supabase_anon_key)
        self.client.postgrest.auth(access_token)

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        response = self.client.table("profiles").select("user_id,currency_code,decimal_scale").eq("user_id", user_id).maybe_single().execute()
        return response.data

    def ensure_profile(self, user_id: str) -> dict[str, Any]:
        response = self.client.table("profiles").upsert({"user_id": user_id}, on_conflict="user_id").execute()
        return response.data[0]

    def update_profile(self, user_id: str, currency_code: str) -> dict[str, Any]:
        response = self.client.table("profiles").update({"currency_code": currency_code, "decimal_scale": CURRENCY_SCALES[currency_code]}).eq("user_id", user_id).execute()
        return response.data[0]

    def export_account(self, user_id: str) -> dict[str, Any]:
        profile = self.ensure_profile(user_id)
        exported = {"profile": profile}
        for table in EXPORT_TABLES:
            exported[table] = self.client.table(table).select("*").execute().data
        return exported

    def delete_account(self, user_id: str) -> None:
        # Fail closed BEFORE deleting anything: if the service-role key is
        # missing, deleting finance data first and only then discovering we
        # can't remove the auth.users row would leave the account in exactly
        # the "resurrectable" state this method exists to prevent (data
        # gone, JWT still valid, ensure_profile recreates an empty profile).
        if not self._settings.supabase_service_role_key:
            raise ApiError(
                503,
                "account_deletion_not_configured",
                "Account deletion is not fully configured",
            )

        # 1. Remove the user's own finance data (and profile row) under RLS,
        #    using the caller's own JWT. `delete_my_account()` cascades from
        #    `profiles` to every finance table via ON DELETE CASCADE.
        self.client.rpc("delete_my_account").execute()

        # 2. Remove the `auth.users` row so the same still-valid JWT cannot
        #    call `ensure_profile` again and silently recreate an empty
        #    profile. This requires elevated privileges the anon-key + user
        #    JWT client never has, so a short-lived service-role client is
        #    constructed fresh here — never reused, never stored on self —
        #    since account deletion is the one operation that needs it.
        # Every other method on this class must keep using the anon-key +
        # user-JWT client so RLS stays the enforcement boundary.
        from supabase import create_client

        admin_client = create_client(self._settings.supabase_url, self._settings.supabase_service_role_key)
        admin_client.auth.admin.delete_user(user_id)


async def get_gateway(principal: Principal = Depends(get_current_principal), settings: Settings = Depends(get_settings)) -> FinanceGateway:
    return SupabaseGateway(settings, principal.access_token)
