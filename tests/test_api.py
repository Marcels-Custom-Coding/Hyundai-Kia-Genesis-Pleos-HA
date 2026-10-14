"""Pleos client: token handling and error codes."""

from __future__ import annotations

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.api import (
    PleosAuthError,
    PleosClient,
    PleosConnectionError,
    PleosVehicleGoneError,
)
from custom_components.hkg_pleos.const import API_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import VIN, error, load, mock_pleos


def _client(hass: HomeAssistant) -> PleosClient:
    return PleosClient(async_get_clientsession(hass), "hyundai", " id ", "secret ")


async def test_token_is_reused(hass: HomeAssistant, pleos: AiohttpClientMocker) -> None:
    client = _client(hass)
    assert (await client.async_get_vehicles())[0]["vin"] == VIN
    data = await client.async_get_endpoint(VIN, "batteries")
    assert data["charge"]["stateOfCharge"] == 30.5
    logins = [c for c in pleos.mock_calls if c[0] == "POST"]
    assert len(logins) == 1
    # Brand header and trimmed credentials
    assert logins[0][2] == {"clientId": "id", "clientSecret": "secret"}
    assert logins[0][3]["Brand"] == "hyundai"
    assert pleos.mock_calls[-1][3]["Authorization"] == "Bearer token-1"


async def test_expired_token_is_renewed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    client = _client(hass)
    mock_pleos(aioclient_mock)
    await client.async_login()

    calls = {"n": 0}

    async def batteries(method, url, data):  # noqa: ANN001
        calls["n"] += 1
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        if calls["n"] == 1:
            return AiohttpClientMockResponse(
                method, url, status=400, json=error("40003")
            )
        return AiohttpClientMockResponse(method, url, json=load("batteries"))

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{API_HOST}/v1/auth/personal-token", json=load("token"))
    aioclient_mock.get(f"{API_HOST}/v1/vehicles/{VIN}/batteries", side_effect=batteries)
    data = await client.async_get_endpoint(VIN, "batteries")
    assert data is not None
    assert calls["n"] == 2
    assert [c[0] for c in aioclient_mock.mock_calls] == ["GET", "POST", "GET"]


async def test_wrong_secret(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_pleos(aioclient_mock, token_status=404, token_json=error("40404"))
    with pytest.raises(PleosAuthError):
        await _client(hass).async_get_vehicles()


async def test_server_error_is_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_pleos(aioclient_mock, token_status=500, token_json=error("50001"))
    with pytest.raises(PleosConnectionError):
        await _client(hass).async_get_vehicles()


async def test_network_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{API_HOST}/v1/auth/personal-token", exc=aiohttp.ClientConnectionError()
    )
    with pytest.raises(PleosConnectionError):
        await _client(hass).async_login()


async def test_no_data_and_vehicle_gone(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_pleos(
        aioclient_mock,
        endpoints={
            "batteries": (404, error("4045")),
            "status": (410, error("4101")),
        },
    )
    client = _client(hass)
    assert await client.async_get_endpoint(VIN, "batteries") is None
    with pytest.raises(PleosVehicleGoneError):
        await client.async_get_endpoint(VIN, "status")
