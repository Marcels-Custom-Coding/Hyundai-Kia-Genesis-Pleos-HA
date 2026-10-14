"""Sensors. Keys and names follow the Hyundai / Kia Connect integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import data as d
from .coordinator import PleosConfigEntry, PleosCoordinator
from .data import VehicleData
from .entity import PleosEntity, async_add_when_available

PARALLEL_UPDATES = 0

CHARGE_STATUSES = [
    "not_charging",
    "charging",
    "fast_charging",
    "v2l_operating",
    "v2l_stop",
    "v2x_operating",
    "reserved_charging",
    "wireless_charging",
]
SEAT_LEVELS = ["off", "low", "middle", "high"]


def _snake(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in value)


@dataclass(frozen=True, kw_only=True)
class PleosSensorEntityDescription(SensorEntityDescription):
    """Sensor with the value source and the old kia_uvo key."""

    value_fn: Callable[[VehicleData], Any]
    unit_fn: Callable[[VehicleData], str | None] | None = None
    # Key of the matching kia_uvo entity (end of its unique_id), for take-over.
    uvo_key: str | None = None


def _tire(row: str, side: str) -> PleosSensorEntityDescription:
    key = f"tire_pressure_{row}_{side}"
    return PleosSensorEntityDescription(
        key=key,
        translation_key=key,
        uvo_key=key,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: d.tire_pressure(data, row, side),
        unit_fn=lambda data: d.tire_unit(data, row, side),
    )


def _seat(row: str, side: str) -> tuple[PleosSensorEntityDescription, ...]:
    seat = f"{'front' if row == 'front' else 'rear'}_{side}_seat"
    return (
        PleosSensorEntityDescription(
            key=f"{seat}_status",
            translation_key=f"{seat}_status",
            uvo_key=f"{seat}_status",
            icon="mdi:car-seat-heater",
            device_class=SensorDeviceClass.ENUM,
            options=SEAT_LEVELS,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data: d.seat(data, row, side, "heat"),
        ),
        PleosSensorEntityDescription(
            key=f"{seat}_ventilation",
            translation_key=f"{seat}_ventilation",
            icon="mdi:car-seat-cooler",
            device_class=SensorDeviceClass.ENUM,
            options=SEAT_LEVELS,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data: d.seat(data, row, side, "ventilation"),
        ),
    )


SENSORS: tuple[PleosSensorEntityDescription, ...] = (
    PleosSensorEntityDescription(
        key="ev_battery_percentage",
        translation_key="ev_battery_percentage",
        uvo_key="ev_battery_percentage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: d.number(d.charge(data, "stateOfCharge")),
    ),
    PleosSensorEntityDescription(
        key="ev_battery_capacity",
        translation_key="ev_battery_capacity",
        uvo_key="ev_battery_capacity",
        native_unit_of_measurement=UnitOfEnergy.KILO_JOULE,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: d.number(d.charge(data, "batteryCapacity")),
    ),
    PleosSensorEntityDescription(
        key="ev_charge_limit_ac",
        translation_key="ev_charge_limit_ac",
        icon="mdi:ev-plug-type2",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: d.target_soc(data, "standard"),
    ),
    PleosSensorEntityDescription(
        key="ev_charge_limit_dc",
        translation_key="ev_charge_limit_dc",
        icon="mdi:ev-plug-ccs2",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: d.target_soc(data, "quick"),
    ),
    PleosSensorEntityDescription(
        key="ev_estimated_current_charge_duration",
        translation_key="ev_estimated_current_charge_duration",
        uvo_key="ev_estimated_current_charge_duration",
        icon="mdi:ev-station",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: d.number(d.charge(data, "remainTime")),
    ),
    PleosSensorEntityDescription(
        key="ev_charging_status",
        translation_key="ev_charging_status",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_STATUSES,
        value_fn=lambda data: _snake(d.charge(data, "status")),
    ),
    PleosSensorEntityDescription(
        key="total_driving_range",
        translation_key="total_driving_range",
        uvo_key="_total_driving_range",
        icon="mdi:road-variant",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: d.dte_value(data, "total"),
        unit_fn=lambda data: d.dte_unit(data, "total"),
    ),
    PleosSensorEntityDescription(
        key="ev_driving_range",
        translation_key="ev_driving_range",
        uvo_key="_ev_driving_range",
        icon="mdi:road-variant",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: d.dte_value(data, "ev"),
        unit_fn=lambda data: d.dte_unit(data, "ev"),
    ),
    PleosSensorEntityDescription(
        key="fuel_driving_range",
        translation_key="fuel_driving_range",
        uvo_key="_fuel_driving_range",
        icon="mdi:road-variant",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: d.dte_value(data, "fuel"),
        unit_fn=lambda data: d.dte_unit(data, "fuel"),
    ),
    PleosSensorEntityDescription(
        key="fuel_level",
        translation_key="fuel_level",
        uvo_key="fuel_level",
        icon="mdi:fuel",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: d.number(
            d.get(data, "powertrains", "engine", "fuelLevel")
        ),
    ),
    PleosSensorEntityDescription(
        key="car_battery_percentage",
        translation_key="car_battery_percentage",
        uvo_key="car_battery_percentage",
        icon="mdi:car-battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=d.aux_battery,
    ),
    PleosSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        uvo_key="_odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: d.number(d.get(data, "driving", "odometer", "value")),
        unit_fn=lambda data: d.DISTANCE_UNITS.get(
            d.get(data, "driving", "odometer", "unit") or ""
        ),
    ),
    _tire("front", "left"),
    _tire("front", "right"),
    _tire("rear", "left"),
    _tire("rear", "right"),
    *_seat("front", "left"),
    *_seat("front", "right"),
    *_seat("rear", "left"),
    *_seat("rear", "right"),
    PleosSensorEntityDescription(
        key="air_temperature",
        translation_key="air_temperature",
        uvo_key="_air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: d.temperature(data, "climateControl", "temperature")[0],
        unit_fn=lambda data: d.temperature(data, "climateControl", "temperature")[1],
    ),
    PleosSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        uvo_key="_outside_temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: d.temperature(data, "outsideTemperature")[0],
        unit_fn=lambda data: d.temperature(data, "outsideTemperature")[1],
    ),
    PleosSensorEntityDescription(
        key="last_updated_at",
        translation_key="last_updated_at",
        uvo_key="last_updated_at",
        icon="mdi:update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=d.last_updated,
    ),
    PleosSensorEntityDescription(
        key="location_last_updated_at",
        translation_key="location_last_updated_at",
        uvo_key="location_last_updated_at",
        icon="mdi:map-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: d.timestamp(data, "locations"),
    ),
)

VIN_SENSOR = PleosSensorEntityDescription(
    key="vehicle_identification_number",
    translation_key="vehicle_identification_number",
    uvo_key="VIN",
    icon="mdi:identifier",
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda data: None,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PleosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of all cars."""
    async_add_entities(
        PleosVinSensor(coordinator, VIN_SENSOR)
        for coordinator in entry.runtime_data.coordinators.values()
    )
    async_add_when_available(
        entry,
        async_add_entities,
        SENSORS,
        lambda description, data: description.value_fn(data) is not None,
        PleosSensor,
    )


class PleosSensor(PleosEntity, SensorEntity):
    """A value read from Pleos."""

    entity_description: PleosSensorEntityDescription

    def __init__(
        self, coordinator: PleosCoordinator, description: PleosSensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._last_unit: str | None = None

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.vehicle_data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.unit_fn is None:
            return self.entity_description.native_unit_of_measurement
        # Keep the last known unit when a response comes without one.
        if unit := self.entity_description.unit_fn(self.vehicle_data):
            self._last_unit = unit
        return self._last_unit


class PleosVinSensor(PleosEntity, SensorEntity):
    """The VIN, like the old integration offered it."""

    entity_description: PleosSensorEntityDescription

    def __init__(
        self, coordinator: PleosCoordinator, description: PleosSensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_native_value = coordinator.vin

    @property
    def available(self) -> bool:
        return True
