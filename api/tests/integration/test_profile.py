import base64
import hashlib
import hmac
import json
import logging
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


@pytest.mark.anyio
async def test_foreign_and_missing_profile_have_indistinguishable_404_and_no_sensitive_logs(client, caplog):
    http, app = client
    gateway = InMemorySupabaseGateway()
    gateway.ensure_profile("owner-a")
    app.dependency_overrides[get_gateway] = gateway_override(gateway)

    caplog.set_level(logging.INFO, logger="app")
    token = token_for("owner-b")
    headers = {"Authorization": f"Bearer {token}"}
    foreign = await http.get("/v1/profiles/owner-a", headers=headers)
    missing = await http.get("/v1/profiles/not-a-user", headers=headers)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["code"] == missing.json()["code"] == "resource_not_found"
    assert foreign.json()["message"] == missing.json()["message"] == "Resource not_found".replace("_", " ")
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in logs
    assert "owner-a" not in logs


@pytest.mark.anyio
async def test_profile_defaults_to_clp_and_owner_can_select_supported_currency(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    assert (await http.get("/v1/profile", headers=headers)).json() == {"currency_code": "CLP", "decimal_scale": 0}
    response = await http.put("/v1/profile", headers=headers, json={"currency_code": "USD"})
    assert response.status_code == 200
    assert response.json() == {"currency_code": "USD", "decimal_scale": 2}


@pytest.mark.anyio
async def test_export_and_deletion_only_affect_authenticated_user(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    gateway.ensure_profile("owner-a")
    gateway.ensure_profile("owner-b")
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    a_headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    b_headers = {"Authorization": f"Bearer {token_for('owner-b')}"}

    exported = await http.get("/v1/account/export", headers=a_headers)
    assert exported.status_code == 200
    assert exported.json()["profile"]["user_id"] == "owner-a"
    assert "owner-b" not in json.dumps(exported.json())
    assert (await http.delete("/v1/account", headers=a_headers)).status_code == 204
    assert (await http.get("/v1/profile", headers=b_headers)).status_code == 200
    assert gateway.get_profile("owner-a") is None
    assert gateway.get_profile("owner-b") is not None


@pytest.mark.anyio
async def test_configured_export_limit_rejects_without_mutating_existing_data(client, monkeypatch):
    monkeypatch.setenv("MAX_EXPORT_ROWS", "0")
    http, app = client
    gateway = InMemorySupabaseGateway()
    gateway.ensure_profile("owner-a")
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    response = await http.get("/v1/account/export", headers={"Authorization": f"Bearer {token_for('owner-a')}"})
    assert response.status_code == 429
    assert response.json()["code"] == "usage_limit_reached"
    assert gateway.get_profile("owner-a") is not None
