import base64
import hashlib
import hmac
import json
import sys
import time
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


async def _open_period(http, headers):
    response = await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})
    return response.json()


@pytest.mark.anyio
async def test_categories_are_owner_only(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    a_headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    b_headers = {"Authorization": f"Bearer {token_for('owner-b')}"}

    category = (await http.post("/v1/categories", headers=a_headers, json={"name": "Salary", "kind": "income"})).json()
    assert (await http.get("/v1/categories", headers=b_headers)).json() == []
    hidden = await http.post(f"/v1/categories/{category['id']}/archive", headers=b_headers)
    assert hidden.status_code == 404


@pytest.mark.anyio
async def test_archiving_a_category_keeps_history_but_blocks_new_assignment(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    await _open_period(http, headers)
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()

    entry = await http.post(
        "/v1/income",
        headers=headers,
        json={"category_id": category["id"], "occurred_on": "2026-01-10", "amount_minor": 500_000},
    )
    assert entry.status_code == 201

    archived = await http.post(f"/v1/categories/{category['id']}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    still_there = await http.get("/v1/income", headers=headers)
    assert still_there.json()[0]["category_id"] == category["id"]

    blocked = await http.post(
        "/v1/income",
        headers=headers,
        json={"category_id": category["id"], "occurred_on": "2026-01-11", "amount_minor": 1_000},
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "category_not_assignable"


@pytest.mark.anyio
async def test_income_entries_report_valid_period_totals(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    period = await _open_period(http, headers)
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()

    for amount in (100_000, 250_000):
        response = await http.post(
            "/v1/income",
            headers=headers,
            json={"category_id": category["id"], "occurred_on": "2026-01-05", "amount_minor": amount},
        )
        assert response.status_code == 201

    listed = await http.get(f"/v1/income?period_id={period['id']}", headers=headers)
    entries = listed.json()
    assert len(entries) == 2
    assert sum(entry["amount_minor"] for entry in entries) == 350_000


@pytest.mark.anyio
async def test_income_and_expense_entries_are_kept_in_separate_rows(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    await _open_period(http, headers)
    income_category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()
    expense_category = (await http.post("/v1/categories", headers=headers, json={"name": "Rent", "kind": "expense"})).json()

    await http.post(
        "/v1/income",
        headers=headers,
        json={"category_id": income_category["id"], "occurred_on": "2026-01-05", "amount_minor": 500_000},
    )
    await http.post(
        "/v1/expenses",
        headers=headers,
        json={"category_id": expense_category["id"], "occurred_on": "2026-01-06", "amount_minor": 300_000},
    )

    income_entries = (await http.get("/v1/income", headers=headers)).json()
    expense_entries = (await http.get("/v1/expenses", headers=headers)).json()
    assert len(income_entries) == 1
    assert len(expense_entries) == 1
    assert income_entries[0]["id"] != expense_entries[0]["id"]

    wrong_kind = await http.post(
        "/v1/income",
        headers=headers,
        json={"category_id": expense_category["id"], "occurred_on": "2026-01-07", "amount_minor": 1_000},
    )
    assert wrong_kind.status_code == 422
    assert wrong_kind.json()["code"] == "category_kind_mismatch"


@pytest.mark.anyio
async def test_editing_an_expense_in_a_closed_period_is_rejected_until_reopened(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    period = await _open_period(http, headers)
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Rent", "kind": "expense"})).json()
    entry = (
        await http.post(
            "/v1/expenses",
            headers=headers,
            json={"category_id": category["id"], "occurred_on": "2026-01-06", "amount_minor": 300_000},
        )
    ).json()

    await http.post(f"/v1/periods/{period['id']}/close", headers={**headers, "If-Match": str(period["version"])})

    blocked = await http.put(f"/v1/expenses/{entry['id']}", headers=headers, json={"amount_minor": 400_000})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "period_closed"

    reopened = await http.post(f"/v1/periods/{period['id']}/reopen", headers={**headers, "If-Match": "2"})
    assert reopened.status_code == 200

    allowed = await http.put(f"/v1/expenses/{entry['id']}", headers=headers, json={"amount_minor": 400_000})
    assert allowed.status_code == 200
    assert allowed.json()["amount_minor"] == 400_000


@pytest.mark.anyio
async def test_partial_update_only_changes_the_provided_field(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    await _open_period(http, headers)
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()
    entry = (
        await http.post(
            "/v1/income",
            headers=headers,
            json={"category_id": category["id"], "occurred_on": "2026-01-05", "amount_minor": 100_000, "note": "original"},
        )
    ).json()

    updated = await http.put(f"/v1/income/{entry['id']}", headers=headers, json={"amount_minor": 150_000})
    assert updated.status_code == 200
    body = updated.json()
    assert body["amount_minor"] == 150_000
    assert body["category_id"] == category["id"]
    assert body["occurred_on"] == "2026-01-05"
    assert body["note"] == "original"


@pytest.mark.anyio
async def test_explicit_null_note_clears_it_but_omitting_it_leaves_it_unchanged(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    await _open_period(http, headers)
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()
    entry = (
        await http.post(
            "/v1/income",
            headers=headers,
            json={"category_id": category["id"], "occurred_on": "2026-01-05", "amount_minor": 100_000, "note": "original"},
        )
    ).json()

    unchanged = await http.put(f"/v1/income/{entry['id']}", headers=headers, json={"amount_minor": 120_000})
    assert unchanged.json()["note"] == "original"

    cleared = await http.put(f"/v1/income/{entry['id']}", headers=headers, json={"note": None})
    assert cleared.status_code == 200
    assert cleared.json()["note"] is None
    # Clearing note must not have touched the other fields.
    assert cleared.json()["amount_minor"] == 120_000


@pytest.mark.anyio
async def test_moving_an_entry_to_a_different_period_updates_its_period_id(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    january = await _open_period(http, headers)
    february = (
        await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-02-01", "ends_on": "2026-02-28"})
    ).json()
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()
    entry = (
        await http.post(
            "/v1/income",
            headers=headers,
            json={"category_id": category["id"], "occurred_on": "2026-01-05", "amount_minor": 100_000},
        )
    ).json()
    assert entry["period_id"] == january["id"]

    moved = await http.put(f"/v1/income/{entry['id']}", headers=headers, json={"occurred_on": "2026-02-10"})
    assert moved.status_code == 200
    assert moved.json()["period_id"] == february["id"]
    assert moved.json()["occurred_on"] == "2026-02-10"

    # The entry no longer appears under its original period's listing.
    january_entries = (await http.get(f"/v1/income?period_id={january['id']}", headers=headers)).json()
    assert january_entries == []
    february_entries = (await http.get(f"/v1/income?period_id={february['id']}", headers=headers)).json()
    assert len(february_entries) == 1


@pytest.mark.anyio
async def test_moving_an_entry_into_a_closed_period_is_rejected(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    january = await _open_period(http, headers)
    february = (
        await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-02-01", "ends_on": "2026-02-28"})
    ).json()
    await http.post(f"/v1/periods/{february['id']}/close", headers={**headers, "If-Match": str(february["version"])})
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()
    entry = (
        await http.post(
            "/v1/income",
            headers=headers,
            json={"category_id": category["id"], "occurred_on": "2026-01-05", "amount_minor": 100_000},
        )
    ).json()

    blocked = await http.put(f"/v1/income/{entry['id']}", headers=headers, json={"occurred_on": "2026-02-10"})
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "no_open_period"
    # Rejected — the entry must still belong to its original period.
    assert (await http.get(f"/v1/income?period_id={january['id']}", headers=headers)).json()[0]["id"] == entry["id"]


@pytest.mark.anyio
async def test_writing_an_entry_with_no_matching_open_period_is_rejected(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    category = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()

    response = await http.post(
        "/v1/income",
        headers=headers,
        json={"category_id": category["id"], "occurred_on": "2026-01-05", "amount_minor": 1_000},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "no_open_period"
