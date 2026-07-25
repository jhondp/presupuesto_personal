"""Opt-in disposable Supabase RLS test; never runs against an unmarked project."""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

import pytest
import httpx

sys_path = str(Path(__file__).resolve().parents[2])
import sys
sys.path.insert(0, sys_path)

from app.main import create_app

REQUIRED_ENVIRONMENT = (
    "SUPABASE_TEST_URL",
    "SUPABASE_TEST_ANON_KEY",
    "SUPABASE_TEST_SERVICE_ROLE_KEY",
    "SUPABASE_TEST_JWT_SECRET",
)


def _require_disposable_harness() -> dict[str, str]:
    missing = [name for name in REQUIRED_ENVIRONMENT if not os.getenv(name)]
    if os.getenv("SUPABASE_TEST_ALLOW_DESTRUCTIVE") != "true" or missing:
        pytest.skip(
            "Disposable Supabase RLS harness unavailable: set "
            "SUPABASE_TEST_ALLOW_DESTRUCTIVE=true and " + ", ".join(REQUIRED_ENVIRONMENT)
        )
    return {name: os.environ[name] for name in REQUIRED_ENVIRONMENT}


def _token_for(user_id: str, secret: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user_id, "role": "authenticated", "exp": int(time.time()) + 300}).encode()).rstrip(b"=")
    signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), header + b"." + payload, hashlib.sha256).digest()).rstrip(b"=")
    return b".".join((header, payload, signature)).decode()


def _user_client(url: str, anon_key: str, token: str):
    from supabase import create_client

    client = create_client(url, anon_key)
    client.postgrest.auth(token)
    return client


@pytest.mark.anyio
async def test_rls_isolates_two_users_and_api_export_deletion(monkeypatch):
    env = _require_disposable_harness()
    from supabase import create_client

    admin = create_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_SERVICE_ROLE_KEY"])
    suffix = uuid.uuid4().hex
    users = []
    try:
        for label in ("a", "b"):
            result = admin.auth.admin.create_user(
                {"email": f"rls-{label}-{suffix}@example.test", "password": uuid.uuid4().hex, "email_confirm": True}
            )
            users.append(str(result.user.id))
        user_a, user_b = users
        token_a = _token_for(user_a, env["SUPABASE_TEST_JWT_SECRET"])
        token_b = _token_for(user_b, env["SUPABASE_TEST_JWT_SECRET"])
        db_a = _user_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_ANON_KEY"], token_a)
        db_b = _user_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_ANON_KEY"], token_b)
        db_a.table("profiles").upsert({"user_id": user_a}).execute()
        db_b.table("profiles").upsert({"user_id": user_b}).execute()

        assert db_b.table("profiles").select("user_id").eq("user_id", user_a).execute().data == []

        monkeypatch.setenv("SUPABASE_URL", env["SUPABASE_TEST_URL"])
        monkeypatch.setenv("SUPABASE_ANON_KEY", env["SUPABASE_TEST_ANON_KEY"])
        monkeypatch.setenv("SUPABASE_JWT_SECRET", env["SUPABASE_TEST_JWT_SECRET"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as http:
            exported = await http.get("/v1/account/export", headers={"Authorization": f"Bearer {token_a}"})
            assert exported.status_code == 200
            assert exported.json()["profile"]["user_id"] == user_a
            assert user_b not in json.dumps(exported.json())
            assert (await http.delete("/v1/account", headers={"Authorization": f"Bearer {token_a}"})).status_code == 204

        assert db_b.table("profiles").select("user_id").eq("user_id", user_b).execute().data == [{"user_id": user_b}]
    finally:
        for user_id in users:
            try:
                admin.auth.admin.delete_user(user_id)
            except Exception:
                pass


@pytest.mark.anyio
async def test_expense_entries_and_composite_ownership_fks_and_full_export(monkeypatch):
    """PR1 hardening: expense_entries has the same FK/ownership rules as
    income_entries, a cross-owner category/period reference is rejected by
    the composite FK, and export includes debt_installments/alert_rules."""
    from postgrest.exceptions import APIError

    env = _require_disposable_harness()
    from supabase import create_client

    admin = create_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_SERVICE_ROLE_KEY"])
    suffix = uuid.uuid4().hex
    users = []
    try:
        for label in ("a", "b"):
            result = admin.auth.admin.create_user(
                {"email": f"rls-fk-{label}-{suffix}@example.test", "password": uuid.uuid4().hex, "email_confirm": True}
            )
            users.append(str(result.user.id))
        user_a, user_b = users
        token_a = _token_for(user_a, env["SUPABASE_TEST_JWT_SECRET"])
        db_a = _user_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_ANON_KEY"], token_a)
        token_b = _token_for(user_b, env["SUPABASE_TEST_JWT_SECRET"])
        db_b = _user_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_ANON_KEY"], token_b)
        db_a.table("profiles").upsert({"user_id": user_a}).execute()
        db_b.table("profiles").upsert({"user_id": user_b}).execute()

        category_a = db_a.table("categories").insert(
            {"user_id": user_a, "name": "Salary", "kind": "income"}
        ).execute().data[0]
        period_a = db_a.table("budget_periods").insert(
            {"user_id": user_a, "starts_on": "2026-01-01", "ends_on": "2026-01-31"}
        ).execute().data[0]

        # Own-owner income and expense entries behave identically: both accept
        # a same-owner category/period reference (expense_entries previously
        # had no FK at all after `LIKE ... INCLUDING ALL`).
        income = db_a.table("income_entries").insert(
            {
                "user_id": user_a,
                "category_id": category_a["id"],
                "period_id": period_a["id"],
                "amount_minor": 100_000,
                "occurred_on": "2026-01-05",
            }
        ).execute().data[0]
        expense = db_a.table("expense_entries").insert(
            {
                "user_id": user_a,
                "category_id": category_a["id"],
                "period_id": period_a["id"],
                "amount_minor": 50_000,
                "occurred_on": "2026-01-06",
            }
        ).execute().data[0]
        assert income["category_id"] == category_a["id"]
        assert expense["category_id"] == category_a["id"]

        # Cross-owner attempt: user A's entry tries to reference user B's
        # category. The plain FK would only check the category exists; the
        # composite (user_id, category_id) FK must reject this.
        category_b = db_b.table("categories").insert(
            {"user_id": user_b, "name": "Salary", "kind": "income"}
        ).execute().data[0]
        with pytest.raises(APIError):
            db_a.table("income_entries").insert(
                {
                    "user_id": user_a,
                    "category_id": category_b["id"],
                    "amount_minor": 1_000,
                    "occurred_on": "2026-01-07",
                }
            ).execute()
        with pytest.raises(APIError):
            db_a.table("expense_entries").insert(
                {
                    "user_id": user_a,
                    "category_id": category_b["id"],
                    "amount_minor": 1_000,
                    "occurred_on": "2026-01-07",
                }
            ).execute()

        debt = db_a.table("debts").insert(
            {"user_id": user_a, "bank": "Bank A", "principal_minor": 1_000_000, "installment_minor": 100_000, "installment_count": 10}
        ).execute().data[0]
        db_a.table("debt_installments").insert(
            {"user_id": user_a, "debt_id": debt["id"], "ordinal": 1, "due_on": "2026-02-01", "amount_minor": 100_000}
        ).execute()
        db_a.table("alert_rules").insert({"user_id": user_a, "threshold_minor": 500_000}).execute()

        # Cross-owner debt_installments must be rejected the same way.
        debt_b = db_b.table("debts").insert(
            {"user_id": user_b, "bank": "Bank B", "principal_minor": 1_000_000, "installment_minor": 100_000, "installment_count": 10}
        ).execute().data[0]
        with pytest.raises(APIError):
            db_a.table("debt_installments").insert(
                {"user_id": user_a, "debt_id": debt_b["id"], "ordinal": 1, "due_on": "2026-02-01", "amount_minor": 100_000}
            ).execute()

        monkeypatch.setenv("SUPABASE_URL", env["SUPABASE_TEST_URL"])
        monkeypatch.setenv("SUPABASE_ANON_KEY", env["SUPABASE_TEST_ANON_KEY"])
        monkeypatch.setenv("SUPABASE_JWT_SECRET", env["SUPABASE_TEST_JWT_SECRET"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as http:
            exported = await http.get("/v1/account/export", headers={"Authorization": f"Bearer {token_a}"})
            assert exported.status_code == 200
            body = exported.json()
            assert {"debt_installments", "alert_rules"}.issubset(body.keys())
            assert len(body["debt_installments"]) == 1
            assert len(body["alert_rules"]) == 1
            assert len(body["income_entries"]) == 1
            assert len(body["expense_entries"]) == 1
    finally:
        for user_id in users:
            try:
                admin.auth.admin.delete_user(user_id)
            except Exception:
                pass


class _FakeAuthAdmin:
    def __init__(self) -> None:
        self.deleted_user_ids: list[str] = []

    def delete_user(self, user_id: str) -> None:
        self.deleted_user_ids.append(user_id)


class _FakeAuth:
    def __init__(self) -> None:
        self.admin = _FakeAuthAdmin()


class _FakePostgrest:
    def auth(self, token: str) -> None:
        self.token = token


class _FakeRpcBuilder:
    def __init__(self, calls: list[str], name: str) -> None:
        self._calls = calls
        self._name = name

    def execute(self):
        self._calls.append(self._name)
        return None


class _FakeSupabaseClient:
    """Mirrors the same mocking style as the FastAPI dependency overrides used
    in test_profile.py, but at the supabase-py client boundary instead."""

    def __init__(self, url: str, key: str) -> None:
        self.url = url
        self.key = key
        self.postgrest = _FakePostgrest()
        self.auth = _FakeAuth()
        self.rpc_calls: list[str] = []

    def rpc(self, name: str) -> _FakeRpcBuilder:
        return _FakeRpcBuilder(self.rpc_calls, name)


def test_delete_account_removes_auth_user_via_short_lived_service_role_client(monkeypatch):
    """Unit-level: hitting real Supabase auth admin isn't feasible in this
    test environment, so the raw supabase-py client is mocked (there is no
    existing lower-level fixture in this suite to reuse)."""
    from app.core.config import Settings
    from app.repositories.supabase import SupabaseGateway

    created_clients: list[_FakeSupabaseClient] = []

    def fake_create_client(url: str, key: str) -> _FakeSupabaseClient:
        client = _FakeSupabaseClient(url, key)
        created_clients.append(client)
        return client

    monkeypatch.setattr("supabase.create_client", fake_create_client)

    settings = Settings(
        supabase_url="https://example.test",
        supabase_anon_key="anon-key",
        supabase_service_role_key="service-role-key",
    )
    gateway = SupabaseGateway(settings, access_token="user-jwt")
    gateway.delete_account("user-123")

    assert len(created_clients) == 2
    anon_client, admin_client = created_clients
    assert anon_client.key == "anon-key"
    assert anon_client.rpc_calls == ["delete_my_account"]
    assert admin_client.key == "service-role-key"
    assert admin_client.auth.admin.deleted_user_ids == ["user-123"]
    # The elevated client is never reused as the gateway's own client, so
    # every other method keeps using the anon-key + user-JWT client for RLS.
    assert gateway.client is anon_client
    assert gateway.client is not admin_client


def test_delete_account_without_service_role_key_fails_closed(monkeypatch):
    """Must fail BEFORE deleting anything: if finance data were deleted
    first and the auth-user removal skipped afterward, the account would
    be left in exactly the "resurrectable" state this method exists to
    prevent (data gone, JWT still valid, ensure_profile recreates it)."""
    from app.core.config import Settings
    from app.core.errors import ApiError
    from app.repositories.supabase import SupabaseGateway

    created_clients: list[_FakeSupabaseClient] = []

    def fake_create_client(url: str, key: str) -> _FakeSupabaseClient:
        client = _FakeSupabaseClient(url, key)
        created_clients.append(client)
        return client

    monkeypatch.setattr("supabase.create_client", fake_create_client)

    settings = Settings(supabase_url="https://example.test", supabase_anon_key="anon-key")
    gateway = SupabaseGateway(settings, access_token="user-jwt")

    with pytest.raises(ApiError) as exc_info:
        gateway.delete_account("user-123")

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "account_deletion_not_configured"
    # `created_clients[0]` is the anon-key client built by SupabaseGateway.__init__
    # itself (unavoidable — it's the client for get/update/export). No finance
    # data was touched: the RPC must never run when deletion can't be
    # completed end-to-end, and no second (service-role) client is created.
    assert len(created_clients) == 1
    assert created_clients[0].rpc_calls == []
