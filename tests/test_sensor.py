"""Tests for the sensor platform."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.const import DOMAIN, VEHICLE_MODEL, VEHICLE_NAME, VEHICLE_TYPE

from .conftest import VIN, entry_data, register_pleos, setup_entry


@pytest.mark.parametrize(
    ("entity_id", "state", "unit"),
    [
        ("sensor.ioniq_5_ev_battery_level", "40", "%"),
        # 273960 kJ as in the API documentation.
        ("sensor.ioniq_5_ev_battery_capacity", "76.1", "kWh"),
        ("sensor.ioniq_5_ac_charge_limit", "80", "%"),
        ("sensor.ioniq_5_dc_charge_limit", "90", "%"),
        ("sensor.ioniq_5_estimated_charge_duration", "10", "min"),
        ("sensor.ioniq_5_charging_status", "charging", None),
        # Ranges come as strings.
        ("sensor.ioniq_5_ev_range", "106", "km"),
        ("sensor.ioniq_5_total_driving_range", "106", "km"),
        ("sensor.ioniq_5_odometer", "1000", "km"),
        # Raw kpa values are multiplied by 5; 255 means no reading.
        ("sensor.ioniq_5_tire_pressure_front_left", "250", "kPa"),
        ("sensor.ioniq_5_tire_pressure_front_right", "250", "kPa"),
        ("sensor.ioniq_5_tire_pressure_rear_left", "245", "kPa"),
        ("sensor.ioniq_5_tire_pressure_rear_right", STATE_UNKNOWN, "kPa"),
        ("sensor.ioniq_5_set_temperature", "21", "°C"),
        ("sensor.ioniq_5_outside_temperature", "15", "°C"),
        ("sensor.ioniq_5_steering_wheel_heat_level", "off", None),
        ("sensor.ioniq_5_warnings", "washFluid, tirePressureRearLeft", None),
        ("sensor.ioniq_5_last_updated_at", "2026-01-01T00:05:00+00:00", None),
        ("sensor.ioniq_5_location_last_updated", "2026-01-01T00:00:00+00:00", None),
        ("sensor.ioniq_5_vehicle_identification_number", VIN, None),
    ],
)
async def test_sensor_states(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    entity_id: str,
    state: str,
    unit: str | None,
) -> None:
    """Sensors show the fixture values in HA units."""
    assert await setup_entry(hass, config_entry)

    sensor = hass.states.get(entity_id)
    assert sensor is not None, entity_id
    assert sensor.state == state
    assert sensor.attributes.get("unit_of_measurement") == unit


async def test_sensor_registry(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Unique IDs use the VIN; the raw battery ratio is disabled by default."""
    assert await setup_entry(hass, config_entry)

    entry = entity_registry.async_get("sensor.ioniq_5_ev_range")
    assert entry.unique_id == f"{VIN}_ev_driving_range"
    ratio = entity_registry.async_get("sensor.ioniq_5_ev_battery_remaining_ratio")
    assert ratio.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("sensor.ioniq_5_warnings").attributes["warnings"] == [
        "washFluid",
        "tirePressureRearLeft",
    ]


async def test_ev_has_no_fuel_sensors(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """An EV gets no fuel level or fuel range sensor."""
    assert await setup_entry(hass, config_entry)

    unique_ids = {
        entry.unique_id
        for entry in er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    }
    assert f"{VIN}_ev_driving_range" in unique_ids
    assert f"{VIN}_fuel_level" not in unique_ids
    assert f"{VIN}_fuel_driving_range" not in unique_ids


async def test_combustion_vehicle(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
) -> None:
    """A combustion car gets fuel sensors, no EV range, no charge sensors."""
    vehicle_payloads["powertrains"] = {
        "data": {
            "engine": {"fuelLevel": 55},
            "distanceToEmpties": [{"type": "ICE", "value": "420.5", "unit": "mile"}],
        }
    }
    vehicle_payloads["batteries"] = {"data": {}}
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data(
            **{VIN: {VEHICLE_NAME: "Tucson", VEHICLE_MODEL: "TUCSON", VEHICLE_TYPE: "GN"}}
        ),
    )
    entry.add_to_hass(hass)
    assert await setup_entry(hass, entry)

    assert hass.states.get("sensor.tucson_fuel_level").state == "55"
    # Miles are reported; the metric test instance shows kilometres.
    fuel_range = hass.states.get("sensor.tucson_fuel_driving_range")
    assert fuel_range.attributes["unit_of_measurement"] == "km"
    assert float(fuel_range.state) == pytest.approx(420.5 * 1.609344, abs=0.01)
    # The only range is also the total range.
    total = hass.states.get("sensor.tucson_total_driving_range")
    assert total.state == fuel_range.state
    assert hass.states.get("sensor.tucson_ev_range") is None
    assert hass.states.get("sensor.tucson_estimated_charge_duration") is None


@pytest.mark.parametrize(
    ("tire", "expected", "unit"),
    [
        ({"left": 24, "right": 255, "unit": "bar"}, ("2.4", STATE_UNKNOWN), "bar"),
        # psi as is; the metric test instance converts it to kPa.
        ({"left": 36, "right": 35, "unit": "psi"}, ("248.211252", "241.316495"), "kPa"),
    ],
)
async def test_tire_units(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
    tire: dict[str, Any],
    expected: tuple[str, str],
    unit: str,
) -> None:
    """Bar values are divided by ten, psi values are used as is."""
    vehicle_payloads["status"]["data"]["tire"] = [tire, tire]
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, config_entry)

    left = hass.states.get("sensor.ioniq_5_tire_pressure_front_left")
    right = hass.states.get("sensor.ioniq_5_tire_pressure_front_right")
    assert (left.state, right.state) == expected
    assert left.attributes["unit_of_measurement"] == unit


async def test_range_without_value(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """A range of "-" is unknown, but the sensor exists; no warnings = "none"."""
    vehicle_payloads["powertrains"]["data"]["distanceToEmpties"] = [
        {"type": "EV", "value": "-", "unit": "km"}
    ]
    vehicle_payloads["status"]["data"]["warnings"] = []
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, config_entry)

    assert hass.states.get("sensor.ioniq_5_ev_range").state == STATE_UNKNOWN
    assert hass.states.get("sensor.ioniq_5_warnings").state == "none"
