"""Salesforce JWT Bearer authentication with a small in-memory token cache."""

import asyncio
import os
import time
from typing import TypedDict

import httpx
import jwt as pyjwt


class SessionCache(TypedDict):
    access_token: str | None
    instance_url: str | None
    expires_at: float


_SESSION_CACHE: SessionCache = {
    "access_token": None,
    "instance_url": None,
    "expires_at": 0,
}
_SESSION_LOCK = asyncio.Lock()
_DEFAULT_SESSION_TTL_SECONDS = 25 * 60


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _build_jwt_assertion() -> str:
    client_id = _required_env("SALESFORCE_JWT_CLIENT_ID")
    subject = _required_env("SALESFORCE_JWT_SUBJECT")

    private_key = _required_env("SALESFORCE_JWT_PRIVATE_KEY").replace("\\n", "\n")
    audience = os.environ.get(
        "SALESFORCE_JWT_AUDIENCE",
        "https://login.salesforce.com",
    ).strip()

    now = int(time.time())
    claims = {
        "iss": client_id,
        "sub": subject,
        "aud": audience,
        "exp": now + 180,
    }
    return pyjwt.encode(claims, private_key, algorithm="RS256")


async def get_salesforce_session(force_refresh: bool = False) -> tuple[str, str]:
    """Return ``(access_token, instance_url)``."""
    now = time.time()

    if (
        not force_refresh
        and _SESSION_CACHE["access_token"]
        and _SESSION_CACHE["instance_url"]
        and now < _SESSION_CACHE["expires_at"]
    ):
        return _SESSION_CACHE["access_token"], _SESSION_CACHE["instance_url"]

    async with _SESSION_LOCK:
        now = time.time()
        if (
            not force_refresh
            and _SESSION_CACHE["access_token"]
            and _SESSION_CACHE["instance_url"]
            and now < _SESSION_CACHE["expires_at"]
        ):
            return _SESSION_CACHE["access_token"], _SESSION_CACHE["instance_url"]

        token_url = os.environ.get(
            "SALESFORCE_TOKEN_URL",
            "https://login.salesforce.com/services/oauth2/token",
        ).strip()

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": _build_jwt_assertion(),
                },
            )

        if response.is_error:
            raise RuntimeError(
                f"Salesforce token exchange failed "
                f"({response.status_code}): {response.text}"
            )

        payload = response.json()
        access_token = payload.get("access_token")
        instance_url = payload.get("instance_url")
        if not access_token or not instance_url:
            raise RuntimeError(
                "Salesforce token response did not contain access_token "
                "and instance_url."
            )

        _SESSION_CACHE["access_token"] = access_token
        _SESSION_CACHE["instance_url"] = instance_url.rstrip("/")
        _SESSION_CACHE["expires_at"] = now + _DEFAULT_SESSION_TTL_SECONDS

        return access_token, instance_url.rstrip("/")
