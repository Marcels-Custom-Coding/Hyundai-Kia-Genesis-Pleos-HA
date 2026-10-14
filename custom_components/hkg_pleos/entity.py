"""Base entity and the shared entity setup."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BRAND_NAMES, CONF_BRAND, DOMAIN
from .coordinator import PleosConfigEntry, PleosCoordinator
from .data import VehicleData


def device_info(
    entry: PleosConfigEntry, vin: str, vehicle: dict[str, Any]
) -> DeviceInfo:
    """One device per car, keyed by the VIN."""
    return DeviceInfo(
        identifiers={(DOMAIN, vin), (DOMAIN, f"vin:{vin}")},
        manufacturer=BRAND_NAMES.get(entry.data[CONF_BRAND]),
        model=vehicle.get("model") or None,
        model_id=vehicle.get("model_code") or None,
        name=vehicle["name"],
        serial_number=vin,
    )


class PleosEntity(CoordinatorEntity[PleosCoordinator]):
    """Entity of one car."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PleosCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_{key}"
        self._attr_device_info = device_info(
            coordinator.config_entry, coordinator.vin, coordinator.vehicle
        )

    @property
    def vehicle_data(self) -> VehicleData:
        return self.coordinator.data or {}


@callback
def async_add_when_available[D](
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    descriptions: Iterable[D],
    has_value: Callable[[D, VehicleData], bool],
    factory: Callable[[PleosCoordinator, D], Entity],
) -> None:
    """Create entities only for values the car reports.

    A value that is null at start-up (car asleep, endpoint without data yet)
    gets its entity as soon as it shows up in a later update.
    """
    descriptions = tuple(descriptions)
    for coordinator in entry.runtime_data.coordinators.values():
        created: set[int] = set()

        @callback
        def add_new(
            coordinator: PleosCoordinator = coordinator, created: set[int] = created
        ) -> None:
            data = coordinator.data or {}
            new: list[Entity] = []
            for index, description in enumerate(descriptions):
                if index not in created and has_value(description, data):
                    created.add(index)
                    new.append(factory(coordinator, description))
            if new:
                async_add_entities(new)

        add_new()
        entry.async_on_unload(coordinator.async_add_listener(add_new))
