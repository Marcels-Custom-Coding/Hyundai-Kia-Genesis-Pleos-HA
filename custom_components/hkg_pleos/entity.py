"""Base entity: one device per vehicle (VIN)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BRANDS, DOMAIN
from .coordinator import PleosCoordinator

type VehicleData = dict[str, dict[str, Any] | None]


@dataclass(frozen=True, kw_only=True)
class PleosEntityDescription(EntityDescription):
    """Common fields of all Pleos entity descriptions.

    ``legacy_key`` is the ``key`` the "Hyundai / Kia Connect" (kia_uvo)
    integration used for the same reading; its unique_id there is
    ``kia_uvo_<vehicle id>_<legacy_key>``. None = no counterpart.
    ``exists_fn`` decides on the first refresh whether the entity is created.
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
