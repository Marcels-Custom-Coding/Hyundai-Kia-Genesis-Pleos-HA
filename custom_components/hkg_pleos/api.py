"""Client for the Pleos Vehicle Data API (private users)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import API_HOST

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30)

# Token is missing, expired or no longer accepted: fetch a new one and retry.
TOKEN_ERRORS = {"401", "4011", "40002", "40003", "40004"}
# No data for this VIN (yet), or the endpoint is not offered for it.
NO_DATA_ERRORS = {"4045", "403", "404"}
# The vehicle is no longer part of the key (consent withdrawn, car removed).
VEHICLE_GONE_ERRORS = {"4101", "5006"}


class PleosError(Exception):
    """Generic Pleos error."""

    def __init__(self, message: str = "", code: str | None = None) -> None:
        super().__init__(message or code or "Pleos error")
        self.code = code


class PleosConnectionError(PleosError):
    """Pleos could not be reached or answered with a server error."""


class PleosAuthError(PleosError):
    """Client ID or secret are wrong, revoked or expired."""


class PleosVehicleGoneError(PleosError):
    """The VIN is no longer shared with this key."""


def _error_code(payload: Any) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        code = payload["error"].get("code")
        return None if code is None else str(code)
    return None


class PleosClient:
    """Small async client: one access token per brand and API key."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        brand: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._session = session
        self.brand = brand
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def _call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        headers = {"Brand": self.brand, "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._session.request(
                method, f"{API_HOST}{path}", headers=headers, json=json, timeout=TIMEOUT
            ) as resp:
                try:
                    payload = await resp.json(content_type=None)
                except ValueError:
                    payload = None
                return resp.status, payload
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PleosConnectionError(str(err) or type(err).__name__) from err

    async def async_login(self) -> str:
        """Fetch a new access token."""
        status, payload = await self._call(
            "POST",
            "/v1/auth/personal-token",
            json={"clientId": self._client_id, "clientSecret": self._client_secret},
        )
        token = None
        if status == 200 and isinstance(payload, dict):
            token = (payload.get("data") or {}).get("accessToken")
        if token:
            self._token = token
            return token
        code = _error_code(payload)
        if status >= 500 or code in {"50001", "50201", "5001"}:
            raise PleosConnectionError(f"Login failed with HTTP {status}", code)
        raise PleosAuthError(f"Login refused (HTTP {status})", code)

    async def _token_for_request(self) -> str:
        async with self._lock:
            if self._token is None:
                await self.async_login()
            assert self._token is not None
            return self._token

    async def _renew_token(self, used: str) -> None:
        async with self._lock:
            # Another request may already have fetched a fresh token.
            if self._token == used:
                self._token = None
                await self.async_login()

    async def _get(self, path: str) -> tuple[int, Any]:
        token = await self._token_for_request()
        status, payload = await self._call("GET", path, token=token)
        if status != 200 and (_error_code(payload) in TOKEN_ERRORS or status == 401):
            _LOGGER.debug("Access token rejected, fetching a new one")
            await self._renew_token(token)
            token = await self._token_for_request()
            status, payload = await self._call("GET", path, token=token)
            if status != 200 and (
                _error_code(payload) in TOKEN_ERRORS or status == 401
            ):
                raise PleosAuthError("Access token rejected", _error_code(payload))
        return status, payload

    async def async_get_vehicles(self) -> list[dict[str, Any]]:
        """Return the vehicles shared with this key."""
        status, payload = await self._get("/v1/vehicles/consent")
        if status == 200 and isinstance(payload, dict):
            vehicles = (payload.get("data") or {}).get("vehicles") or []
            return [v for v in vehicles if isinstance(v, dict) and v.get("vin")]
        code = _error_code(payload)
        if code in NO_DATA_ERRORS:
            return []
        if status >= 500:
            raise PleosConnectionError(f"Vehicle list failed (HTTP {status})", code)
        raise PleosError(f"Vehicle list failed (HTTP {status})", code)

    async def async_get_endpoint(
        self, vin: str, endpoint: str
    ) -> dict[str, Any] | None:
        """Return the data block of one vehicle endpoint, None if there is none."""
        status, payload = await self._get(f"/v1/vehicles/{vin}/{endpoint}")
        if status == 200 and isinstance(payload, dict):
            data = payload.get("data")
            return data if isinstance(data, dict) else None
        code = _error_code(payload)
        if code in NO_DATA_ERRORS:
            return None
        if code in VEHICLE_GONE_ERRORS:
            raise PleosVehicleGoneError(f"Vehicle not shared ({code})", code)
        if status >= 500:
            raise PleosConnectionError(f"{endpoint} failed (HTTP {status})", code)
        raise PleosError(f"{endpoint} failed (HTTP {status})", code)
