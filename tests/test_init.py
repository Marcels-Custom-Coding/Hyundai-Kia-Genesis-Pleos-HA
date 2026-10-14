"""Setup, entities, errors and take-over."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.const import (
    CONF_MIGRATE_VINS,
    CONF_VEHICLES,
    DOMAIN,
    LEGACY_DOMAIN,
)
from custom_components.hkg_pleos.diagnostics import async_get_config_entry_diagnostics
from custom_components.hkg_pleos.migrate import find_device
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

from .conftest import VIN, error, load, mock_pleos


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(
    hass: HomeAssistant, pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    def state(entity_id: str) -> str:
        current = hass.states.get(entity_id)
        assert current is not None, entity_id
        return current.state

    # Same entity ids as Hyundai / Kia Connect
    assert state("sensor.my_car_ev_battery_level") == "30.5"
    assert state("sensor.my_car_ev_range") == "106"
    assert (
        hass.states.get("sensor.my_car_ev_range").attributes["unit_of_measurement"]
        == "km"
    )
    assert state("sensor.my_car_total_driving_range") == "106"
    assert state("sensor.my_car_odometer") == "6549.2"
    assert state("sensor.my_car_estimated_charge_duration") == "54"
    assert state("sensor.my_car_vehicle_identification_number") == VIN
    # Home Assistant shows pressure in kPa on metric systems: 40 psi, 36/10 bar.
    assert round(float(state("sensor.my_car_tire_pressure_front_left"))) == 276
    # bar is metric already and stays as it is.
    assert state("sensor.my_car_tire_pressure_rear_left") == "3.6"
    # 255 means "no reading": no entity until a real value arrives.
    assert hass.states.get("sensor.my_car_tire_pressure_rear_right") is None
    assert state("sensor.my_car_outside_temperature") == "30"
    assert state("sensor.my_car_set_temperature") == "17"
    assert state("sensor.my_car_front_right_seat") == "low"
    assert state("sensor.my_car_charging_status") == "fast_charging"
    assert state("sensor.my_car_ac_charge_limit") == "100"
    assert state("sensor.my_car_dc_charge_limit") == "80"
    assert state("sensor.my_car_last_updated_at") == "2025-09-01T09:10:00+00:00"

    assert state("binary_sensor.my_car_ev_battery_charge") == STATE_ON
    assert state("binary_sensor.my_car_ev_battery_plug") == STATE_ON
    assert state("binary_sensor.my_car_front_right_door") == STATE_ON
    assert state("binary_sensor.my_car_front_left_door") == STATE_OFF
    # Lock sensors are on when unlocked
    assert state("binary_sensor.my_car_front_left_door_lock") == STATE_OFF
    assert state("binary_sensor.my_car_front_right_door_lock") == STATE_ON
    assert state("binary_sensor.my_car_locked") == STATE_ON
    assert state("binary_sensor.my_car_washer_fluid_warning") == STATE_ON
    assert state("binary_sensor.my_car_brake_fluid_warning") == STATE_OFF
    assert state("binary_sensor.my_car_engine") == STATE_ON
    assert state("binary_sensor.my_car_front_right_seat_heater") == STATE_ON
    assert state("binary_sensor.my_car_air_conditioner") == STATE_ON

    tracker = hass.states.get("device_tracker.my_car_location")
    assert tracker.attributes["latitude"] == 49.9749
    assert tracker.attributes["heading"] == 180

    # Values the car does not report get no entity (EV: no fuel).
    assert hass.states.get("sensor.my_car_fuel_level") is None
    assert hass.states.get("binary_sensor.my_car_fuel_low_level") is None
    assert hass.states.get("sensor.my_car_car_battery_level") is None

    device = find_device(hass, (DOMAIN, VIN))
    assert device.name == "My Car"
    assert device.model == "IONIQ 5"
    assert device.manufacturer == "Hyundai"
    assert (DOMAIN, f"vin:{VIN}") in device.identifiers

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    text = str(diagnostics)
    assert VIN not in text
    assert "49.9749" not in text
    assert "client-secret" not in text


async def test_entities_appear_later(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_pleos(aioclient_mock, endpoints={"locations": (404, error("4045"))})
    await _setup(hass, config_entry)
    assert hass.states.get("device_tracker.my_car_location") is None
    assert hass.states.get("sensor.my_car_ev_battery_level") is not None

    mock_pleos(aioclient_mock)
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("device_tracker.my_car_location") is not None


async def test_endpoint_failure_keeps_old_values(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_pleos(aioclient_mock)
    await _setup(hass, config_entry)
    mock_pleos(aioclient_mock, endpoints={"batteries": (500, error("5001"))})
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.my_car_ev_battery_level").state == "30.5"


async def test_key_revoked(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    mock_pleos(aioclient_mock, token_status=404, token_json=error("40404"))
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows and flows[0]["context"]["source"] == "reauth"
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"auth_failed_{config_entry.entry_id}"
    )
    assert issue is not None


async def test_key_revoked_while_running(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_pleos(aioclient_mock)
    await _setup(hass, config_entry)
    endpoints = {
        ep: (400, error("40003"))
        for ep in ("batteries", "powertrains", "locations", "driving", "status")
    }
    mock_pleos(
        aioclient_mock, token_status=404, token_json=error("40404"), endpoints=endpoints
    )
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_vehicle_removed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    mock_pleos(aioclient_mock, consent={"data": {"vehicles": []}})
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    issue_id = f"vehicle_removed_{config_entry.entry_id}_{VIN}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.is_fixable

    from custom_components.hkg_pleos.repairs import async_create_fix_flow

    flow = await async_create_fix_flow(hass, issue_id, issue.data)
    flow.hass = hass
    flow.handler = DOMAIN
    flow.issue_id = issue_id
    result = await flow.async_step_init()
    assert result["description_placeholders"]["name"] == "My Car"
    await flow.async_step_confirm({})
    await hass.async_block_till_done()
    assert config_entry.data[CONF_VEHICLES] == {}


async def test_take_over_kia_uvo(
    hass: HomeAssistant, pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    old_entry = MockConfigEntry(domain=LEGACY_DOMAIN)
    old_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=old_entry.entry_id,
        identifiers={(LEGACY_DOMAIN, "abc-1"), (LEGACY_DOMAIN, f"vin:{VIN}")},
        name="Ioniq",
    )
    registry = er.async_get(hass)
    old_ids = {}
    for domain, key, object_id in (
        ("sensor", "ev_battery_percentage", "ioniq_ev_battery_level"),
        ("sensor", "_odometer", "ioniq_odometer"),
        ("binary_sensor", "is_locked", "ioniq_locked"),
        ("binary_sensor", "front_left_door_is_locked", "ioniq_front_left_door_lock"),
        ("device_tracker", "location", "ioniq_location"),
        ("lock", "door_lock", "ioniq_door_lock"),
    ):
        old_ids[key] = registry.async_get_or_create(
            domain,
            LEGACY_DOMAIN,
            f"kia_uvo_abc-1_{key}",
            suggested_object_id=object_id,
            device_id=device.id,
            config_entry=old_entry,
        ).entity_id
    registry.async_update_entity(old_ids["_odometer"], area_id="garage")

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=config_entry.unique_id,
        data={**config_entry.data, CONF_MIGRATE_VINS: [VIN]},
        options=config_entry.options,
    )
    await _setup(hass, config_entry)

    for key, entity_id in old_ids.items():
        entry = registry.async_get(entity_id)
        if key == "door_lock":
            # Nothing to take over: Pleos is read-only.
            assert entry.platform == LEGACY_DOMAIN
            continue
        assert entry.platform == DOMAIN, entity_id
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.states.get("sensor.ioniq_ev_battery_level").state == "30.5"
    assert registry.async_get("sensor.ioniq_odometer").area_id == "garage"
    assert CONF_MIGRATE_VINS not in config_entry.data
    # Not taken over entities keep the new naming.
    assert hass.states.get("sensor.my_car_outside_temperature") is not None


async def test_unload(
    hass: HomeAssistant, pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert load("token")
