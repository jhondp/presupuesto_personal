import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import ApiError


@dataclass(frozen=True)
class Principal:
    user_id: str
    access_token: str


def _decode_segment(segment: str) -> dict[str, object]:
    try:
        padded = segment + "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError):
        raise ApiError(401, "invalid_token", "Invalid authentication token") from None


class JwtVerifier:
    """Verifies HS256 Supabase JWTs at the API boundary before data access."""

    def __init__(self, secret: str):
        self.secret = secret

    def verify(self, token: str) -> Principal:
        if not self.secret:
            raise ApiError(503, "auth_not_configured", "Authentication is not configured")
        parts = token.split(".")
        if len(parts) != 3:
            raise ApiError(401, "invalid_token", "Invalid authentication token")
        header = _decode_segment(parts[0])
        payload = _decode_segment(parts[1])
        if header.get("alg") != "HS256":
            raise ApiError(401, "invalid_token", "Invalid authentication token")
        signed = f"{parts[0]}.{parts[1]}".encode()
        expected = base64.urlsafe_b64encode(hmac.new(self.secret.encode(), signed, hashlib.sha256).digest()).rstrip(b"=").decode()
        if not hmac.compare_digest(expected, parts[2]):
            raise ApiError(401, "invalid_token", "Invalid authentication token")
        subject = payload.get("sub")
        expires_at = payload.get("exp")
        if not isinstance(subject, str) or not subject or not isinstance(expires_at, (int, float)) or expires_at <= time.time():
            raise ApiError(401, "invalid_token", "Invalid authentication token")
        return Principal(user_id=subject, access_token=token)


async def get_current_principal(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "authentication_required", "Authentication is required")
    return JwtVerifier(settings.supabase_jwt_secret).verify(authorization.removeprefix("Bearer ").strip())
