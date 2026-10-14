"""Tests for the Pleos API client."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.api import (
    PleosAuthError,
    PleosClient,
    PleosConnectionError,
    PleosRegionError,
    PleosVehicleNotFoundError,
    vehicle_display_name,
    vehicle_model,
)
from custom_components.hkg_pleos.const import ENDPOINTS

from .conftest import (
    BRAND,
    CLIENT_ID,
    CLIENT_SECRET,
    CONSENT_URL,
    TOKEN_URL,
    VIN,
    endpoint_url,
    sequence,
)

EXPIRED = {"error": {"code": "40003", "message": "Token expired"}}


def _client(hass: HomeAssistant, secret: str = CLIENT_SECRET) -> PleosClient:
    return PleosClient(async_get_clientsession(hass), BRAND, CLIENT_ID, secret)


def _calls(aioclient_mock: AiohttpClientMocker, url: str) -> list[Any]:
    return [call for call in aioclient_mock.mock_calls if str(call[1]) == url]


async def test_login_ok(hass: HomeAssistant, mock_pleos: AiohttpClientMocker) -> None:
    """Login sends ID and secret and the brand header."""
    client = _client(hass, secret=f"  {CLIENT_SECRET} ")
    await client.async_login()

    method, _url, body, headers = _calls(mock_pleos, TOKEN_URL)[0]
    assert method == "POST"
    assert body == {"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET}
    assert headers["Brand"] == BRAND
    assert "Authorization" not in headers


async def test_get_vehicles(hass: HomeAssistant, mock_pleos: AiohttpClientMocker) -> None:
    """The vehicle list is returned with bearer token and brand header."""
    vehicles = await _client(hass).async_get_vehicles()

    assert [v["vin"] for v in vehicles] == [VIN]
    assert vehicle_display_name(vehicles[0]) == "IONIQ 5"
    assert vehicle_model(vehicles[0]) == "IONIQ 5"
    _method, _url, _body, headers = _calls(mock_pleos, CONSENT_URL)[0]
    assert headers["Authorization"] == "Bearer test-access-token"
    assert headers["Brand"] == BRAND


async def test_get_vehicle_data(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    vehicle_payloads: dict[str, dict[str, Any]],
) -> None:
    """All snapshot endpoints are fetched with a single login."""
    data = await _client(hass).async_get_vehicle_data(VIN)

    assert set(data) == set(ENDPOINTS)
    for endpoint in ENDPOINTS:
        assert data[endpoint] == vehicle_payloads[endpoint]["data"]
    assert len(_calls(mock_pleos, TOKEN_URL)) == 1


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (HTTPStatus.UNAUTHORIZED, {"error": {"code": "40001", "message": "Invalid client"}}),
        (HTTPStatus.BAD_REQUEST, {"error": {"code": "40404", "message": "Unknown key"}}),
        (HTTPStatus.OK, {"meta": {"success": False, "code": "40001"}}),
    ],
)
async def test_login_wrong_secret(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    payload: dict[str, Any],
) -> None:
    """A wrong secret raises PleosAuthError (not the region subclass)."""
    aioclient_mock.post(TOKEN_URL, status=status, json=payload)

    with pytest.raises(PleosAuthError) as exc_info:
        await _client(hass, secret="wrong").async_login()
    assert not isinstance(exc_info.value, PleosRegionError)


async def test_login_region(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A region message raises PleosRegionError."""
    aioclient_mock.post(
        TOKEN_URL,
        status=HTTPStatus.FORBIDDEN,
        json={"error": {"code": "40300", "message": "Service is not supported in your region"}},
    )

    with pytest.raises(PleosRegionError):
        await _client(hass).async_login()


async def test_login_missing_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A success answer without token is an API error, not a crash."""
    aioclient_mock.post(TOKEN_URL, json={"data": {}})

    with pytest.raises(Exception, match="missing_token"):
        await _client(hass).async_login()


@pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.BAD_REQUEST])
async def test_token_refresh_on_40003(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    status: int,
) -> None:
    """An expired token (40003) triggers one new login and a retry."""
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    aioclient_mock.get(
        CONSENT_URL,
        side_effect=sequence(
            "get", CONSENT_URL, (status, EXPIRED), (HTTPStatus.OK, consent_payload)
        ),
    )

    vehicles = await _client(hass).async_get_vehicles()

    assert [v["vin"] for v in vehicles] == [VIN]
    assert len(_calls(aioclient_mock, TOKEN_URL)) == 2
    assert len(_calls(aioclient_mock, CONSENT_URL)) == 2


async def test_token_refresh_fails_twice(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
) -> None:
    """A token that is refused again after re-login raises PleosAuthError."""
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    aioclient_mock.get(CONSENT_URL, status=HTTPStatus.UNAUTHORIZED, json=EXPIRED)

    with pytest.raises(PleosAuthError):
        await _client(hass).async_get_vehicles()
    assert len(_calls(aioclient_mock, CONSENT_URL)) == 2


async def test_no_data_endpoint_is_none(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
) -> None:
    """An endpoint answering 4045 (no data) comes back as None."""
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    for endpoint, payload in vehicle_payloads.items():
        if endpoint == "locations":
            aioclient_mock.get(
                endpoint_url(endpoint),
                status=HTTPStatus.NOT_FOUND,
                json={"error": {"code": "4045", "message": "No data"}},
            )
        else:
            aioclient_mock.get(endpoint_url(endpoint), json=payload)

    data = await _client(hass).async_get_vehicle_data(VIN)

    assert data["locations"] is None
    assert data["batteries"] == vehicle_payloads["batteries"]["data"]
    assert data["status"] == vehicle_payloads["status"]["data"]


async def test_vehicle_not_found(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
) -> None:
    """4101 (vehicle not in key) raises PleosVehicleNotFoundError."""
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    for endpoint in ENDPOINTS:
        aioclient_mock.get(
            endpoint_url(endpoint),
            status=HTTPStatus.BAD_REQUEST,
            json={"error": {"code": "4101", "message": "Unregistered vehicle"}},
        )

    with pytest.raises(PleosVehicleNotFoundError):
        await _client(hass).async_get_vehicle_data(VIN)


async def test_connection_error_login(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A network problem raises PleosConnectionError without the URL."""
    aioclient_mock.post(TOKEN_URL, exc=aiohttp.ClientConnectionError("boom"))

    with pytest.raises(PleosConnectionError) as exc_info:
        await _client(hass).async_login()
    assert "pleos" not in str(exc_info.value).lower()


async def test_connection_error_vehicle_data(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
) -> None:
    """A timeout on one endpoint raises PleosConnectionError (no VIN in text)."""
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    for endpoint, payload in vehicle_payloads.items():
        if endpoint == "status":
            aioclient_mock.get(endpoint_url(endpoint), exc=TimeoutError())
        else:
            aioclient_mock.get(endpoint_url(endpoint), json=payload)

    with pytest.raises(PleosConnectionError) as exc_info:
        await _client(hass).async_get_vehicle_data(VIN)
    assert VIN not in str(exc_info.value)


async def test_server_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
) -> None:
    """HTTP 5xx is treated as a connection problem."""
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    aioclient_mock.get(CONSENT_URL, status=HTTPStatus.BAD_GATEWAY, text="Bad gateway")

    with pytest.raises(PleosConnectionError):
        await _client(hass).async_get_vehicles()


def test_vehicle_display_name_fallbacks() -> None:
    """Nickname, then name, then sellname, then VIN."""
    assert vehicle_display_name({"vin": VIN, "nickname": " ", "name": "Kona"}) == "Kona"
    assert vehicle_display_name({"vin": VIN, "sellname": "IONIQ 6"}) == "IONIQ 6"
    assert vehicle_display_name({"vin": VIN}) == VIN
    assert vehicle_model({"vin": VIN}) is None
