"""Entities for readings that the car only reports now and then."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import register_pleos, setup_entry

OUTSIDE = "sensor.ioniq_5_outside_temperature"
HEATER = "binary_sensor.ioniq_5_steering_wheel_heater"


def _without_readings(payloads: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    missing = copy.deepcopy(payloads)
    status = missing["status"]["data"]
    status["outsideTemperature"] = {"value": None, "unit": "C"}
    status["steeringWheelHeat"] = None
    return missing


async def test_entity_added_when_reading_appears(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """A reading missing at startup creates its entity on a later refresh."""
    register_pleos(
        aioclient_mock, token_payload, consent_payload, _without_readings(vehicle_payloads)
    )
    assert await setup_entry(hass, config_entry)
    assert hass.states.get(OUTSIDE) is None
    assert hass.states.get(HEATER) is None

    aioclient_mock.clear_requests()
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    coordinator = next(iter(config_entry.runtime_data.coordinators.values()))
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(OUTSIDE).state == "15"
    assert hass.states.get(HEATER) is not None


async def test_known_entity_kept_when_reading_missing(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """An entity created before stays after a restart without the reading."""
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, config_entry)
    assert hass.states.get(OUTSIDE) is not None
    assert await hass.config_entries.async_unload(config_entry.entry_id)

    aioclient_mock.clear_requests()
    register_pleos(
        aioclient_mock, token_payload, consent_payload, _without_readings(vehicle_payloads)
    )
    assert await setup_entry(hass, config_entry)
    assert hass.states.get(OUTSIDE) is not None
    assert hass.states.get(HEATER) is not None
