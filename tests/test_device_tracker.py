"""Tests for the device tracker platform."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_NOT_HOME, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import register_pleos, setup_entry

TRACKER = "device_tracker.ioniq_5_location"


async def test_location(
    hass: HomeAssistant, mock_pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """The fixture position is shown with its extra attributes."""
    assert await setup_entry(hass, config_entry)

    tracker = hass.states.get(TRACKER)
    assert tracker.state == STATE_NOT_HOME
    assert tracker.attributes["latitude"] == 52.5
    assert tracker.attributes["longitude"] == 13.4
    assert tracker.attributes["source_type"] == "gps"
    assert tracker.attributes["altitude"] == 20
    assert tracker.attributes["heading"] == 90
    assert tracker.attributes["speed"] == 0
    assert tracker.attributes["speed_unit"] == "km/h"
    assert tracker.attributes["last_update"] == "2026-01-01T00:00:00+00:00"


async def test_location_home(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """A position in the home zone is "home"; strings are parsed."""
    vehicle_payloads["locations"]["data"]["location"].update(
        latitude=str(hass.config.latitude), longitude=str(hass.config.longitude)
    )
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, config_entry)

    assert hass.states.get(TRACKER).state == "home"


@pytest.mark.parametrize(
    "location",
    [
        {"latitude": 52.5, "longitude": 13.4, "type": 1},
        {"latitude": 0, "longitude": 0},
        {"latitude": 95, "longitude": 13.4},
        {"latitude": "invalid", "longitude": 13.4},
    ],
    ids=["not_wgs84", "null_island", "out_of_range", "invalid"],
)
async def test_location_unusable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
    location: dict[str, Any],
) -> None:
    """Unusable fixes make the tracker unknown, but it still exists."""
    vehicle_payloads["locations"]["data"]["location"] = location
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, config_entry)

    tracker = hass.states.get(TRACKER)
    assert tracker.state == STATE_UNKNOWN
    assert "latitude" not in tracker.attributes


async def test_no_location_block(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Without location data there is no tracker."""
    vehicle_payloads["locations"] = {"error": {"code": "4045", "message": "No data"}}
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, config_entry)

    assert hass.states.get(TRACKER) is None
    assert hass.states.get("sensor.ioniq_5_ev_range") is not None
