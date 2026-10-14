"""Client for the Pleos Vehicle Data API (read only)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import API_HOST, ENDPOINTS

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30)

# The token response carries no lifetime; the documentation states one hour.
DEFAULT_TOKEN_LIFETIME = 3600
TOKEN_REFRESH_MARGIN = 120

# Codes that mean "the access token is no longer accepted, fetch a new one".
TOKEN_CODES = frozenset({"401", "4009", "4011", "40002", "40003", "40004"})
# Codes returned by the token endpoint for an unknown or revoked key.
KEY_CODES = frozenset({"40001", "40404"})
NO_DATA_CODE = "4045"
NO_PERMISSION_CODE = "5006"
UNREGISTERED_VEHICLE_CODE = "4101"
REGION_HINTS = ("region", "country", "not supported in")


class PleosError(Exception):
    """Base error of the Pleos client."""


class PleosConnectionError(PleosError):
    """Pleos could not be reached or answered with a server error."""


class PleosAuthError(PleosError):
    """The client ID / secret is wrong, revoked or expired."""


class PleosRegionError(PleosAuthError):
    """The account or vehicle is outside a supported region."""


class PleosNoDataError(PleosError):
    """The vehicle has not reported data for this endpoint (4045)."""


class PleosPermissionError(PleosError):
    """The key has no permission for this data (5006 / persistent 403)."""


class PleosVehicleNotFoundError(PleosError):
    """The vehicle is not (or no longer) part of the key (4101)."""


class PleosApiError(PleosError):
    """Any other error answer."""

    def __init__(self, status: int, code: str | None, message: str | None) -> None:
        """Store the error details without URLs (they contain the VIN)."""
        super().__init__(f"HTTP {status}, code {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


def _error_details(payload: Any) -> tuple[str | None, str | None]:
    """Return (code, message) of an error answer."""
    if not isinstance(payload, dict):
        return None, None
    for key in ("error", "meta"):
        block = payload.get(key)
        if isinstance(block, dict) and block.get("code") is not None:
            message = block.get("message")
            return str(block["code"]), str(message) if message is not None else None
    if payload.get("code") is not None:
        message = payload.get("message")
        return str(payload["code"]), str(message) if message is not None else None
    return None, None


def _is_error(status: int, payload: Any) -> bool:
    if status >= 300:
        return True
    if not isinstance(payload, dict):
        return True
    if payload.get("error"):
        return True
    meta = payload.get("meta")
    return isinstance(meta, dict) and meta.get("success") in (False, "false")


class PleosClient:
    """Small async client: personal token + vehicle data endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        brand: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.brand = brand
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._token: str | None = None
        self._token_expires = 0.0
        self._token_lock = asyncio.Lock()

    async def _raw(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        headers = {"Brand": self.brand, "Accept": "application/json"}
        if body is None:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with self._session.request(
                method,
                API_HOST + path,
                headers=headers,
                json=body,
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as resp:
                try:
                    payload = await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    payload = None
                return resp.status, payload
        except (aiohttp.ClientError, TimeoutError) as err:
            # Never include the URL: it contains the VIN.
            raise PleosConnectionError(type(err).__name__) from None

    async def async_login(self) -> None:
        """Fetch a new access token (always)."""
        status, payload = await self._raw(
            "POST",
            "/v1/auth/personal-token",
            body={"clientId": self._client_id, "clientSecret": self._client_secret},
        )
        if _is_error(status, payload):
            code, message = _error_details(payload)
            if status == 429 or status >= 500:
                raise PleosConnectionError(f"HTTP {status}")
            text = (message or "").lower()
            if status == 451 or any(hint in text for hint in REGION_HINTS):
                raise PleosRegionError(message or f"HTTP {status}")
            if status in (400, 401, 403, 404) or code in KEY_CODES | TOKEN_CODES:
                raise PleosAuthError(f"HTTP {status}, code {code}")
            raise PleosApiError(status, code, message)
        data = payload.get("data") if isinstance(payload, dict) else None
        token = data.get("accessToken") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise PleosApiError(status, "missing_token", "No access token in answer")
        lifetime = data.get("expiresIn")
        if not isinstance(lifetime, (int, float)) or lifetime <= 0:
            lifetime = DEFAULT_TOKEN_LIFETIME
        self._token = token
        self._token_expires = time.monotonic() + lifetime - TOKEN_REFRESH_MARGIN

    async def _ensure_token(self, stale: str | None = None) -> None:
        """Log in when there is no valid token, or the token is ``stale``.

        Parallel requests that all saw the same rejected token log in once.
        """
        async with self._token_lock:
            if (
                self._token is None
                or (stale is not None and self._token == stale)
                or time.monotonic() >= self._token_expires
            ):
                await self.async_login()

    def invalidate_token(self) -> None:
        """Forget the current token (next call logs in again)."""
        self._token = None

    async def async_get(self, path: str) -> Any:
        """GET a path and return the "data" block; refreshes the token once."""
        await self._ensure_token()
        for attempt in range(2):
            used_token = self._token
            status, payload = await self._raw("GET", path)
            if not _is_error(status, payload):
                return payload.get("data")
            code, message = _error_details(payload)
            token_problem = status == 401 or code in TOKEN_CODES
            if attempt == 0 and (
                token_problem or (status == 403 and code != NO_PERMISSION_CODE)
            ):
                # Expired tokens come back as 401, 403 or 40003: log in again.
                await self._ensure_token(stale=used_token)
                continue
            if code == NO_DATA_CODE:
                raise PleosNoDataError(path.rsplit("/", 1)[-1])
            if code == UNREGISTERED_VEHICLE_CODE:
                raise PleosVehicleNotFoundError(code)
            if code == NO_PERMISSION_CODE or status == 403:
                raise PleosPermissionError(code or str(status))
            if token_problem:
                raise PleosAuthError(f"HTTP {status}, code {code}")
            if status == 429 or status >= 500:
                raise PleosConnectionError(f"HTTP {status}")
            raise PleosApiError(status, code, message)
        raise PleosApiError(0, None, "unreachable")  # pragma: no cover

    async def async_get_vehicles(self) -> list[dict[str, Any]]:
        """Return the vehicles contained in the key."""
        data = await self.async_get("/v1/vehicles/consent")
        vehicles = data.get("vehicles") if isinstance(data, dict) else None
        if not isinstance(vehicles, list):
            raise PleosApiError(200, "invalid_vehicle_list", "No vehicle list")
        return [
            vehicle
            for vehicle in vehicles
            if isinstance(vehicle, dict) and isinstance(vehicle.get("vin"), str) and vehicle["vin"]
        ]

    async def async_get_vehicle_data(self, vin: str) -> dict[str, dict[str, Any] | None]:
        """Fetch all snapshot endpoints of a vehicle in parallel.

        Endpoints without data or permission come back as None. Auth, connection
        and "vehicle not in key" errors are raised.
        """
        await self._ensure_token()

        async def fetch(endpoint: str) -> dict[str, Any] | None:
            try:
                data = await self.async_get(f"/v1/vehicles/{vin}/{endpoint}")
            except (PleosNoDataError, PleosPermissionError) as err:
                _LOGGER.debug("No %s data: %s", endpoint, type(err).__name__)
                return None
            except PleosApiError as err:
                _LOGGER.debug("Error on %s: %s", endpoint, err)
                return None
            return data if isinstance(data, dict) else None

        results = await asyncio.gather(
            *(fetch(endpoint) for endpoint in ENDPOINTS), return_exceptions=True
        )
        data: dict[str, dict[str, Any] | None] = {}
        for endpoint, result in zip(ENDPOINTS, results, strict=True):
            if isinstance(result, BaseException):
                raise result
            data[endpoint] = result
        return data


def vehicle_display_name(vehicle: dict[str, Any]) -> str:
    """Name shown in the brand app: nickname, else name, else sellname."""
    for key in ("nickname", "name", "sellname"):
        value = vehicle.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return vehicle["vin"]


def vehicle_model(vehicle: dict[str, Any]) -> str | None:
    """Model name (sellname) of a vehicle."""
    for key in ("sellname", "name"):
        value = vehicle.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
