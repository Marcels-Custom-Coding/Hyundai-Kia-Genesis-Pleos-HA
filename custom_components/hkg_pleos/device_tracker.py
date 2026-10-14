"""Position of the car."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import data as d
from .coordinator import PleosConfigEntry, PleosCoordinator
from .data import VehicleData
from .entity import PleosEntity, async_add_when_available

PARALLEL_UPDATES = 0

# kia_uvo key, also used as our key so the take-over finds it.
LOCATION_KEY = "location"


def _has_position(_: object, data: VehicleData) -> bool:
    return d.get(data, "locations", "location", "latitude") is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one tracker per car."""
    async_add_when_available(
        entry,
        async_add_entities,
        (LOCATION_KEY,),
        _has_position,
        lambda coordinator, _: PleosTracker(coordinator),
    )


class PleosTracker(PleosEntity, TrackerEntity):
    """GPS position from /locations."""

    _attr_translation_key = LOCATION_KEY
    _attr_icon = "mdi:map-marker-outline"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: PleosCoordinator) -> None:
        super().__init__(coordinator, LOCATION_KEY)

    @property
    def latitude(self) -> float | None:
        return d.number(d.get(self.vehicle_data, "locations", "location", "latitude"))

    @property
    def longitude(self) -> float | None:
        return d.number(d.get(self.vehicle_data, "locations", "location", "longitude"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        location = d.get(self.vehicle_data, "locations", "location") or {}
        speed = location.get("speed") or {}
        attributes: dict[str, Any] = {
            "altitude": location.get("altitude"),
            "heading": location.get("heading"),
            "speed": speed.get("value"),
            "speed_unit": d.SPEED_UNITS.get(speed.get("unit") or ""),
        }
        if stamp := d.timestamp(self.vehicle_data, "locations"):
            attributes["last_updated_at"] = stamp.isoformat()
        return {k: v for k, v in attributes.items() if v is not None}
