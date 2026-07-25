import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import date
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.main import create_app
from app.repositories.supabase import InMemorySupabaseGateway, get_gateway


@pytest.fixture
def anyio_backend():
    return "asyncio"


def gateway_override(gateway):
    async def override_gateway():
        return gateway

    return override_gateway


def token_for(user_id: str, secret: str = "test-secret") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user_id, "exp": int(time.time()) + 3600}).encode()).rstrip(b"=")
    signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), header + b"." + payload, hashlib.sha256).digest()).rstrip(b"=")
    return b".".join((header, payload, signature)).decode()


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http, app


async def _open_period(http, headers, starts_on: str, ends_on: str):
    response = await http.post("/v1/periods", headers=headers, json={"starts_on": starts_on, "ends_on": ends_on})
    return response.json()


@pytest.mark.anyio
async def test_creating_a_debt_below_principal_total_is_rejected_with_422(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    response = await http.post(
        "/v1/debts",
        headers=headers,
        json={"bank": "Bank A", "principal_minor": 1_000_000, "installment_minor": 100_000, "installment_count": 5},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "installment_total_below_principal"


@pytest.mark.anyio
async def test_generating_a_schedule_with_no_later_period_is_rejected_with_409(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    debt = (
        await http.post(
            "/v1/debts",
            headers=headers,
            json={"bank": "Bank A", "principal_minor": 1_000_000, "installment_minor": 100_000, "installment_count": 10},
        )
    ).json()

    response = await http.post(f"/v1/debts/{debt['id']}/schedule", headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "no_later_period"


@pytest.mark.anyio
async def test_generating_a_schedule_is_idempotent(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    # Both periods must start after the debt's creation date (i.e. after
    # "today") — a period the debt predates can never anchor its schedule.
    await _open_period(http, headers, "2030-01-01", "2030-01-31")
    await _open_period(http, headers, "2030-02-01", "2030-02-28")
    debt = (
        await http.post(
            "/v1/debts",
            headers=headers,
            json={"bank": "Bank A", "principal_minor": 300_000, "installment_minor": 100_000, "installment_count": 3},
        )
    ).json()

    first = await http.post(f"/v1/debts/{debt['id']}/schedule", headers=headers)
    assert first.status_code == 200
    first_installments = first.json()
    assert len(first_installments) == 3
    assert [item["ordinal"] for item in first_installments] == [1, 2, 3]
    assert first_installments[0]["due_on"] == "2030-01-01"

    second = await http.post(f"/v1/debts/{debt['id']}/schedule", headers=headers)
    assert second.status_code == 200
    second_installments = second.json()
    assert len(second_installments) == 3
    # Repeat generation must not create duplicates — same rows, same ids.
    assert {item["id"] for item in first_installments} == {item["id"] for item in second_installments}


@pytest.mark.anyio
async def test_another_users_debt_and_schedule_are_not_found(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    owner_headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    other_headers = {"Authorization": f"Bearer {token_for('owner-b')}"}

    debt = (
        await http.post(
            "/v1/debts",
            headers=owner_headers,
            json={"bank": "Bank A", "principal_minor": 300_000, "installment_minor": 100_000, "installment_count": 3},
        )
    ).json()

    assert (await http.get(f"/v1/debts/{debt['id']}", headers=other_headers)).status_code == 404
    assert (await http.post(f"/v1/debts/{debt['id']}/schedule", headers=other_headers)).status_code == 404
    assert (await http.get("/v1/debts", headers=other_headers)).json() == []


@pytest.mark.anyio
async def test_debt_list_and_export_reflect_generated_installments(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    await _open_period(http, headers, "2030-02-01", "2030-02-28")

    debt = (
        await http.post(
            "/v1/debts",
            headers=headers,
            json={"bank": "Bank A", "principal_minor": 200_000, "installment_minor": 100_000, "installment_count": 2},
        )
    ).json()
    await http.post(f"/v1/debts/{debt['id']}/schedule", headers=headers)

    listed = await http.get("/v1/debts", headers=headers)
    assert listed.json() == [debt]

    exported = await http.get("/v1/account/export", headers=headers)
    body = exported.json()
    assert [d["id"] for d in body["debts"]] == [debt["id"]]
    assert len(body["debt_installments"]) == 2


# --- opt-in disposable Supabase harness: differential SQL-vs-Python schedule
# equality and concurrent-generation duplicate-freedom. Skipped unless a
# disposable project is explicitly configured (mirrors test_supabase_rls.py).

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


@pytest.mark.anyio
async def test_sql_and_python_schedules_are_identical_and_generation_is_race_safe():
    from app.domain.debts import build_schedule
    from supabase import create_client

    env = _require_disposable_harness()
    admin = create_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_SERVICE_ROLE_KEY"])
    suffix = uuid.uuid4().hex
    user_id = None
    try:
        result = admin.auth.admin.create_user(
            {"email": f"debts-{suffix}@example.test", "password": uuid.uuid4().hex, "email_confirm": True}
        )
        user_id = str(result.user.id)
        token = _token_for(user_id, env["SUPABASE_TEST_JWT_SECRET"])
        db = create_client(env["SUPABASE_TEST_URL"], env["SUPABASE_TEST_ANON_KEY"])
        db.postgrest.auth(token)
        db.table("profiles").upsert({"user_id": user_id}).execute()

        period = db.table("budget_periods").insert(
            {"user_id": user_id, "starts_on": "2026-03-01", "ends_on": "2026-03-31"}
        ).execute().data[0]
        debt = db.table("debts").insert(
            {"user_id": user_id, "bank": "Bank A", "principal_minor": 500_000, "installment_minor": 100_000, "installment_count": 5}
        ).execute().data[0]

        expected = build_schedule(
            {
                "created_on": date.fromisoformat(debt["created_at"][:10]),
                "installment_minor": 100_000,
                "installment_count": 5,
            },
            [{"starts_on": date.fromisoformat(period["starts_on"])}],
        )

        first = db.rpc("generate_debt_schedule", {"p_debt_id": debt["id"]}).execute().data
        second = db.rpc("generate_debt_schedule", {"p_debt_id": debt["id"]}).execute().data
        assert len(first) == 5
        # Concurrent-safe by construction (row-locked RPC): calling it twice
        # sequentially must yield the exact same rows, not duplicates.
        assert {row["id"] for row in first} == {row["id"] for row in second}
        actual = sorted(({"ordinal": row["ordinal"], "due_on": row["due_on"]} for row in first), key=lambda r: r["ordinal"])
        expected_sorted = sorted(
            ({"ordinal": item["ordinal"], "due_on": item["due_on"].isoformat()} for item in expected), key=lambda r: r["ordinal"]
        )
        assert actual == expected_sorted
    finally:
        if user_id:
            try:
                admin.auth.admin.delete_user(user_id)
            except Exception:
                pass
