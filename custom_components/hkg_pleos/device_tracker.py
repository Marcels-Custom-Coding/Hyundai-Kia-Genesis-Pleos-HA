"""GPS location of a Pleos vehicle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.device_tracker import (
    SourceType,
    TrackerEntity,
    TrackerEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import readings as r
from .coordinator import PleosConfigEntry, PleosCoordinator
from .entity import PleosEntity, PleosEntityDescription, async_add_vehicle_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PleosTrackerEntityDescription(TrackerEntityDescription, PleosEntityDescription):
    """Describes the Pleos location tracker."""

    value_fn: Callable[[PleosCoordinator], dict[str, Any] | None]


def _locations(coordinator: PleosCoordinator) -> dict[str, Any] | None:
    block = (coordinator.data or {}).get("locations")
    return block if isinstance(block, dict) else None


TRACKER_DESCRIPTIONS: tuple[PleosTrackerEntityDescription, ...] = (
    PleosTrackerEntityDescription(
        key="location",
        translation_key="location",
        legacy_key="location",
        icon="mdi:map-marker-outline",
        value_fn=lambda c: r.valid_location(_locations(c)),
        # Created when the vehicle reports a location block at all; a fix
        # outside WGS84 or out of range only makes the state unknown.
        exists_fn=lambda c: isinstance(r.get(_locations(c), "location"), dict),
    ),
)


def tracker_exists(
    description: PleosTrackerEntityDescription, coordinator: PleosCoordinator
) -> bool:
    """Whether the tracker is created for this vehicle."""
    if description.exists_fn is not None:
        return description.exists_fn(coordinator)
    return description.value_fn(coordinator) is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the location trackers of all vehicles."""
    async_add_vehicle_entities(
        hass,
        entry,
        "device_tracker",
        async_add_entities,
        descriptions=TRACKER_DESCRIPTIONS,
        exists=tracker_exists,
        factory=PleosTracker,
    )


class PleosTracker(PleosEntity, TrackerEntity):
    """Vehicle position."""

    entity_description: PleosTrackerEntityDescription
    _attr_source_type = SourceType.GPS

    @property
    def _location(self) -> dict[str, Any] | None:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def latitude(self) -> float | None:
        """Return the latitude."""
        if (location := self._location) is None:
            return None
        return r.parse_number(location.get("latitude"))

    @property
    def longitude(self) -> float | None:
        """Return the longitude."""
        if (location := self._location) is None:
            return None
        return r.parse_number(location.get("longitude"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return altitude, heading, speed and time of the fix."""
        location = self._location or {}
        speed = r.get(location, "speed")
        timestamp = r.parse_timestamp(r.get(_locations(self.coordinator), "timestamp"))
        return {
            "altitude": r.parse_number(r.get(location, "altitude")),
            "heading": r.parse_number(r.get(location, "heading")),
            "speed": r.measured_value(speed),
            "speed_unit": r.speed_unit(r.get(speed, "unit")),
            "last_update": timestamp.isoformat() if timestamp else None,
        }
