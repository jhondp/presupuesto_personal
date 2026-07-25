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


@pytest.mark.anyio
async def test_overlapping_period_is_rejected_with_409(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    first = await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})
    assert first.status_code == 201
    overlapping = await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-15", "ends_on": "2026-02-15"})
    assert overlapping.status_code == 409
    assert overlapping.json()["code"] == "period_overlap"


@pytest.mark.anyio
async def test_close_then_reopen_preserves_the_same_period_and_bumps_version(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    created = (await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})).json()
    period_id = created["id"]

    closed = await http.post(f"/v1/periods/{period_id}/close", headers={**headers, "If-Match": str(created["version"])})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["version"] == created["version"] + 1

    reopened = await http.post(f"/v1/periods/{period_id}/reopen", headers={**headers, "If-Match": str(closed.json()["version"])})
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
    # Same record survives the round trip: reopening does not create a new period.
    assert reopened.json()["id"] == period_id
    assert (await http.get("/v1/periods", headers=headers)).json() == [reopened.json()]


@pytest.mark.anyio
async def test_closing_with_a_stale_if_match_is_rejected_with_409(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    created = (await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})).json()
    period_id = created["id"]

    stale = await http.post(f"/v1/periods/{period_id}/close", headers={**headers, "If-Match": "999"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"
    # A rejected transition must not mutate the record.
    assert (await http.get("/v1/periods", headers=headers)).json()[0]["status"] == "open"


@pytest.mark.anyio
async def test_closing_without_if_match_is_rejected(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    created = (await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})).json()
    response = await http.post(f"/v1/periods/{created['id']}/close", headers=headers)
    assert response.status_code == 428
    assert response.json()["code"] == "if_match_required"


@pytest.mark.anyio
async def test_closing_an_already_closed_period_is_rejected(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    created = (await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})).json()
    period_id = created["id"]
    await http.post(f"/v1/periods/{period_id}/close", headers={**headers, "If-Match": str(created["version"])})

    again = await http.post(f"/v1/periods/{period_id}/close", headers={**headers, "If-Match": "2"})
    assert again.status_code == 409
    assert again.json()["code"] == "invalid_transition"


@pytest.mark.anyio
async def test_another_users_period_is_not_found(client):
    http, app = client
    gateway = InMemorySupabaseGateway()
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    owner_headers = {"Authorization": f"Bearer {token_for('owner-a')}"}
    other_headers = {"Authorization": f"Bearer {token_for('owner-b')}"}

    created = (await http.post("/v1/periods", headers=owner_headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})).json()
    response = await http.post(
        f"/v1/periods/{created['id']}/close", headers={**other_headers, "If-Match": str(created["version"])}
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_a_conflict_raised_by_the_gateway_becomes_409_not_500(client):
    """Regression test: on the live SupabaseGateway path, a lost version race
    or an invalid transition surfaces as a raised PeriodConflictError, not a
    None return (see repositories/supabase.py._transition_period). The route
    must catch that and return the documented 409 — before this fix it fell
    through to the generic 500 handler instead."""
    from app.domain.periods import PeriodConflictError

    http, app = client
    gateway = InMemorySupabaseGateway()

    def _boom(self, user_id, period_id, expected_version):
        raise PeriodConflictError("version_conflict", "The period was modified by another request")

    gateway.close_period = _boom.__get__(gateway, InMemorySupabaseGateway)
    app.dependency_overrides[get_gateway] = gateway_override(gateway)
    headers = {"Authorization": f"Bearer {token_for('owner-a')}"}

    created = (await http.post("/v1/periods", headers=headers, json={"starts_on": "2026-01-01", "ends_on": "2026-01-31"})).json()
    response = await http.post(f"/v1/periods/{created['id']}/close", headers={**headers, "If-Match": str(created["version"])})
    assert response.status_code == 409
    assert response.json()["code"] == "version_conflict"


def test_transition_period_classifies_rpc_errors_by_exact_message(monkeypatch):
    """Unit-level: SupabaseGateway._transition_period must match the RPCs'
    exact `raise exception '...'` strings (0004_period_lifecycle.sql), not
    loose substrings — an unrecognized error must re-raise rather than being
    mislabeled as a stale-version conflict."""
    from postgrest.exceptions import APIError

    from app.core.config import Settings
    from app.domain.periods import PeriodConflictError
    from app.repositories.supabase import SupabaseGateway

    class _FakeRpcCall:
        def __init__(self, error_message: str | None):
            self._error_message = error_message

        def execute(self):
            if self._error_message is not None:
                raise APIError({"message": self._error_message, "code": "P0001", "details": None, "hint": None})
            return type("Response", (), {"data": None})()

    class _FakePostgrest:
        def auth(self, token: str) -> None:
            pass

    class _FakeClient:
        def __init__(self, error_message: str | None):
            self.postgrest = _FakePostgrest()
            self._error_message = error_message

        def rpc(self, name: str, params: dict):
            return _FakeRpcCall(self._error_message)

    def gateway_with(error_message: str | None) -> SupabaseGateway:
        monkeypatch.setattr("supabase.create_client", lambda url, key: _FakeClient(error_message))
        return SupabaseGateway(Settings(supabase_url="https://example.test", supabase_anon_key="anon-key"), access_token="user-jwt")

    assert gateway_with("period_not_found").close_period("user-1", "period-1", 1) is None

    with pytest.raises(PeriodConflictError) as invalid:
        gateway_with("period_already_closed").close_period("user-1", "period-1", 1)
    assert invalid.value.code == "invalid_transition"

    with pytest.raises(PeriodConflictError) as conflict:
        gateway_with("version_conflict").close_period("user-1", "period-1", 1)
    assert conflict.value.code == "version_conflict"

    with pytest.raises(APIError):
        gateway_with("some_unrelated_database_error").close_period("user-1", "period-1", 1)
