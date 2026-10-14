"""Shared fixtures for the Hyundai Kia Genesis (Pleos) tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.hkg_pleos.const import API_HOST, ENDPOINTS

FIXTURES = Path(__file__).parent / "fixtures"

BRAND = "hyundai"
CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
VIN = "KMHTEST0000000001"

TOKEN_URL = f"{API_HOST}/v1/auth/personal-token"
CONSENT_URL = f"{API_HOST}/v1/vehicles/consent"


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
    aioclient_mock.post(TOKEN_URL, json=token_payload)
    aioclient_mock.get(CONSENT_URL, json=consent_payload)
    for endpoint, payload in vehicle_payloads.items():
        aioclient_mock.get(endpoint_url(endpoint), json=payload)
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
