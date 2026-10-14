"""Take over entity ids from the Hyundai / Kia Connect integration (kia_uvo).

Only runs when the user agreed during setup. The old registry entries are
removed and ours are registered under exactly the same entity id, so history,
automations and dashboards keep working.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, LEGACY_DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Mapping:
    """Our entity and the kia_uvo key it replaces."""

    platform: Platform
    key: str
    uvo_key: str


def mappings() -> list[Mapping]:
    """All entities that have a kia_uvo counterpart."""
    from .binary_sensor import BINARY_SENSORS
    from .device_tracker import LOCATION_KEY
    from .sensor import SENSORS, VIN_SENSOR

    result = [
        Mapping(Platform.SENSOR, desc.key, desc.uvo_key)
        for desc in (*SENSORS, VIN_SENSOR)
        if desc.uvo_key
    ]
    result += [
        Mapping(Platform.BINARY_SENSOR, desc.key, desc.uvo_key)
        for desc in BINARY_SENSORS
        if desc.uvo_key
    ]
    result.append(Mapping(Platform.DEVICE_TRACKER, LOCATION_KEY, LOCATION_KEY))
    return result


@callback
def legacy_device(hass: HomeAssistant, vin: str) -> dr.DeviceEntry | None:
    """Find the kia_uvo device of a car by its VIN."""
    devices = dr.async_get(hass).devices.values()
    if device := find_device(hass, (LEGACY_DOMAIN, f"vin:{vin}")):
        return device
    for device in devices:
        if device.serial_number == vin and any(
            domain == LEGACY_DOMAIN for domain, _ in device.identifiers
        ):
            return device
    return None


@callback
def find_device(
    hass: HomeAssistant, identifier: tuple[str, str]
) -> dr.DeviceEntry | None:
    """Device with this identifier (works on all supported HA versions)."""
    for device in dr.async_get(hass).devices.values():
        if identifier in device.identifiers:
            return device
    return None


@callback
def legacy_vins(hass: HomeAssistant, vins: Iterable[str]) -> list[str]:
    """VINs that have a kia_uvo device with entities."""
    registry = er.async_get(hass)
    result = []
    for vin in vins:
        device = legacy_device(hass, vin)
        if device and er.async_entries_for_device(
            registry, device.id, include_disabled_entities=True
        ):
            result.append(vin)
    return result


def _uvo_key(unique_id: str) -> str | None:
    """kia_uvo builds unique ids as kia_uvo_<vehicle id>_<key>."""
    prefix = f"{LEGACY_DOMAIN}_"
    if not unique_id.startswith(prefix):
        return None
    _, sep, key = unique_id[len(prefix) :].partition("_")
    return key if sep else None


@callback
def async_take_over(
    hass: HomeAssistant, config_entry_id: str, vins: Iterable[str]
) -> int:
    """Move the entity ids of the kia_uvo entities over to ours."""
    registry = er.async_get(hass)
    moved = 0
    by_uvo_key = {(m.platform.value, m.uvo_key): m for m in mappings()}
    for vin in vins:
        device = legacy_device(hass, vin)
        if device is None:
            continue
        for old in er.async_entries_for_device(
            registry, device.id, include_disabled_entities=True
        ):
            uvo_key = _uvo_key(old.unique_id)
            mapping = by_uvo_key.get((old.domain, uvo_key or ""))
            if mapping is None:
                continue
            new_unique_id = f"{vin}_{mapping.key}"
            if registry.async_get_entity_id(old.domain, DOMAIN, new_unique_id):
                continue
            entity_id = old.entity_id
            registry.async_remove(entity_id)
            new = registry.async_get_or_create(
                old.domain,
                DOMAIN,
                new_unique_id,
                suggested_object_id=entity_id.split(".", 1)[1],
                config_entry=hass.config_entries.async_get_entry(config_entry_id),
            )
            if new.entity_id != entity_id:
                # Someone grabbed the id meanwhile; nothing else to keep.
                _LOGGER.warning("Could not keep %s, got %s", entity_id, new.entity_id)
            registry.async_update_entity(
                new.entity_id,
                name=old.name,
                icon=old.icon,
                area_id=old.area_id,
                labels=old.labels,
                aliases=old.aliases,
            )
            moved += 1
    _LOGGER.info("Took over %s entity ids from %s", moved, LEGACY_DOMAIN)
    return moved
