"""Base entity: one device per vehicle (VIN)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BRANDS, DOMAIN
from .coordinator import PleosConfigEntry, PleosCoordinator

type VehicleData = dict[str, dict[str, Any] | None]


@dataclass(frozen=True, kw_only=True)
class PleosEntityDescription(EntityDescription):
    """Common fields of all Pleos entity descriptions.

    ``legacy_key`` is the ``key`` the "Hyundai / Kia Connect" (kia_uvo)
    integration used for the same reading; its unique_id there is
    ``kia_uvo_<vehicle id>_<legacy_key>``. None = no counterpart.
    ``exists_fn`` decides whether the vehicle reports this reading; the
    entity is created as soon as it does (see ``async_add_vehicle_entities``).
    """

    legacy_key: str | None = None
    exists_fn: Callable[[PleosCoordinator], bool] | None = None


def dig(data: Any, *path: str | int) -> Any:
    """Return a nested value or None; "invalid" counts as missing."""
    for key in path:
        try:
            data = data[key]
        except (KeyError, IndexError, TypeError):
            return None
    if data == "invalid":
        return None
    return data


def device_info(coordinator: PleosCoordinator) -> DeviceInfo:
    """Device of a vehicle; identifiers like kia_uvo's VIN identifier."""
    vin = coordinator.vin
    brand = BRANDS.get(coordinator.client.brand, coordinator.client.brand)
    return DeviceInfo(
        identifiers={(DOMAIN, vin), (DOMAIN, f"vin:{vin}")},
        manufacturer=brand,
        model=coordinator.model,
        name=coordinator.vehicle_name,
        serial_number=vin,
    )


class PleosEntity(CoordinatorEntity[PleosCoordinator]):
    """Base class of all entities of a vehicle."""

    _attr_has_entity_name = True
    entity_description: PleosEntityDescription

    def __init__(self, coordinator: PleosCoordinator, description: PleosEntityDescription) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.vin}_{description.key}"
        self._attr_device_info = device_info(coordinator)


def async_add_vehicle_entities[D: PleosEntityDescription](
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    platform: str,
    async_add_entities: Callable[[Iterable[Entity]], None],
    *,
    descriptions: Iterable[D],
    exists: Callable[[D, PleosCoordinator], bool],
    factory: Callable[[PleosCoordinator, D], Entity],
) -> None:
    """Add an entity once its reading shows up, and keep known ones.

    Cars send some readings only now and then (a value can be null on one
    poll and present on the next). Entities are therefore created when a
    reading appears on any refresh, and entities created earlier are kept
    even when the reading is missing at startup.
    """
    descriptions = tuple(descriptions)
    known = {
        reg.unique_id
        for reg in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if reg.domain == platform
    }
    added: set[str] = set()

    @callback
    def _check() -> None:
        new: list[Entity] = []
        for coordinator in entry.runtime_data.coordinators.values():
            for description in descriptions:
                unique_id = f"{coordinator.vin}_{description.key}"
                if unique_id in added:
                    continue
                if unique_id in known or (
                    coordinator.data is not None and exists(description, coordinator)
                ):
                    added.add(unique_id)
                    new.append(factory(coordinator, description))
        if new:
            async_add_entities(new)

    _check()
    for coordinator in entry.runtime_data.coordinators.values():
        entry.async_on_unload(coordinator.async_add_listener(_check))
