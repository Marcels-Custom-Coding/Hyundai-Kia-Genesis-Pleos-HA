"""Tests for the binary sensor platform."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import register_pleos, setup_entry


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payloads: tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]],
    entry: MockConfigEntry,
) -> None:
    register_pleos(aioclient_mock, *payloads)
    assert await setup_entry(hass, entry)


@pytest.fixture
def payloads(
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """The three fixture payload groups, ready to be changed by a test."""
    return token_payload, consent_payload, vehicle_payloads


@pytest.mark.parametrize(
    ("entity_id", "state"),
    [
        # Doors: front row locked, back left closed (unlocked), back right open.
        ("binary_sensor.ioniq_5_front_left_door", STATE_OFF),
        ("binary_sensor.ioniq_5_back_left_door", STATE_OFF),
        ("binary_sensor.ioniq_5_back_right_door", STATE_ON),
        # Lock class: on = unlocked.
        ("binary_sensor.ioniq_5_front_left_door_lock", STATE_OFF),
        ("binary_sensor.ioniq_5_front_right_door_lock", STATE_OFF),
        ("binary_sensor.ioniq_5_back_left_door_lock", STATE_ON),
        ("binary_sensor.ioniq_5_back_right_door_lock", STATE_ON),
        ("binary_sensor.ioniq_5_locked", STATE_ON),
        ("binary_sensor.ioniq_5_hood", STATE_OFF),
        ("binary_sensor.ioniq_5_trunk", STATE_OFF),
        ("binary_sensor.ioniq_5_sunroof", STATE_OFF),
        # Warnings list.
        ("binary_sensor.ioniq_5_washer_fluid_warning", STATE_ON),
        ("binary_sensor.ioniq_5_tire_pressure_rear_left", STATE_ON),
        ("binary_sensor.ioniq_5_tire_pressure_front_left", STATE_OFF),
        ("binary_sensor.ioniq_5_tire_pressure_all", STATE_OFF),
        ("binary_sensor.ioniq_5_smart_key_battery_warning", STATE_OFF),
        ("binary_sensor.ioniq_5_brake_fluid_warning", STATE_OFF),
        ("binary_sensor.ioniq_5_headlamp_status", STATE_OFF),
        ("binary_sensor.ioniq_5_turn_signal_left_front", STATE_OFF),
        ("binary_sensor.ioniq_5_rear_left_lamp_fault", STATE_OFF),
        # Charging.
        ("binary_sensor.ioniq_5_ev_battery_charge", STATE_ON),
        ("binary_sensor.ioniq_5_ev_battery_plug", STATE_ON),
        ("binary_sensor.ioniq_5_v2l_status", STATE_OFF),
        ("binary_sensor.ioniq_5_v2x_status", STATE_OFF),
        # Driving.
        ("binary_sensor.ioniq_5_engine", STATE_OFF),
        ("binary_sensor.ioniq_5_ign3", STATE_ON),
        ("binary_sensor.ioniq_5_accessory", STATE_OFF),
        ("binary_sensor.ioniq_5_sleep_mode_check", STATE_OFF),
        ("binary_sensor.ioniq_5_transmission_condition", STATE_ON),
        # Climate.
        ("binary_sensor.ioniq_5_air_conditioner", STATE_ON),
        ("binary_sensor.ioniq_5_defrost", STATE_OFF),
        ("binary_sensor.ioniq_5_steering_wheel_heater", STATE_OFF),
        ("binary_sensor.ioniq_5_front_left_seat_heater", STATE_ON),
        ("binary_sensor.ioniq_5_front_right_seat_heater", STATE_OFF),
        ("binary_sensor.ioniq_5_rear_right_seat_heater", STATE_OFF),
    ],
)
async def test_binary_sensor_states(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    entity_id: str,
    state: str,
) -> None:
    """Binary sensors show the fixture values."""
    assert await setup_entry(hass, config_entry)

    sensor = hass.states.get(entity_id)
    assert sensor is not None, entity_id
    assert sensor.state == state


async def test_icons_follow_state(
    hass: HomeAssistant, mock_pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """State dependent icons."""
    assert await setup_entry(hass, config_entry)

    assert hass.states.get("binary_sensor.ioniq_5_locked").attributes["icon"] == "mdi:lock-open"
    assert (
        hass.states.get("binary_sensor.ioniq_5_front_left_door_lock").attributes["icon"]
        == "mdi:lock"
    )
    assert (
        hass.states.get("binary_sensor.ioniq_5_front_left_seat_heater").attributes["icon"]
        == "mdi:seat-heater"
    )


async def test_all_doors_locked(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payloads: tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]],
    config_entry: MockConfigEntry,
) -> None:
    """The vehicle is locked (off) only when every door is locked."""
    payloads[2]["status"]["data"]["doors"] = [
        {"left": "locked", "right": "locked"},
        {"left": "locked", "right": "invalid"},
    ]
    await _setup(hass, aioclient_mock, payloads, config_entry)

    # Unknown doors are ignored; a door without reading gets no entity.
    assert hass.states.get("binary_sensor.ioniq_5_locked").state == STATE_OFF
    assert hass.states.get("binary_sensor.ioniq_5_back_left_door_lock").state == STATE_OFF
    assert hass.states.get("binary_sensor.ioniq_5_back_right_door_lock") is None


async def test_fuel_warnings_not_for_ev(
    hass: HomeAssistant, mock_pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """An EV gets no low fuel or engine oil warning."""
    assert await setup_entry(hass, config_entry)

    ids = hass.states.async_entity_ids("binary_sensor")
    assert not [entity_id for entity_id in ids if "fuel_level" in entity_id or "oil" in entity_id]


@pytest.mark.parametrize(
    ("status", "v2l", "v2x"),
    [
        ("v2lOperating", STATE_ON, STATE_OFF),
        ("v2lStop", STATE_OFF, STATE_OFF),
        ("v2xOperating", STATE_OFF, STATE_ON),
        ("notCharging", STATE_OFF, STATE_OFF),
    ],
)
async def test_v2x_status(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payloads: tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]],
    config_entry: MockConfigEntry,
    status: str,
    v2l: str,
    v2x: str,
) -> None:
    """V2L / V2X are on only while operating."""
    charge = payloads[2]["batteries"]["data"]["charge"]
    charge["status"] = status
    charge["charging"] = False
    await _setup(hass, aioclient_mock, payloads, config_entry)

    assert hass.states.get("binary_sensor.ioniq_5_v2l_status").state == v2l
    assert hass.states.get("binary_sensor.ioniq_5_v2x_status").state == v2x
    assert hass.states.get("binary_sensor.ioniq_5_ev_battery_charge").state == STATE_OFF


async def test_lamp_warnings(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payloads: tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]],
    config_entry: MockConfigEntry,
) -> None:
    """Lamp faults come from the warnings list."""
    payloads[2]["status"]["data"]["warnings"] = ["frontHeadLamp", "rearRightStopLamp"]
    await _setup(hass, aioclient_mock, payloads, config_entry)

    assert hass.states.get("binary_sensor.ioniq_5_headlamp_status").state == STATE_ON
    assert hass.states.get("binary_sensor.ioniq_5_rear_right_lamp_fault").state == STATE_ON
    assert hass.states.get("binary_sensor.ioniq_5_rear_left_lamp_fault").state == STATE_OFF
    assert hass.states.get("binary_sensor.ioniq_5_washer_fluid_warning").state == STATE_OFF


async def test_no_warning_list(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payloads: tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]],
    config_entry: MockConfigEntry,
) -> None:
    """Without a warnings list no warning sensors are created."""
    del payloads[2]["status"]["data"]["warnings"]
    await _setup(hass, aioclient_mock, payloads, config_entry)

    assert hass.states.get("binary_sensor.ioniq_5_washer_fluid_warning") is None
    assert hass.states.get("binary_sensor.ioniq_5_headlamp_status") is None
    assert hass.states.get("binary_sensor.ioniq_5_locked") is not None
