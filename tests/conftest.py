"""Shared fixtures for the Hyundai Kia Genesis (Pleos) tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.hkg_pleos.const import (
    API_HOST,
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLES,
    DOMAIN,
    ENDPOINTS,
    VEHICLE_MODEL,
    VEHICLE_NAME,
    VEHICLE_TYPE,
)

FIXTURES = Path(__file__).parent / "fixtures"

BRAND = "hyundai"
CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
VIN = "KMHTEST0000000001"

TOKEN_URL = f"{API_HOST}/v1/auth/personal-token"
CONSENT_URL = f"{API_HOST}/v1/vehicles/consent"

ENTRY_TITLE = "Hyundai \N{EN DASH} IONIQ 5"


def entry_data(**vehicles: dict[str, Any]) -> dict[str, Any]:
    """Config entry data with the fixture key and the given vehicles.

    Without vehicles, the fixture vehicle (VIN) is used.
    """
    return {
        CONF_BRAND: BRAND,
        CONF_CLIENT_ID: CLIENT_ID,
        CONF_CLIENT_SECRET: CLIENT_SECRET,
        CONF_VEHICLES: vehicles
        or {VIN: {VEHICLE_NAME: "IONIQ 5", VEHICLE_MODEL: "IONIQ 5", VEHICLE_TYPE: "EV"}},
    }


def load_json(name: str) -> dict[str, Any]:
    """Load a JSON fixture from tests/fixtures."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def endpoint_url(endpoint: str, vin: str = VIN) -> str:
    """URL of a per-vehicle endpoint."""
    return f"{API_HOST}/v1/vehicles/{vin}/{endpoint}"


def sequence(method: str, url: str, *answers: tuple[int, Any]) -> Callable[..., Any]:
    """Side effect returning the given (status, json) answers in order.

    The last answer is repeated once the list is used up.
    """
    remaining = list(answers)

    async def side_effect(*_args: Any) -> AiohttpClientMockResponse:
        status, payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return AiohttpClientMockResponse(method, URL(url), status=status, json=payload)

    return side_effect


def register_pleos(
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    vin: str = VIN,
) -> None:
    """Register answers for the token, vehicle list and snapshot endpoints."""
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    aioclient_mock.get(CONSENT_URL, json=consent_payload)
    for endpoint, payload in vehicle_payloads.items():
        aioclient_mock.get(endpoint_url(endpoint, vin), json=payload)


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    """Set up a config entry and wait until its platforms are done."""
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return result


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom integrations in every test."""
    return


@pytest.fixture
def token_payload() -> dict[str, Any]:
    """Answer of the token endpoint."""
    return load_json("token")


@pytest.fixture
def consent_payload() -> dict[str, Any]:
    """Answer of the vehicle list endpoint."""
    return load_json("consent")


@pytest.fixture
def vehicle_payloads() -> dict[str, dict[str, Any]]:
    """Answers of all per-vehicle snapshot endpoints, keyed by endpoint."""
    return {endpoint: load_json(endpoint) for endpoint in ENDPOINTS}


@pytest.fixture
def mock_pleos(
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
) -> AiohttpClientMocker:
    """Answer all Pleos API calls with the sample payloads."""
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    return aioclient_mock


@pytest.fixture
def mock_pleos_client(
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
) -> Generator[AsyncMock]:
    """Patch the PleosClient methods (for config flow / platform tests)."""
    data = {endpoint: payload["data"] for endpoint, payload in vehicle_payloads.items()}
    with (
        patch(
            "custom_components.hkg_pleos.api.PleosClient.async_login",
            AsyncMock(return_value=None),
        ) as login,
        patch(
            "custom_components.hkg_pleos.api.PleosClient.async_get_vehicles",
            AsyncMock(return_value=consent_payload["data"]["vehicles"]),
        ),
        patch(
            "custom_components.hkg_pleos.api.PleosClient.async_get_vehicle_data",
            AsyncMock(return_value=data),
        ),
    ):
        yield login


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry for the fixture key and vehicle, added to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=ENTRY_TITLE,
        unique_id=f"{BRAND}_{CLIENT_ID}",
        data=entry_data(),
        options={CONF_SCAN_INTERVAL: 10},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip setting up the integration (config flow tests)."""
    with patch(
        "custom_components.hkg_pleos.async_setup_entry", AsyncMock(return_value=True)
    ) as setup:
        yield setup
