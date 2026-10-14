"""Binary sensors. Keys and names follow the Hyundai / Kia Connect integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import data as d
from .coordinator import PleosConfigEntry, PleosCoordinator
from .data import VehicleData
from .entity import PleosEntity, async_add_when_available

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PleosBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor with the value source and icons like kia_uvo."""

    is_on_fn: Callable[[VehicleData], bool | None]
    on_icon: str | None = None
    off_icon: str | None = None
    # Key of the matching kia_uvo entity (end of its unique_id), for take-over.
    uvo_key: str | None = None
    # Only create the entity when this also has a value (e.g. fuel warning on EVs).
    requires_fn: Callable[[VehicleData], object] | None = None


def _diag(
    key: str,
    is_on_fn: Callable[[VehicleData], bool | None],
    *,
    device_class: BinarySensorDeviceClass | None = None,
    on_icon: str | None = None,
    off_icon: str | None = None,
    uvo: bool = True,
) -> PleosBinarySensorEntityDescription:
    return PleosBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        uvo_key=key if uvo else None,
        device_class=device_class,
        entity_category=EntityCategory.DIAGNOSTIC,
        on_icon=on_icon,
        off_icon=off_icon or on_icon,
        is_on_fn=is_on_fn,
    )


DOOR_POSITIONS = {
    "front_left": ("front", "left"),
    "front_right": ("front", "right"),
    "back_left": ("rear", "left"),
    "back_right": ("rear", "right"),
}
SEAT_POSITIONS = {
    "front_left": ("front", "left"),
    "front_right": ("front", "right"),
    "rear_left": ("rear", "left"),
    "rear_right": ("rear", "right"),
}
LAMP = "mdi:lightbulb-alert-outline"
LAMP_OK = "mdi:lightbulb-outline"
TIRE = "mdi:car-tire-alert"


def _doors() -> list[PleosBinarySensorEntityDescription]:
    result = []
    for name, (row, side) in DOOR_POSITIONS.items():
        result.append(
            _diag(
                f"{name}_door_is_open",
                lambda data, row=row, side=side: d.door_open(data, row, side),
                device_class=BinarySensorDeviceClass.DOOR,
                on_icon="mdi:car-door",
            )
        )
        result.append(
            _diag(
                f"{name}_door_is_locked",
                lambda data, row=row, side=side: d.door_unlocked(data, row, side),
                device_class=BinarySensorDeviceClass.LOCK,
                on_icon="mdi:lock-open",
                off_icon="mdi:lock",
            )
        )
    return result


def _seats() -> list[PleosBinarySensorEntityDescription]:
    return [
        _diag(
            f"{name}_seat_heater_on",
            lambda data, row=row, side=side: (
                None
                if (heat := d.seat(data, row, side, "heat")) is None
                else heat != "off"
            ),
            on_icon="mdi:seat-heater",
            off_icon="mdi:seat-outline",
        )
        for name, (row, side) in SEAT_POSITIONS.items()
    ]


def _warning(
    key: str, *names: str, icon: str, off_icon: str | None = None, problem: bool = True
) -> PleosBinarySensorEntityDescription:
    return _diag(
        key,
        lambda data: d.warning(data, *names),
        device_class=BinarySensorDeviceClass.PROBLEM if problem else None,
        on_icon=icon,
        off_icon=off_icon,
    )


BINARY_SENSORS: tuple[PleosBinarySensorEntityDescription, ...] = (
    # Charging
    PleosBinarySensorEntityDescription(
        key="ev_battery_is_charging",
        translation_key="ev_battery_is_charging",
        uvo_key="ev_battery_is_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: d.charge(data, "charging"),
    ),
    PleosBinarySensorEntityDescription(
        key="ev_battery_is_plugged_in",
        translation_key="ev_battery_is_plugged_in",
        uvo_key="ev_battery_is_plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=d.plugged_in,
    ),
    PleosBinarySensorEntityDescription(
        key="ev_v2l_status",
        translation_key="ev_v2l_status",
        uvo_key="ev_v2l_status",
        icon="mdi:ev-station",
        is_on_fn=lambda data: d.charge_status_is(data, "v2lOperating"),
    ),
    PleosBinarySensorEntityDescription(
        key="ev_v2x_status",
        translation_key="ev_v2x_status",
        uvo_key="ev_v2x_status",
        icon="mdi:ev-station",
        is_on_fn=lambda data: d.charge_status_is(data, "v2xOperating"),
    ),
    # Driving
    _diag(
        "engine_is_running",
        lambda data: d.flag(d.get(data, "driving", "ignition", "status")),
        on_icon="mdi:engine",
        off_icon="mdi:engine-off",
    ),
    _diag(
        "accessory_on",
        lambda data: d.ignition(data, "acc"),
        on_icon="mdi:car-key",
        off_icon="mdi:car-off",
    ),
    _diag(
        "ign3",
        lambda data: d.ignition(data, "ign3"),
        on_icon="mdi:key",
        off_icon="mdi:car-off",
    ),
    _diag(
        "sleep_mode_check",
        lambda data: d.flag(d.get(data, "driving", "sleepMode")),
        on_icon="mdi:sleep",
        off_icon="mdi:sleep-off",
    ),
    _diag(
        "transmission_condition",
        lambda data: d.get(data, "driving", "transmission", "parkingPosition"),
        on_icon="mdi:car-shift-pattern",
        off_icon="mdi:car",
    ),
    # Doors, lids, lock
    *_doors(),
    PleosBinarySensorEntityDescription(
        key="is_locked",
        translation_key="is_locked",
        uvo_key="is_locked",
        device_class=BinarySensorDeviceClass.LOCK,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=d.any_door_unlocked,
    ),
    _diag(
        "hood_is_open",
        lambda data: d.flag(d.get(data, "status", "hood"), "open"),
        device_class=BinarySensorDeviceClass.DOOR,
        on_icon="mdi:car",
    ),
    _diag(
        "trunk_is_open",
        lambda data: d.flag(d.get(data, "status", "trunk"), "open"),
        device_class=BinarySensorDeviceClass.DOOR,
        on_icon="mdi:car-back",
    ),
    _diag(
        "sunroof_is_open",
        lambda data: d.flag(d.get(data, "status", "sunroof"), "open"),
        device_class=BinarySensorDeviceClass.WINDOW,
        on_icon="mdi:window-closed",
    ),
    # Climate
    _diag(
        "air_control_is_on",
        lambda data: d.flag(d.get(data, "status", "climateControl", "status")),
        on_icon="mdi:air-conditioner",
    ),
    _diag(
        "defrost_is_on",
        lambda data: d.flag(d.get(data, "status", "windshield", "defrost")),
        on_icon="mdi:car-defrost-front",
    ),
    _diag(
        "steering_wheel_heater_is_on",
        lambda data: d.flag(d.get(data, "status", "steeringWheelHeat")),
        on_icon="mdi:steering",
    ),
    *_seats(),
    # Warning lights
    PleosBinarySensorEntityDescription(
        key="fuel_level_is_low",
        translation_key="fuel_level_is_low",
        uvo_key="fuel_level_is_low",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_icon="mdi:gas-station-off",
        off_icon="mdi:gas-station",
        is_on_fn=lambda data: d.warning(data, "lowFuel"),
        requires_fn=lambda data: d.get(data, "powertrains", "engine", "fuelLevel"),
    ),
    PleosBinarySensorEntityDescription(
        key="smart_key_battery_warning_is_on",
        translation_key="smart_key_battery_warning_is_on",
        uvo_key="smart_key_battery_warning_is_on",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        on_icon="mdi:battery-alert",
        off_icon="mdi:battery",
        is_on_fn=lambda data: d.warning(data, "smartKeyBattery"),
    ),
    _warning(
        "washer_fluid_warning_is_on",
        "washFluid",
        icon="mdi:wiper-wash-alert",
        off_icon="mdi:wiper-wash",
    ),
    _warning(
        "brake_fluid_warning_is_on",
        "brakeOil",
        icon="mdi:car-brake-alert",
        off_icon="mdi:car-brake-fluid-level",
    ),
    _warning("oil_level_warning_is_on", "engineOil", icon="mdi:oil"),
    _warning("tire_pressure_all_warning_is_on", "tirePressureLow", icon=TIRE),
    _warning(
        "tire_pressure_front_left_warning_is_on", "tirePressureFrontLeft", icon=TIRE
    ),
    _warning(
        "tire_pressure_front_right_warning_is_on", "tirePressureFrontRight", icon=TIRE
    ),
    _warning(
        "tire_pressure_rear_left_warning_is_on", "tirePressureRearLeft", icon=TIRE
    ),
    _warning(
        "tire_pressure_rear_right_warning_is_on", "tirePressureRearRight", icon=TIRE
    ),
    _warning("headlamp_status", "frontHeadLamp", icon=LAMP, off_icon=LAMP_OK),
    _warning(
        "turn_signal_left_front", "frontLeftTurnSignal", icon=LAMP, off_icon=LAMP_OK
    ),
    _warning(
        "turn_signal_right_front", "frontRightTurnSignal", icon=LAMP, off_icon=LAMP_OK
    ),
    _warning(
        "turn_signal_left_rear", "rearLeftTurnSignal", icon=LAMP, off_icon=LAMP_OK
    ),
    _warning(
        "turn_signal_right_rear", "rearRightTurnSignal", icon=LAMP, off_icon=LAMP_OK
    ),
    _warning("stop_lamp_left", "rearLeftStopLamp", icon=LAMP, off_icon=LAMP_OK),
    _warning("stop_lamp_right", "rearRightStopLamp", icon=LAMP, off_icon=LAMP_OK),
)


def _has_value(
    description: PleosBinarySensorEntityDescription, data: VehicleData
) -> bool:
    if description.requires_fn is not None and description.requires_fn(data) is None:
        return False
    return description.is_on_fn(data) is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors of all cars."""
    async_add_when_available(
        entry,
        async_add_entities,
        BINARY_SENSORS,
        _has_value,
        PleosBinarySensor,
    )


class PleosBinarySensor(PleosEntity, BinarySensorEntity):
    """An on/off value read from Pleos."""

    entity_description: PleosBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: PleosCoordinator,
        description: PleosBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.vehicle_data)

    @property
    def icon(self) -> str | None:
        description = self.entity_description
        if description.on_icon is None:
            return description.icon
        return description.on_icon if self.is_on else description.off_icon
