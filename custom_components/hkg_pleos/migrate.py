"""Optional takeover of entity IDs from the "Hyundai / Kia Connect" integration.

Only runs for VINs the user agreed to in the config flow. For every entity
this integration will create, the matching kia_uvo registry entry (exact
unique_id ``kia_uvo_<vehicle id>_<legacy_key>``) is removed and the new entity
is registered under the old entity_id, so history, automations and dashboards
keep working.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, LEGACY_DOMAIN
from .coordinator import PleosConfigEntry, PleosCoordinator, PleosRuntimeData
from .entity import PleosEntityDescription

_LOGGER = logging.getLogger(__name__)

VIN_PREFIX = "vin:"

# How long to wait for removed kia_uvo entities to leave the state machine.
_STATE_RELEASE_TIMEOUT = 5.0
_STATE_RELEASE_STEP = 0.05


def legacy_device(hass: HomeAssistant, vin: str) -> dr.DeviceEntry | None:
    """kia_uvo device of a VIN, if there is one."""
    dev_reg = dr.async_get(hass)
    return dev_reg.async_get_device(identifiers={(LEGACY_DOMAIN, f"{VIN_PREFIX}{vin}")})


def legacy_vehicle_id(device: dr.DeviceEntry) -> str | None:
    """kia_uvo vehicle id from the device's non-VIN identifier."""
    for domain, identifier in device.identifiers:
        if domain == LEGACY_DOMAIN and not identifier.startswith(VIN_PREFIX):
            return identifier
    return None


def legacy_device_vins(hass: HomeAssistant, vins: Iterable[str]) -> set[str]:
    """VINs that have a kia_uvo device (with a usable vehicle id)."""
    found: set[str] = set()
    for vin in vins:
        device = legacy_device(hass, vin)
        if device is not None and legacy_vehicle_id(device) is not None:
            found.add(vin)
    return found


@dataclass(frozen=True)
class _Planned:
    platform: str
    key: str
    legacy_key: str


def _planned_entities(coordinator: PleosCoordinator) -> list[_Planned]:
    """Entities with a kia_uvo counterpart that will be created for a vehicle."""
    from .binary_sensor import (  # noqa: PLC0415
        BINARY_SENSOR_DESCRIPTIONS,
        binary_sensor_exists,
    )
    from .device_tracker import TRACKER_DESCRIPTIONS, tracker_exists  # noqa: PLC0415
    from .sensor import SENSOR_DESCRIPTIONS, sensor_exists  # noqa: PLC0415

    groups: list[tuple[Platform, Iterable[PleosEntityDescription], Callable[[Any, Any], bool]]] = [
        (Platform.SENSOR, SENSOR_DESCRIPTIONS, sensor_exists),
        (Platform.BINARY_SENSOR, BINARY_SENSOR_DESCRIPTIONS, binary_sensor_exists),
        (Platform.DEVICE_TRACKER, TRACKER_DESCRIPTIONS, tracker_exists),
    ]
    planned: list[_Planned] = []
    for platform, descriptions, exists in groups:
        for description in descriptions:
            if description.legacy_key is None:
                continue
            try:
                created = exists(description, coordinator)
            except (KeyError, IndexError, TypeError, ValueError):
                created = False
            if created:
                planned.append(_Planned(platform, description.key, description.legacy_key))
    return planned


async def _async_wait_released(hass: HomeAssistant, entity_ids: list[str]) -> None:
    """Give removed kia_uvo entities time to drop their states."""
    loop_time = asyncio.get_running_loop().time
    deadline = loop_time() + _STATE_RELEASE_TIMEOUT
    while any(not hass.states.async_available(entity_id) for entity_id in entity_ids):
        if loop_time() >= deadline:
            return
        await asyncio.sleep(_STATE_RELEASE_STEP)


def _carry_over(old: er.RegistryEntry) -> dict[str, Any]:
    """User settings of the old entry worth keeping."""
    changes: dict[str, Any] = {}
    if old.name is not None:
        changes["name"] = old.name
    if old.icon is not None:
        changes["icon"] = old.icon
    if old.area_id is not None:
        changes["area_id"] = old.area_id
    if old.aliases:
        changes["aliases"] = set(old.aliases)
    if old.labels:
        changes["labels"] = set(old.labels)
    if old.hidden_by is er.RegistryEntryHider.USER:
        changes["hidden_by"] = old.hidden_by
    if old.disabled_by is er.RegistryEntryDisabler.USER:
        changes["disabled_by"] = old.disabled_by
    return changes


async def async_migrate_legacy_entities(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    runtime: PleosRuntimeData,
    vins: list[str],
) -> None:
    """Take over entity IDs of kia_uvo entities for the given VINs."""
    ent_reg = er.async_get(hass)

    # (old entry, platform, new unique_id) of everything that is taken over.
    takeovers: list[tuple[er.RegistryEntry, str, str]] = []
    for vin in vins:
        coordinator = runtime.coordinators.get(vin)
        if coordinator is None:
            continue
        device = legacy_device(hass, vin)
        if device is None or (vehicle_id := legacy_vehicle_id(device)) is None:
            _LOGGER.debug("No kia_uvo device found for a vehicle, nothing to take over")
            continue
        for planned in _planned_entities(coordinator):
            old_unique_id = f"{LEGACY_DOMAIN}_{vehicle_id}_{planned.legacy_key}"
            old_entity_id = ent_reg.async_get_entity_id(
                planned.platform, LEGACY_DOMAIN, old_unique_id
            )
            if old_entity_id is None:
                continue
            old = ent_reg.async_get(old_entity_id)
            if old is None:
                continue
            takeovers.append((old, planned.platform, f"{vin}_{planned.key}"))

    if not takeovers:
        return

    for old, _, _ in takeovers:
        ent_reg.async_remove(old.entity_id)
    await _async_wait_released(hass, [old.entity_id for old, _, _ in takeovers])

    taken: list[str] = []
    for old, platform, new_unique_id in takeovers:
        new = ent_reg.async_get_or_create(
            platform,
            DOMAIN,
            new_unique_id,
            config_entry=entry,
            suggested_object_id=old.entity_id.split(".", 1)[1],
        )
        changes = _carry_over(old)
        if new.entity_id != old.entity_id:
            changes["new_entity_id"] = old.entity_id
        if changes:
            try:
                new = ent_reg.async_update_entity(new.entity_id, **changes)
            except ValueError as err:
                _LOGGER.warning("Could not take over %s: %s", old.entity_id, err)
                continue
        for domain, options in old.options.items():
            if domain == platform and options:
                ent_reg.async_update_entity_options(new.entity_id, domain, dict(options))
        taken.append(new.entity_id)

    if taken:
        _LOGGER.info(
            "Took over %d entities from Hyundai / Kia Connect: %s",
            len(taken),
            ", ".join(sorted(taken)),
        )
