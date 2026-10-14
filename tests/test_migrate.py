"""Tests for taking over entity IDs from the kia_uvo integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.const import CONF_PENDING_MIGRATION, DOMAIN, LEGACY_DOMAIN
from custom_components.hkg_pleos.migrate import legacy_device_vins

from .conftest import BRAND, CLIENT_ID, VIN, entry_data, setup_entry

LEGACY_ID = "abc123"


@pytest.fixture
def legacy_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A kia_uvo entry with a device for the fixture vehicle."""
    entry = MockConfigEntry(domain=LEGACY_DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def legacy_device(hass: HomeAssistant, legacy_entry: MockConfigEntry) -> dr.DeviceEntry:
    """The kia_uvo device of the fixture vehicle."""
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=legacy_entry.entry_id,
        identifiers={(LEGACY_DOMAIN, LEGACY_ID), (LEGACY_DOMAIN, f"vin:{VIN}")},
        name="IONIQ 5",
    )


def _legacy_entity(
    entity_registry: er.EntityRegistry,
    legacy_entry: MockConfigEntry,
    device: dr.DeviceEntry,
    platform: str,
    legacy_key: str,
    object_id: str,
) -> er.RegistryEntry:
    return entity_registry.async_get_or_create(
        platform,
        LEGACY_DOMAIN,
        f"{LEGACY_DOMAIN}_{LEGACY_ID}_{legacy_key}",
        config_entry=legacy_entry,
        device_id=device.id,
        suggested_object_id=object_id,
    )


def _pending_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{BRAND}_{CLIENT_ID}",
        data={**entry_data(), CONF_PENDING_MIGRATION: [VIN]},
    )
    entry.add_to_hass(hass)
    return entry


def test_legacy_device_vins(hass: HomeAssistant, legacy_device: dr.DeviceEntry) -> None:
    """Only VINs with a kia_uvo device are found."""
    assert legacy_device_vins(hass, [VIN, "KMHOTHER000000009"]) == {VIN}


def test_legacy_device_without_vehicle_id(
    hass: HomeAssistant, legacy_entry: MockConfigEntry
) -> None:
    """A device with only the VIN identifier cannot be mapped."""
    dr.async_get(hass).async_get_or_create(
        config_entry_id=legacy_entry.entry_id, identifiers={(LEGACY_DOMAIN, f"vin:{VIN}")}
    )
    assert legacy_device_vins(hass, [VIN]) == set()


async def test_takeover(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    legacy_entry: MockConfigEntry,
    legacy_device: dr.DeviceEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Matching kia_uvo entities hand their entity IDs and settings over."""
    old = _legacy_entity(
        entity_registry,
        legacy_entry,
        legacy_device,
        "sensor",
        "_ev_driving_range",
        "my_car_ev_range",
    )
    entity_registry.async_update_entity(old.entity_id, name="Custom", icon="mdi:car")
    _legacy_entity(entity_registry, legacy_entry, legacy_device, "sensor", "VIN", "my_car_vin")
    _legacy_entity(
        entity_registry,
        legacy_entry,
        legacy_device,
        "binary_sensor",
        "back_right_door_is_open",
        "my_car_back_right_door",
    )
    _legacy_entity(
        entity_registry, legacy_entry, legacy_device, "device_tracker", "location", "my_car"
    )
    # Not created for an EV: stays with kia_uvo.
    _legacy_entity(
        entity_registry, legacy_entry, legacy_device, "sensor", "fuel_level", "my_car_fuel"
    )
    # Only an exact unique_id matches.
    _legacy_entity(
        entity_registry, legacy_entry, legacy_device, "sensor", "x_odometer", "my_car_x_odo"
    )
    hass.states.async_set("sensor.my_car_ev_range", "unavailable", {"restored": True})

    entry = _pending_entry(hass)
    assert await setup_entry(hass, entry)

    taken = entity_registry.async_get("sensor.my_car_ev_range")
    assert taken.platform == DOMAIN
    assert taken.config_entry_id == entry.entry_id
    assert taken.unique_id == f"{VIN}_ev_driving_range"
    assert taken.name == "Custom"
    assert taken.icon == "mdi:car"
    assert hass.states.get("sensor.my_car_ev_range").state == "106"
    assert entity_registry.async_get("sensor.my_car_vin").unique_id == (
        f"{VIN}_vehicle_identification_number"
    )
    assert hass.states.get("binary_sensor.my_car_back_right_door").state == "on"
    assert entity_registry.async_get("device_tracker.my_car").platform == DOMAIN

    assert entity_registry.async_get("sensor.my_car_fuel").platform == LEGACY_DOMAIN
    assert entity_registry.async_get("sensor.my_car_x_odo").platform == LEGACY_DOMAIN
    # The new entity does not also exist under its own ID.
    assert hass.states.get("sensor.ioniq_5_ev_range") is None
    assert CONF_PENDING_MIGRATION not in entry.data


async def test_no_pending_migration_leaves_legacy_alone(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    legacy_entry: MockConfigEntry,
    legacy_device: dr.DeviceEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Without consent nothing is taken over."""
    _legacy_entity(
        entity_registry,
        legacy_entry,
        legacy_device,
        "sensor",
        "_ev_driving_range",
        "my_car_ev_range",
    )
    assert await setup_entry(hass, config_entry)

    assert entity_registry.async_get("sensor.my_car_ev_range").platform == LEGACY_DOMAIN
    assert hass.states.get("sensor.ioniq_5_ev_range").state == "106"


async def test_pending_without_legacy_device(
    hass: HomeAssistant, mock_pleos: AiohttpClientMocker
) -> None:
    """A pending takeover without kia_uvo device is dropped quietly."""
    entry = _pending_entry(hass)
    assert await setup_entry(hass, entry)

    assert hass.states.get("sensor.ioniq_5_ev_range").state == "106"
    assert CONF_PENDING_MIGRATION not in entry.data
