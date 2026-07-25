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


async def _open_period(http, headers, starts_on: str, ends_on: str):
    return (await http.post("/v1/periods", headers=headers, json={"starts_on": starts_on, "ends_on": ends_on})).json()


@pytest.mark.anyio
async def test_insights_reports_period_totals_balance_and_category_breakdown(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    period = await _open_period(http, headers, "2026-01-01", "2026-01-31")
    salary = (await http.post("/v1/categories", headers=headers, json={"name": "Salary", "kind": "income"})).json()
    rent = (await http.post("/v1/categories", headers=headers, json={"name": "Rent", "kind": "expense"})).json()

    await http.post("/v1/income", headers=headers, json={"category_id": salary["id"], "occurred_on": "2026-01-05", "amount_minor": 500_000})
    await http.post("/v1/expenses", headers=headers, json={"category_id": rent["id"], "occurred_on": "2026-01-06", "amount_minor": 200_000})

    response = await http.get(f"/v1/insights?period_id={period['id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["income_minor"] == 500_000
    assert body["expense_minor"] == 200_000
    assert body["balance_minor"] == 300_000
    assert body["debt_due_minor"] == 0
    assert {row["category_id"]: row["total_minor"] for row in body["by_category"]} == {salary["id"]: 500_000, rent["id"]: 200_000}
    assert body["alerts"] == []


@pytest.mark.anyio
async def test_expense_total_alert_fires_only_once_threshold_is_reached(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    period = await _open_period(http, headers, "2026-01-01", "2026-01-31")
    rent = (await http.post("/v1/categories", headers=headers, json={"name": "Rent", "kind": "expense"})).json()
    await http.post(
        "/v1/alert-rules", headers=headers, json={"label": "Big rent", "kind": "expense_total", "threshold_minor": 200_000}
    )

    below = await http.post("/v1/expenses", headers=headers, json={"category_id": rent["id"], "occurred_on": "2026-01-06", "amount_minor": 100_000})
    assert below.status_code == 201
    quiet = await http.get(f"/v1/insights?period_id={period['id']}", headers=headers)
    assert quiet.json()["alerts"] == []

    await http.post("/v1/expenses", headers=headers, json={"category_id": rent["id"], "occurred_on": "2026-01-10", "amount_minor": 150_000})
    fired = await http.get(f"/v1/insights?period_id={period['id']}", headers=headers)
    alerts = fired.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "expense_total"
    assert alerts[0]["actual_minor"] == 250_000


@pytest.mark.anyio
async def test_debt_due_alert_fires_from_installments_due_within_the_viewed_period(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    period = await _open_period(http, headers, "2030-02-01", "2030-02-28")
    debt = (
        await http.post(
            "/v1/debts",
            headers=headers,
            json={"bank": "Bank A", "principal_minor": 200_000, "installment_minor": 100_000, "installment_count": 2},
        )
    ).json()
    await http.post(f"/v1/debts/{debt['id']}/schedule", headers=headers)
    await http.post("/v1/alert-rules", headers=headers, json={"label": "Debt due", "kind": "debt_due", "threshold_minor": 100_000})

    response = await http.get(f"/v1/insights?period_id={period['id']}", headers=headers)
    body = response.json()
    assert body["debt_due_minor"] == 100_000
    assert [alert["kind"] for alert in body["alerts"]] == ["debt_due"]


@pytest.mark.anyio
async def test_repeated_insight_reads_do_not_mutate_alert_rule_or_installment_state(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    period = await _open_period(http, headers, "2026-01-01", "2026-01-31")
    await http.post("/v1/alert-rules", headers=headers, json={"label": "Rule", "kind": "expense_total", "threshold_minor": 1})
    rule_before = gateway.list_alert_rules("owner-a")

    for _ in range(3):
        await http.get(f"/v1/insights?period_id={period['id']}", headers=headers)

    assert gateway.list_alert_rules("owner-a") == rule_before


@pytest.mark.anyio
async def test_insights_for_another_users_period_is_not_found(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    owner_headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    other_headers = {"Authorization": f"Bearer {token_for('owner-b')}"}
    period = await _open_period(http, owner_headers, "2026-01-01", "2026-01-31")

    response = await http.get(f"/v1/insights?period_id={period['id']}", headers=other_headers)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_alert_rules_are_owner_only(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    owner_headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    other_headers = {"Authorization": f"Bearer {token_for('owner-b')}"}

    rule = (
        await http.post("/v1/alert-rules", headers=owner_headers, json={"label": "Rule", "kind": "expense_total", "threshold_minor": 1})
    ).json()

    assert (await http.get("/v1/alert-rules", headers=other_headers)).json() == []
    assert (await http.delete(f"/v1/alert-rules/{rule['id']}", headers=other_headers)).status_code == 404
    still_there = await http.get("/v1/alert-rules", headers=owner_headers)
    assert len(still_there.json()) == 1

    deleted = await http.delete(f"/v1/alert-rules/{rule['id']}", headers=owner_headers)
    assert deleted.status_code == 204
    assert (await http.get("/v1/alert-rules", headers=owner_headers)).json() == []


@pytest.mark.anyio
async def test_creating_an_alert_rule_with_a_foreign_category_is_not_found(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    owner_headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    other_headers = {"Authorization": f"Bearer {token_for('owner-b')}"}
    category = (await http.post("/v1/categories", headers=other_headers, json={"name": "Rent", "kind": "expense"})).json()

    response = await http.post(
        "/v1/alert-rules",
        headers=owner_headers,
        json={"label": "Rule", "kind": "expense_total", "threshold_minor": 1, "category_id": category["id"]},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_export_includes_alert_rules(client):
    http, app = client
    app.dependency_overrides[get_gateway] = gateway_override(InMemorySupabaseGateway())
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    await http.post("/v1/alert-rules", headers=headers, json={"label": "Rule", "kind": "expense_total", "threshold_minor": 1})

    exported = await http.get("/v1/account/export", headers=headers)
    assert len(exported.json()["alert_rules"]) == 1
