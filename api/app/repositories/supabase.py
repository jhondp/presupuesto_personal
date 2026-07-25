from collections.abc import Mapping
from datetime import date
from typing import Any, Protocol

from fastapi import Depends

from app.core.auth import Principal, get_current_principal
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.domain.debts import DebtScheduleError, build_schedule
from app.domain.periods import PeriodConflictError


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

    # Categories
    def create_category(self, user_id: str, name: str, kind: str) -> dict[str, Any]: ...
    def list_categories(self, user_id: str) -> list[dict[str, Any]]: ...
    def get_category(self, user_id: str, category_id: str) -> dict[str, Any] | None: ...
    def archive_category(self, user_id: str, category_id: str) -> dict[str, Any] | None: ...

    # Budget periods
    def create_period(self, user_id: str, starts_on: date, ends_on: date) -> dict[str, Any]: ...
    def list_periods(self, user_id: str) -> list[dict[str, Any]]: ...
    def get_period(self, user_id: str, period_id: str) -> dict[str, Any] | None: ...
    def close_period(self, user_id: str, period_id: str, expected_version: int) -> dict[str, Any] | None: ...
    def reopen_period(self, user_id: str, period_id: str, expected_version: int) -> dict[str, Any] | None: ...

    # Ledger entries (shared by income_entries and expense_entries)
    def create_entry(
        self, user_id: str, table: str, category_id: str, period_id: str, occurred_on: date, amount_minor: int, note: str | None
    ) -> dict[str, Any]: ...
    def list_entries(self, user_id: str, table: str, period_id: str | None = None) -> list[dict[str, Any]]: ...
    def get_entry(self, user_id: str, table: str, entry_id: str) -> dict[str, Any] | None: ...
    def update_entry(self, user_id: str, table: str, entry_id: str, fields: dict[str, Any]) -> dict[str, Any] | None: ...

    # Debts
    def create_debt(
        self, user_id: str, bank: str, principal_minor: int, installment_minor: int, installment_count: int
    ) -> dict[str, Any]: ...
    def list_debts(self, user_id: str) -> list[dict[str, Any]]: ...
    def get_debt(self, user_id: str, debt_id: str) -> dict[str, Any] | None: ...
    def generate_debt_schedule(self, user_id: str, debt_id: str) -> list[dict[str, Any]] | None: ...


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
        self._categories: dict[str, dict[str, Any]] = {}
        self._periods: dict[str, dict[str, Any]] = {}
        self._period_events: list[dict[str, Any]] = []
        self._entries: dict[str, dict[str, dict[str, Any]]] = {"income_entries": {}, "expense_entries": {}}
        self._debts: dict[str, dict[str, Any]] = {}
        self._installments: dict[str, dict[str, Any]] = {}
        self._installments_by_key: dict[tuple[str, int], str] = {}
        self._next_id = 0

    def _new_id(self) -> str:
        # Sequential ids (not real UUIDs) are enough for a test-only gateway
        # and keep failures easy to read/diff.
        self._next_id += 1
        return f"id-{self._next_id}"

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
        return {
            "profile": profile,
            "categories": self.list_categories(user_id),
            "income_entries": self.list_entries(user_id, "income_entries"),
            "expense_entries": self.list_entries(user_id, "expense_entries"),
            "budget_periods": self.list_periods(user_id),
            "debts": self.list_debts(user_id),
            "debt_installments": self._list_installments(user_id),
            # alert_rules lands in PR3B; kept here (empty) so the export key
            # set matches EXPORT_TABLES.
            "alert_rules": [],
        }

    def delete_account(self, user_id: str) -> None:
        self._profiles.pop(user_id, None)
        self._categories = {cid: c for cid, c in self._categories.items() if c["user_id"] != user_id}
        self._periods = {pid: p for pid, p in self._periods.items() if p["user_id"] != user_id}
        self._period_events = [e for e in self._period_events if e["user_id"] != user_id]
        for table in self._entries:
            self._entries[table] = {eid: e for eid, e in self._entries[table].items() if e["user_id"] != user_id}
        self._debts = {did: d for did, d in self._debts.items() if d["user_id"] != user_id}
        self._installments_by_key = {
            key: iid for key, iid in self._installments_by_key.items() if self._installments[iid]["user_id"] != user_id
        }
        self._installments = {iid: i for iid, i in self._installments.items() if i["user_id"] != user_id}

    # Categories

    def create_category(self, user_id: str, name: str, kind: str) -> dict[str, Any]:
        category = {"id": self._new_id(), "user_id": user_id, "name": name, "kind": kind, "status": "active"}
        self._categories[category["id"]] = category
        return dict(category)

    def list_categories(self, user_id: str) -> list[dict[str, Any]]:
        return [dict(c) for c in self._categories.values() if c["user_id"] == user_id]

    def get_category(self, user_id: str, category_id: str) -> dict[str, Any] | None:
        category = self._categories.get(category_id)
        return dict(category) if category and category["user_id"] == user_id else None

    def archive_category(self, user_id: str, category_id: str) -> dict[str, Any] | None:
        category = self._categories.get(category_id)
        if category is None or category["user_id"] != user_id:
            return None
        category["status"] = "archived"
        return dict(category)

    # Budget periods

    def create_period(self, user_id: str, starts_on: date, ends_on: date) -> dict[str, Any]:
        period = {"id": self._new_id(), "user_id": user_id, "starts_on": starts_on, "ends_on": ends_on, "status": "open", "version": 1}
        self._periods[period["id"]] = period
        return dict(period)

    def list_periods(self, user_id: str) -> list[dict[str, Any]]:
        return [dict(p) for p in self._periods.values() if p["user_id"] == user_id]

    def get_period(self, user_id: str, period_id: str) -> dict[str, Any] | None:
        period = self._periods.get(period_id)
        return dict(period) if period and period["user_id"] == user_id else None

    def close_period(self, user_id: str, period_id: str, expected_version: int) -> dict[str, Any] | None:
        return self._transition_period(user_id, period_id, expected_version, required_status="open", target_status="closed", event_type="closed")

    def reopen_period(self, user_id: str, period_id: str, expected_version: int) -> dict[str, Any] | None:
        return self._transition_period(user_id, period_id, expected_version, required_status="closed", target_status="open", event_type="reopened")

    def _transition_period(
        self, user_id: str, period_id: str, expected_version: int, *, required_status: str, target_status: str, event_type: str
    ) -> dict[str, Any] | None:
        # Mirrors the atomic check-then-write the real close_period/reopen_period
        # SQL RPCs perform (see supabase/migrations/0004_period_lifecycle.sql):
        # ownership, current status, and version are all re-checked here
        # rather than trusting the caller's earlier read.
        period = self._periods.get(period_id)
        if period is None or period["user_id"] != user_id:
            return None
        if period["status"] != required_status or period["version"] != expected_version:
            return None
        period["status"] = target_status
        period["version"] += 1
        self._period_events.append(
            {
                "id": self._new_id(),
                "user_id": user_id,
                "period_id": period_id,
                "event_type": event_type,
                "from_version": expected_version,
                "to_version": period["version"],
            }
        )
        return dict(period)

    # Ledger entries (shared by income_entries and expense_entries)

    def create_entry(
        self, user_id: str, table: str, category_id: str, period_id: str, occurred_on: date, amount_minor: int, note: str | None
    ) -> dict[str, Any]:
        entry = {
            "id": self._new_id(),
            "user_id": user_id,
            "category_id": category_id,
            "period_id": period_id,
            "occurred_on": occurred_on,
            "amount_minor": amount_minor,
            "note": note,
        }
        self._entries[table][entry["id"]] = entry
        return dict(entry)

    def list_entries(self, user_id: str, table: str, period_id: str | None = None) -> list[dict[str, Any]]:
        entries = [dict(e) for e in self._entries[table].values() if e["user_id"] == user_id]
        if period_id is not None:
            entries = [e for e in entries if e["period_id"] == period_id]
        return entries

    def get_entry(self, user_id: str, table: str, entry_id: str) -> dict[str, Any] | None:
        entry = self._entries[table].get(entry_id)
        return dict(entry) if entry and entry["user_id"] == user_id else None

    def update_entry(self, user_id: str, table: str, entry_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        # `fields` already contains exactly the keys the caller intends to
        # change (see routes/_ledger_router.py's use of `model_fields_set`),
        # so every key here is applied as-is — including an explicit `None`
        # for `note`, which is how a caller clears it.
        entry = self._entries[table].get(entry_id)
        if entry is None or entry["user_id"] != user_id:
            return None
        entry.update(fields)
        return dict(entry)

    # Debts

    def create_debt(
        self, user_id: str, bank: str, principal_minor: int, installment_minor: int, installment_count: int
    ) -> dict[str, Any]:
        debt = {
            "id": self._new_id(),
            "user_id": user_id,
            "bank": bank,
            "principal_minor": principal_minor,
            "installment_minor": installment_minor,
            "installment_count": installment_count,
            # Mirrors `created_at::date` on the real (timestamptz) column —
            # only the date component is ever compared against.
            "created_on": date.today(),
        }
        self._debts[debt["id"]] = debt
        return dict(debt)

    def list_debts(self, user_id: str) -> list[dict[str, Any]]:
        return [dict(d) for d in self._debts.values() if d["user_id"] == user_id]

    def get_debt(self, user_id: str, debt_id: str) -> dict[str, Any] | None:
        debt = self._debts.get(debt_id)
        return dict(debt) if debt and debt["user_id"] == user_id else None

    def _list_installments(self, user_id: str) -> list[dict[str, Any]]:
        return sorted(
            (dict(i) for i in self._installments.values() if i["user_id"] == user_id),
            key=lambda i: (i["debt_id"], i["ordinal"]),
        )

    def generate_debt_schedule(self, user_id: str, debt_id: str) -> list[dict[str, Any]] | None:
        # Mirrors the SQL RPC's lock-then-resolve-then-insert-with-conflict-
        # skip shape: ownership is re-checked here rather than trusting an
        # earlier read, and an installment already present for (debt_id,
        # ordinal) is left untouched, which is what makes repeat calls
        # idempotent (see 0006_debt_schedule_and_alerts.sql).
        debt = self._debts.get(debt_id)
        if debt is None or debt["user_id"] != user_id:
            return None
        schedule = build_schedule(debt, self.list_periods(user_id))  # raises DebtScheduleError("no_later_period", ...)
        for item in schedule:
            key = (debt_id, item["ordinal"])
            if key in self._installments_by_key:
                continue
            installment = {
                "id": self._new_id(),
                "user_id": user_id,
                "debt_id": debt_id,
                "ordinal": item["ordinal"],
                "due_on": item["due_on"],
                "amount_minor": item["amount_minor"],
            }
            self._installments[installment["id"]] = installment
            self._installments_by_key[key] = installment["id"]
        return sorted(
            (dict(i) for i in self._installments.values() if i["debt_id"] == debt_id and i["user_id"] == user_id),
            key=lambda i: i["ordinal"],
        )


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

    # Categories

    def create_category(self, user_id: str, name: str, kind: str) -> dict[str, Any]:
        response = self.client.table("categories").insert({"user_id": user_id, "name": name, "kind": kind}).execute()
        return response.data[0]

    def list_categories(self, user_id: str) -> list[dict[str, Any]]:
        return self.client.table("categories").select("*").eq("user_id", user_id).execute().data

    def get_category(self, user_id: str, category_id: str) -> dict[str, Any] | None:
        response = self.client.table("categories").select("*").eq("id", category_id).eq("user_id", user_id).maybe_single().execute()
        return response.data

    def archive_category(self, user_id: str, category_id: str) -> dict[str, Any] | None:
        response = self.client.table("categories").update({"status": "archived"}).eq("id", category_id).eq("user_id", user_id).execute()
        return response.data[0] if response.data else None

    # Budget periods

    @staticmethod
    def _with_period_dates(row: dict[str, Any]) -> dict[str, Any]:
        # PostgREST returns dates as ISO strings; the domain layer (app.domain.periods)
        # compares them against `date.fromisoformat`-parsed request values, so
        # rows read back from Supabase must carry real `date` objects too.
        row = dict(row)
        for key in ("starts_on", "ends_on"):
            if isinstance(row.get(key), str):
                row[key] = date.fromisoformat(row[key])
        return row

    def create_period(self, user_id: str, starts_on: date, ends_on: date) -> dict[str, Any]:
        response = self.client.table("budget_periods").insert(
            {"user_id": user_id, "starts_on": starts_on.isoformat(), "ends_on": ends_on.isoformat()}
        ).execute()
        return self._with_period_dates(response.data[0])

    def list_periods(self, user_id: str) -> list[dict[str, Any]]:
        rows = self.client.table("budget_periods").select("*").eq("user_id", user_id).execute().data
        return [self._with_period_dates(row) for row in rows]

    def get_period(self, user_id: str, period_id: str) -> dict[str, Any] | None:
        response = self.client.table("budget_periods").select("*").eq("id", period_id).eq("user_id", user_id).maybe_single().execute()
        return self._with_period_dates(response.data) if response.data else None

    def close_period(self, user_id: str, period_id: str, expected_version: int) -> dict[str, Any] | None:
        return self._transition_period("close_period", period_id, expected_version)

    def reopen_period(self, user_id: str, period_id: str, expected_version: int) -> dict[str, Any] | None:
        return self._transition_period("reopen_period", period_id, expected_version)

    def _transition_period(self, rpc_name: str, period_id: str, expected_version: int) -> dict[str, Any] | None:
        # Close/reopen must update budget_periods AND append a period_events
        # row atomically, which a bare postgrest .update() call cannot
        # guarantee. `close_period`/`reopen_period` are transactional SQL
        # RPCs (supabase/migrations/0004_period_lifecycle.sql) that re-check
        # ownership, current status, and version themselves, so a stale or
        # cross-owner request is rejected there even if the caller's earlier
        # read was correct at the time.
        from postgrest.exceptions import APIError

        try:
            response = self.client.rpc(rpc_name, {"p_period_id": period_id, "p_expected_version": expected_version}).execute()
        except APIError as exc:
            # Match the RPCs' exact `raise exception '...'` messages (see
            # 0004_period_lifecycle.sql) rather than loose substrings, so an
            # unrelated failure (permissions, network, an unexpected RPC
            # error) re-raises instead of being mislabeled as a stale-version
            # conflict — a caller reading the response, or a maintainer
            # reading logs, would otherwise be told the wrong thing happened.
            message = str(getattr(exc, "message", "") or exc)
            if "period_not_found" in message:
                return None
            if "period_already_closed" in message or "period_already_open" in message:
                raise PeriodConflictError("invalid_transition", "This period cannot make that transition") from exc
            if "version_conflict" in message:
                raise PeriodConflictError("version_conflict", "The period was modified by another request") from exc
            raise
        data = response.data
        row = data[0] if isinstance(data, list) else data
        return self._with_period_dates(row) if row else None

    # Ledger entries (shared by income_entries and expense_entries)

    def create_entry(
        self, user_id: str, table: str, category_id: str, period_id: str, occurred_on: date, amount_minor: int, note: str | None
    ) -> dict[str, Any]:
        payload = {
            "user_id": user_id,
            "category_id": category_id,
            "period_id": period_id,
            "occurred_on": occurred_on.isoformat(),
            "amount_minor": amount_minor,
            "note": note,
        }
        response = self.client.table(table).insert(payload).execute()
        return response.data[0]

    def list_entries(self, user_id: str, table: str, period_id: str | None = None) -> list[dict[str, Any]]:
        query = self.client.table(table).select("*").eq("user_id", user_id)
        if period_id is not None:
            query = query.eq("period_id", period_id)
        return query.execute().data

    def get_entry(self, user_id: str, table: str, entry_id: str) -> dict[str, Any] | None:
        response = self.client.table(table).select("*").eq("id", entry_id).eq("user_id", user_id).maybe_single().execute()
        return response.data

    def update_entry(self, user_id: str, table: str, entry_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        # `fields` already contains exactly the keys the caller intends to
        # change (see routes/_ledger_router.py's use of `model_fields_set`),
        # so every key is sent as-is — including an explicit `None` for
        # `note`, which is how a caller clears it.
        updates = {key: (value.isoformat() if key == "occurred_on" and value is not None else value) for key, value in fields.items()}
        response = self.client.table(table).update(updates).eq("id", entry_id).eq("user_id", user_id).execute()
        return response.data[0] if response.data else None

    # Debts

    def create_debt(
        self, user_id: str, bank: str, principal_minor: int, installment_minor: int, installment_count: int
    ) -> dict[str, Any]:
        payload = {
            "user_id": user_id,
            "bank": bank,
            "principal_minor": principal_minor,
            "installment_minor": installment_minor,
            "installment_count": installment_count,
        }
        response = self.client.table("debts").insert(payload).execute()
        return response.data[0]

    def list_debts(self, user_id: str) -> list[dict[str, Any]]:
        return self.client.table("debts").select("*").eq("user_id", user_id).execute().data

    def get_debt(self, user_id: str, debt_id: str) -> dict[str, Any] | None:
        response = self.client.table("debts").select("*").eq("id", debt_id).eq("user_id", user_id).maybe_single().execute()
        return response.data

    @staticmethod
    def _with_installment_date(row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        if isinstance(row.get("due_on"), str):
            row["due_on"] = date.fromisoformat(row["due_on"])
        return row

    def generate_debt_schedule(self, user_id: str, debt_id: str) -> list[dict[str, Any]] | None:
        # generate_debt_schedule (0006_debt_schedule_and_alerts.sql) is the
        # server-authoritative, `security invoker`, row-locked schedule
        # generator; this method only maps its exact `raise exception '...'`
        # messages to the domain-layer errors/None the routes expect —
        # mirrors _transition_period's exact-message matching above.
        from postgrest.exceptions import APIError

        try:
            response = self.client.rpc("generate_debt_schedule", {"p_debt_id": debt_id}).execute()
        except APIError as exc:
            message = str(getattr(exc, "message", "") or exc)
            if "debt_not_found" in message:
                return None
            if "no_later_period" in message:
                raise DebtScheduleError("no_later_period", "No later budget period exists to anchor the schedule") from exc
            raise
        data = response.data or []
        return [self._with_installment_date(row) for row in data]


async def get_gateway(principal: Principal = Depends(get_current_principal), settings: Settings = Depends(get_settings)) -> FinanceGateway:
    return SupabaseGateway(settings, principal.access_token)
