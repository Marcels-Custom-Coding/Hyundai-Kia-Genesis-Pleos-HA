"""Shared fixtures: Pleos answers as documented, mocked on the HTTP level."""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.const import (
    API_HOST,
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLES,
    DOMAIN,
    ENDPOINTS,
)

pytest_plugins = ["pytest_homeassistant_custom_component"]

FIXTURES = Path(__file__).parent / "fixtures"
VIN = "KMHTEST1234567890"
CLIENT_ID = "client-id"
CLIENT_SECRET = "client-secret"


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def error(code: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": "x", "details": [], "requestId": "r"}}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    yield


def mock_pleos(
    aioclient_mock: AiohttpClientMocker,
    *,
    vin: str = VIN,
    consent: dict[str, Any] | None = None,
    token_status: int = 200,
    token_json: dict[str, Any] | None = None,
    endpoints: dict[str, tuple[int, dict[str, Any]]] | None = None,
) -> None:
    """Register the Pleos URLs on the HTTP mock."""
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{API_HOST}/v1/auth/personal-token",
        status=token_status,
        json=token_json if token_json is not None else load("token"),
    )
    aioclient_mock.get(
        f"{API_HOST}/v1/vehicles/consent",
        json=consent if consent is not None else load("consent"),
    )
    endpoints = endpoints or {}
    for endpoint in ENDPOINTS:
        status, body = endpoints.get(endpoint, (200, load(endpoint)))
        aioclient_mock.get(
            f"{API_HOST}/v1/vehicles/{vin}/{endpoint}", status=status, json=body
        )


@pytest.fixture
def pleos(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    mock_pleos(aioclient_mock)
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Hyundai – My Car",
        unique_id=f"hyundai_{CLIENT_ID}",
        data={
            CONF_BRAND: "hyundai",
            CONF_CLIENT_ID: CLIENT_ID,
            CONF_CLIENT_SECRET: CLIENT_SECRET,
            CONF_VEHICLES: {
                VIN: {
                    "name": "My Car",
                    "model": "IONIQ 5",
                    "model_code": "NE(NE)",
                    "type": "EV",
                }
            },
        },
        options={CONF_SCAN_INTERVAL: 10},
    )
