"""Binary sensors of a Pleos vehicle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import readings as r
from .const import TYPE_EV, TYPE_PHEV, TYPES_WITHOUT_FUEL
from .coordinator import PleosConfigEntry, PleosCoordinator
from .entity import PleosEntity, PleosEntityDescription

PARALLEL_UPDATES = 0

DIAGNOSTIC = EntityCategory.DIAGNOSTIC


@dataclass(frozen=True, kw_only=True)
class PleosBinarySensorEntityDescription(BinarySensorEntityDescription, PleosEntityDescription):
    """Describes a Pleos binary sensor."""

    value_fn: Callable[[PleosCoordinator], bool | None]
    on_icon: str | None = None
    off_icon: str | None = None


def _block(coordinator: PleosCoordinator, endpoint: str) -> dict[str, Any] | None:
    data = coordinator.data or {}
    block = data.get(endpoint)
    return block if isinstance(block, dict) else None


def _batteries(coordinator: PleosCoordinator) -> dict[str, Any] | None:
    return _block(coordinator, "batteries")


def _driving(coordinator: PleosCoordinator) -> dict[str, Any] | None:
    return _block(coordinator, "driving")


def _status(coordinator: PleosCoordinator) -> dict[str, Any] | None:
    return _block(coordinator, "status")


def _has_charge(coordinator: PleosCoordinator) -> bool:
    return isinstance(r.get(_batteries(coordinator), "charge"), dict)


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _is_locked(coordinator: PleosCoordinator) -> bool | None:
    """Lock class: on = unlocked. Off only when every known door is locked."""
    states = r.door_states(_status(coordinator))
    if not states:
        return None
    return not all(state == "locked" for state in states)


def _door_open(row: str, side: str) -> PleosBinarySensorEntityDescription:
    key = f"{row}_{side}_door_is_open"
    return PleosBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        legacy_key=key,
        device_class=BinarySensorDeviceClass.DOOR,
        entity_category=DIAGNOSTIC,
        on_icon="mdi:car-door",
        off_icon="mdi:car-door",
        value_fn=lambda c: r.is_open(r.door_state(_status(c), row, side)),
    )


def _door_lock(row: str, side: str) -> PleosBinarySensorEntityDescription:
    key = f"{row}_{side}_door_is_locked"

    def value(coordinator: PleosCoordinator) -> bool | None:
        state = r.door_state(_status(coordinator), row, side)
        return None if state is None else state != "locked"

    return PleosBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        legacy_key=key,
        device_class=BinarySensorDeviceClass.LOCK,
        entity_category=DIAGNOSTIC,
        on_icon="mdi:lock-open",
        off_icon="mdi:lock",
        value_fn=value,
    )


def _opening(
    key: str, field: str, device_class: BinarySensorDeviceClass, icon: str
) -> PleosBinarySensorEntityDescription:
    return PleosBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        legacy_key=key,
        device_class=device_class,
        entity_category=DIAGNOSTIC,
        on_icon=icon,
        off_icon=icon,
        value_fn=lambda c: r.is_open(r.get(_status(c), field)),
    )


def _warning(
    key: str,
    name: str,
    on_icon: str,
    off_icon: str,
    *,
    device_class: BinarySensorDeviceClass | None = BinarySensorDeviceClass.PROBLEM,
    needs_fuel: bool = False,
) -> PleosBinarySensorEntityDescription:
    def exists(coordinator: PleosCoordinator) -> bool:
        if needs_fuel and coordinator.vehicle_type in TYPES_WITHOUT_FUEL:
            return False
        return r.warnings_list(_status(coordinator)) is not None

    return PleosBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        legacy_key=key,
        device_class=device_class,
        entity_category=DIAGNOSTIC,
        on_icon=on_icon,
        off_icon=off_icon,
        value_fn=lambda c: r.has_warning(_status(c), name),
        exists_fn=exists,
    )


def _tire_warning(position: str, name: str) -> PleosBinarySensorEntityDescription:
    return _warning(
        f"tire_pressure_{position}_warning_is_on",
        name,
        "mdi:car-tire-alert",
        "mdi:car-tire-alert",
    )


def _seat_heater(row: str, side: str) -> PleosBinarySensorEntityDescription:
    key = f"{row}_{side}_seat_heater_on"
    return PleosBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        legacy_key=key,
        entity_category=DIAGNOSTIC,
        on_icon="mdi:seat-heater",
        off_icon="mdi:seat-outline",
        value_fn=lambda c: r.is_active_level(r.seat_heat(_status(c), row, side)),
    )


def _v2x_exists(coordinator: PleosCoordinator) -> bool:
    return (
        coordinator.vehicle_type in (TYPE_EV, TYPE_PHEV)
        and r.charging_status(_batteries(coordinator)) is not None
    )


BINARY_SENSOR_DESCRIPTIONS: tuple[PleosBinarySensorEntityDescription, ...] = (
    PleosBinarySensorEntityDescription(
        key="ev_battery_is_charging",
        translation_key="ev_battery_is_charging",
        legacy_key="ev_battery_is_charging",
        icon="mdi:ev-station",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=DIAGNOSTIC,
        value_fn=lambda c: r.is_charging(_batteries(c)),
        exists_fn=lambda c: r.is_charging(_batteries(c)) is not None,
    ),
    PleosBinarySensorEntityDescription(
        key="ev_battery_is_plugged_in",
        translation_key="ev_battery_is_plugged_in",
        legacy_key="ev_battery_is_plugged_in",
        icon="mdi:power-plug",
        device_class=BinarySensorDeviceClass.PLUG,
        entity_category=DIAGNOSTIC,
        value_fn=lambda c: r.is_plugged_in(_batteries(c)),
        # "invalid" while asleep is possible; the charge block shows support.
        exists_fn=lambda c: (
            r.is_plugged_in(_batteries(c)) is not None
            or (_has_charge(c) and c.vehicle_type in (TYPE_EV, TYPE_PHEV))
        ),
    ),
    PleosBinarySensorEntityDescription(
        key="ev_v2l_status",
        translation_key="ev_v2l_status",
        legacy_key="ev_v2l_status",
        icon="mdi:ev-station",
        value_fn=lambda c: r.status_contains(_batteries(c), "v2l"),
        exists_fn=_v2x_exists,
    ),
    PleosBinarySensorEntityDescription(
        key="ev_v2x_status",
        translation_key="ev_v2x_status",
        legacy_key="ev_v2x_status",
        icon="mdi:ev-station",
        value_fn=lambda c: r.status_contains(_batteries(c), "v2x", "v2g", "v2h"),
        exists_fn=_v2x_exists,
    ),
    PleosBinarySensorEntityDescription(
        key="engine_is_running",
        translation_key="engine_is_running",
        legacy_key="engine_is_running",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:engine",
        off_icon="mdi:engine-off",
        value_fn=lambda c: r.engine_running(_driving(c)),
    ),
    PleosBinarySensorEntityDescription(
        key="accessory_on",
        translation_key="accessory_on",
        legacy_key="accessory_on",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:car-key",
        off_icon="mdi:car-off",
        value_fn=lambda c: r.is_on(r.ignition_detail(_driving(c), "acc")),
    ),
    PleosBinarySensorEntityDescription(
        key="ign3",
        translation_key="ign3",
        legacy_key="ign3",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:key",
        off_icon="mdi:car-off",
        value_fn=lambda c: r.is_on(r.ignition_detail(_driving(c), "ign3")),
    ),
    PleosBinarySensorEntityDescription(
        key="sleep_mode_check",
        translation_key="sleep_mode_check",
        legacy_key="sleep_mode_check",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:sleep",
        off_icon="mdi:sleep-off",
        value_fn=lambda c: r.is_on(r.get(_driving(c), "sleepMode")),
    ),
    PleosBinarySensorEntityDescription(
        key="transmission_condition",
        translation_key="transmission_condition",
        legacy_key="transmission_condition",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:car-shift-pattern",
        off_icon="mdi:car",
        value_fn=lambda c: _bool(r.get(_driving(c), "transmission", "parkingPosition")),
    ),
    _door_open("front", "left"),
    _door_open("front", "right"),
    _door_open("back", "left"),
    _door_open("back", "right"),
    _door_lock("front", "left"),
    _door_lock("front", "right"),
    _door_lock("back", "left"),
    _door_lock("back", "right"),
    PleosBinarySensorEntityDescription(
        key="is_locked",
        translation_key="is_locked",
        legacy_key="is_locked",
        device_class=BinarySensorDeviceClass.LOCK,
        entity_category=DIAGNOSTIC,
        on_icon="mdi:lock-open",
        off_icon="mdi:lock",
        value_fn=_is_locked,
    ),
    _opening("hood_is_open", "hood", BinarySensorDeviceClass.DOOR, "mdi:car"),
    _opening("trunk_is_open", "trunk", BinarySensorDeviceClass.DOOR, "mdi:car-back"),
    _opening("sunroof_is_open", "sunroof", BinarySensorDeviceClass.WINDOW, "mdi:window-closed"),
    _warning(
        "fuel_level_is_low",
        "lowFuel",
        "mdi:gas-station-off",
        "mdi:gas-station",
        needs_fuel=True,
    ),
    _warning("washer_fluid_warning_is_on", "washFluid", "mdi:wiper-wash-alert", "mdi:wiper-wash"),
    _warning(
        "smart_key_battery_warning_is_on",
        "smartKeyBattery",
        "mdi:battery-alert",
        "mdi:battery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    _warning(
        "brake_fluid_warning_is_on",
        "brakeOil",
        "mdi:car-brake-alert",
        "mdi:car-brake-fluid-level",
    ),
    _warning("oil_level_warning_is_on", "engineOil", "mdi:oil", "mdi:oil", needs_fuel=True),
    _warning(
        "tire_pressure_all_warning_is_on",
        "tirePressureLow",
        "mdi:car-tire-alert",
        "mdi:car-tire-alert",
    ),
    _tire_warning("front_left", "tirePressureFrontLeft"),
    _tire_warning("front_right", "tirePressureFrontRight"),
    _tire_warning("rear_left", "tirePressureRearLeft"),
    _tire_warning("rear_right", "tirePressureRearRight"),
    PleosBinarySensorEntityDescription(
        key="air_control_is_on",
        translation_key="air_control_is_on",
        legacy_key="air_control_is_on",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:air-conditioner",
        off_icon="mdi:air-conditioner",
        value_fn=lambda c: r.is_on(r.get(_status(c), "climateControl", "status")),
    ),
    PleosBinarySensorEntityDescription(
        key="defrost_is_on",
        translation_key="defrost_is_on",
        legacy_key="defrost_is_on",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:car-defrost-front",
        off_icon="mdi:car-defrost-front",
        value_fn=lambda c: r.is_on(r.get(_status(c), "windshield", "defrost")),
    ),
    PleosBinarySensorEntityDescription(
        key="steering_wheel_heater_is_on",
        translation_key="steering_wheel_heater_is_on",
        legacy_key="steering_wheel_heater_is_on",
        entity_category=DIAGNOSTIC,
        on_icon="mdi:steering",
        off_icon="mdi:steering",
        value_fn=lambda c: r.is_active_level(r.get(_status(c), "steeringWheelHeat")),
    ),
    _seat_heater("front", "left"),
    _seat_heater("front", "right"),
    _seat_heater("rear", "left"),
    _seat_heater("rear", "right"),
)


def binary_sensor_exists(
    description: PleosBinarySensorEntityDescription, coordinator: PleosCoordinator
) -> bool:
    """Whether the binary sensor is created for this vehicle."""
    if description.exists_fn is not None:
        return description.exists_fn(coordinator)
    return description.value_fn(coordinator) is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors of all vehicles."""
    async_add_entities(
        PleosBinarySensor(coordinator, description)
        for coordinator in entry.runtime_data.coordinators.values()
        for description in BINARY_SENSOR_DESCRIPTIONS
        if binary_sensor_exists(description, coordinator)
    )


class PleosBinarySensor(PleosEntity, BinarySensorEntity):
    """A binary state of a vehicle."""

    entity_description: PleosBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state, None when unknown."""
        try:
            return self.entity_description.value_fn(self.coordinator)
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    @property
    def icon(self) -> str | None:
        """Return the state dependent icon."""
        description = self.entity_description
        if description.on_icon is None or description.off_icon is None:
            return super().icon
        return description.on_icon if self.is_on else description.off_icon
