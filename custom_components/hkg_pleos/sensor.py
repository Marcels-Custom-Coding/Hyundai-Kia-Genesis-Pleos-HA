"""Sensors of a Pleos vehicle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import readings as r
from .const import TYPES_WITHOUT_FUEL
from .coordinator import PleosConfigEntry, PleosCoordinator
from .entity import PleosEntity, PleosEntityDescription

PARALLEL_UPDATES = 0

# HA rejects states longer than 255 characters.
MAX_STATE_LENGTH = 255

type SensorValue = StateType | datetime


@dataclass(frozen=True, kw_only=True)
class PleosSensorEntityDescription(SensorEntityDescription, PleosEntityDescription):
    """Describes a Pleos sensor."""

    value_fn: Callable[[PleosCoordinator], SensorValue]
    unit_fn: Callable[[PleosCoordinator], str | None] | None = None
    attrs_fn: Callable[[PleosCoordinator], dict[str, Any] | None] | None = None


def _block(coordinator: PleosCoordinator, endpoint: str) -> dict[str, Any] | None:
    data = coordinator.data or {}
    block = data.get(endpoint)
    return block if isinstance(block, dict) else None


def _number(value: Any) -> float | int | None:
    number = r.parse_number(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else number


def _charge(coordinator: PleosCoordinator, *path: str) -> Any:
    return r.get(_block(coordinator, "batteries"), "charge", *path)


def _has_charge(coordinator: PleosCoordinator) -> bool:
    return isinstance(_charge(coordinator), dict)


def _status(coordinator: PleosCoordinator, *path: str | int) -> Any:
    return r.get(_block(coordinator, "status"), *path)


def _range_sensor(kind: str, key: str, legacy_key: str) -> PleosSensorEntityDescription:
    return PleosSensorEntityDescription(
        key=key,
        translation_key=key,
        legacy_key=legacy_key,
        icon="mdi:road-variant",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: r.range_value(_block(c, "powertrains"), kind),
        unit_fn=lambda c: r.range_unit(_block(c, "powertrains"), kind),
        # The value may be "-" for a while; the entry itself shows support.
        exists_fn=lambda c: r.find_range_entry(_block(c, "powertrains"), kind) is not None,
    )


def _tire_sensor(row: str, side: str) -> PleosSensorEntityDescription:
    key = f"tire_pressure_{row}_{side}"
    return PleosSensorEntityDescription(
        key=key,
        translation_key=key,
        legacy_key=key,
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: r.tire_value(_block(c, "status"), row, side),
        unit_fn=lambda c: r.tire_unit(_block(c, "status"), row),
        # 255 (no reading) is common while parked; a known unit shows support.
        exists_fn=lambda c: (
            r.tire_value(_block(c, "status"), row, side) is not None
            or r.tire_unit(_block(c, "status"), row) is not None
        ),
    )


def _warnings_state(coordinator: PleosCoordinator) -> str | None:
    warnings = r.warnings_list(_block(coordinator, "status"))
    if warnings is None:
        return None
    state = ", ".join(warnings) or "none"
    if len(state) > MAX_STATE_LENGTH:
        state = state[: MAX_STATE_LENGTH - 3] + "..."
    return state


SENSOR_DESCRIPTIONS: tuple[PleosSensorEntityDescription, ...] = (
    PleosSensorEntityDescription(
        key="ev_battery_percentage",
        translation_key="ev_battery_percentage",
        legacy_key="ev_battery_percentage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _number(_charge(c, "stateOfCharge")),
    ),
    PleosSensorEntityDescription(
        key="ev_battery_capacity",
        translation_key="ev_battery_capacity",
        legacy_key="ev_battery_capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _number(_charge(c, "batteryCapacity")),
    ),
    PleosSensorEntityDescription(
        key="ev_charge_limit_ac",
        translation_key="ev_charge_limit_ac",
        icon="mdi:ev-station",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda c: _number(_charge(c, "targetStateOfCharge", "standard")),
    ),
    PleosSensorEntityDescription(
        key="ev_charge_limit_dc",
        translation_key="ev_charge_limit_dc",
        icon="mdi:ev-station",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda c: _number(_charge(c, "targetStateOfCharge", "quick")),
    ),
    PleosSensorEntityDescription(
        key="ev_estimated_current_charge_duration",
        translation_key="ev_estimated_current_charge_duration",
        legacy_key="ev_estimated_current_charge_duration",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _number(_charge(c, "remainTime")),
        # Only reported while charging.
        exists_fn=_has_charge,
    ),
    PleosSensorEntityDescription(
        key="ev_charging_status",
        translation_key="ev_charging_status",
        icon="mdi:ev-station",
        value_fn=lambda c: r.charging_status(_block(c, "batteries")),
    ),
    _range_sensor("ev", "ev_driving_range", "_ev_driving_range"),
    _range_sensor("fuel", "fuel_driving_range", "_fuel_driving_range"),
    _range_sensor("total", "total_driving_range", "_total_driving_range"),
    PleosSensorEntityDescription(
        key="fuel_level",
        translation_key="fuel_level",
        legacy_key="fuel_level",
        icon="mdi:fuel",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _number(r.get(_block(c, "powertrains"), "engine", "fuelLevel")),
        exists_fn=lambda c: (
            c.vehicle_type not in TYPES_WITHOUT_FUEL
            and r.get(_block(c, "powertrains"), "engine", "fuelLevel") is not None
        ),
    ),
    PleosSensorEntityDescription(
        key="ev_battery_remain_ratio",
        translation_key="ev_battery_remain_ratio",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda c: r.main_battery_ratio(_block(c, "powertrains")),
    ),
    PleosSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        legacy_key="_odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: r.measured_value(r.get(_block(c, "driving"), "odometer")),
        unit_fn=lambda c: r.distance_unit(r.get(_block(c, "driving"), "odometer", "unit")),
    ),
    _tire_sensor("front", "left"),
    _tire_sensor("front", "right"),
    _tire_sensor("rear", "left"),
    _tire_sensor("rear", "right"),
    PleosSensorEntityDescription(
        key="air_temperature",
        translation_key="air_temperature",
        legacy_key="_air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda c: r.measured_value(_status(c, "climateControl", "temperature")),
        unit_fn=lambda c: r.temperature_unit(_status(c, "climateControl", "temperature", "unit")),
        # The set temperature may be missing while the climate is off.
        exists_fn=lambda c: isinstance(_status(c, "climateControl"), dict),
    ),
    PleosSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        legacy_key="_outside_temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: r.measured_value(_status(c, "outsideTemperature")),
        unit_fn=lambda c: r.temperature_unit(_status(c, "outsideTemperature", "unit")),
    ),
    PleosSensorEntityDescription(
        key="steering_wheel_heat_level",
        translation_key="steering_wheel_heat_level",
        icon="mdi:steering",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: (
            v if isinstance(v := _status(c, "steeringWheelHeat"), str) and v else None
        ),
    ),
    PleosSensorEntityDescription(
        key="warnings",
        translation_key="warnings",
        icon="mdi:alert-circle",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_warnings_state,
        attrs_fn=lambda c: {"warnings": r.warnings_list(_block(c, "status")) or []},
    ),
    PleosSensorEntityDescription(
        key="last_updated_at",
        translation_key="last_updated_at",
        legacy_key="last_updated_at",
        icon="mdi:update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: r.latest_timestamp(c.data),
    ),
    PleosSensorEntityDescription(
        key="location_last_updated_at",
        translation_key="location_last_updated_at",
        legacy_key="location_last_updated_at",
        icon="mdi:map-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: r.parse_timestamp(r.get(_block(c, "locations"), "timestamp")),
    ),
    PleosSensorEntityDescription(
        key="vehicle_identification_number",
        translation_key="vehicle_identification_number",
        legacy_key="VIN",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.vin,
    ),
)


def sensor_exists(description: PleosSensorEntityDescription, coordinator: PleosCoordinator) -> bool:
    """Whether the sensor is created for this vehicle."""
    if description.exists_fn is not None:
        return description.exists_fn(coordinator)
    return description.value_fn(coordinator) is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of all vehicles."""
    async_add_entities(
        PleosSensor(coordinator, description)
        for coordinator in entry.runtime_data.coordinators.values()
        for description in SENSOR_DESCRIPTIONS
        if sensor_exists(description, coordinator)
    )


class PleosSensor(PleosEntity, RestoreSensor):
    """A sensor reading of a vehicle."""

    entity_description: PleosSensorEntityDescription

    def __init__(
        self, coordinator: PleosCoordinator, description: PleosSensorEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)
        self._last_unit: str | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known dynamic unit."""
        await super().async_added_to_hass()
        if self.entity_description.unit_fn is None:
            return
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._last_unit = last.native_unit_of_measurement

    @property
    def native_value(self) -> SensorValue:
        """Return the current value."""
        try:
            return self.entity_description.value_fn(self.coordinator)
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the reported unit, else the last known one."""
        if self.entity_description.unit_fn is None:
            return self.entity_description.native_unit_of_measurement
        if (unit := self.entity_description.unit_fn(self.coordinator)) is not None:
            self._last_unit = unit
        return self._last_unit

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)
