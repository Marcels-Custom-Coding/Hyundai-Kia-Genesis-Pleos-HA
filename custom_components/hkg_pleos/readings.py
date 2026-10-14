"""Parsing helpers that turn Pleos payloads into Home Assistant values.

Every helper is a pure function on the endpoint blocks stored in
``PleosCoordinator.data`` (endpoint name -> "data" block or None), so it can be
tested without entities. Missing values, "invalid" and sentinel values become
None.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
import math
from typing import Any

from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.util import dt as dt_util

from .const import ENDPOINTS

type VehicleData = Mapping[str, Mapping[str, Any] | None]

INVALID = "invalid"

# Raw tire pressure value meaning "no reading".
TIRE_INVALID = 255

# distanceToEmpties values outside this range are no reading.
RANGE_MIN = 1
RANGE_MAX = 4095

RANGE_EV = "EV"
RANGE_ICE = "ICE"
RANGE_COMBINED = ("PHEV", "HEV", "FCEV")

DISTANCE_UNITS: dict[str, str] = {
    "km": UnitOfLength.KILOMETERS,
    "mile": UnitOfLength.MILES,
    "miles": UnitOfLength.MILES,
    "meter": UnitOfLength.METERS,
    "feet": UnitOfLength.FEET,
}
TEMPERATURE_UNITS: dict[str, str] = {
    "c": UnitOfTemperature.CELSIUS,
    "f": UnitOfTemperature.FAHRENHEIT,
}
PRESSURE_UNITS: dict[str, str] = {
    "kpa": UnitOfPressure.KPA,
    "bar": UnitOfPressure.BAR,
    "psi": UnitOfPressure.PSI,
}
SPEED_UNITS: dict[str, str] = {
    "kph": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "mph": UnitOfSpeed.MILES_PER_HOUR,
    "mps": UnitOfSpeed.METERS_PER_SECOND,
}

CHARGING_STATUSES = ("charging", "fastcharging", "wirelesscharging")

DOOR_ROWS = {"front": 0, "back": 1}
SEAT_ROWS = {"front": 0, "rear": 1}
TIRE_ROWS = {"front": 0, "rear": 1}


def get(data: Any, *path: str | int) -> Any:
    """Return a nested value or None; the string "invalid" counts as missing."""
    for key in path:
        try:
            data = data[key]
        except (KeyError, IndexError, TypeError):
            return None
    if isinstance(data, str) and data.strip().lower() == INVALID:
        return None
    return data


def parse_number(value: Any) -> float | None:
    """Return a finite number from an int, float or numeric string."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            number = float(value)
        except ValueError:
            return None
    elif isinstance(value, int | float):
        number = float(value)
    else:
        return None
    if not math.isfinite(number):
        return None
    return number


def _int_if_whole(number: float) -> float | int:
    return int(number) if number.is_integer() else number


def _unit(units: Mapping[str, str], unit: Any) -> str | None:
    if not isinstance(unit, str):
        return None
    return units.get(unit.strip().lower())


def distance_unit(unit: Any) -> str | None:
    """Map a Pleos distance unit (km, mile(s), meter, feet) to HA."""
    return _unit(DISTANCE_UNITS, unit)


def temperature_unit(unit: Any) -> str | None:
    """Map a Pleos temperature unit (C, F) to HA."""
    return _unit(TEMPERATURE_UNITS, unit)


def pressure_unit(unit: Any) -> str | None:
    """Map a Pleos pressure unit (kpa, bar, psi) to HA."""
    return _unit(PRESSURE_UNITS, unit)


def speed_unit(unit: Any) -> str | None:
    """Map a Pleos speed unit (kph, mph, mps) to HA."""
    return _unit(SPEED_UNITS, unit)


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp into an aware datetime (UTC if naive)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt_util.parse_datetime(value.strip())
    except ValueError:
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


def latest_timestamp(
    data: VehicleData | None, endpoints: Iterable[str] = ENDPOINTS
) -> datetime | None:
    """Newest timestamp of the given endpoint blocks."""
    if not data:
        return None
    stamps = [
        stamp
        for endpoint in endpoints
        if (stamp := parse_timestamp(get(data, endpoint, "timestamp"))) is not None
    ]
    return max(stamps) if stamps else None


# Ranges (powertrains.distanceToEmpties)


def range_entries(powertrains: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """distanceToEmpties entries with a known type."""
    entries = get(powertrains, "distanceToEmpties")
    if not isinstance(entries, list):
        return []
    return [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("type"), str)
        and entry["type"].strip().lower() != INVALID
    ]


def find_range_entry(powertrains: Mapping[str, Any] | None, kind: str) -> dict[str, Any] | None:
    """Entry for "ev", "fuel" or "total" range.

    total: the first PHEV/HEV/FCEV entry; otherwise the EV or ICE entry if it
    is the only one.
    """
    entries = range_entries(powertrains)
    by_type: dict[str, dict[str, Any]] = {}
    for entry in entries:
        by_type.setdefault(entry["type"].strip().upper(), entry)
    if kind == "ev":
        return by_type.get(RANGE_EV)
    if kind == "fuel":
        return by_type.get(RANGE_ICE)
    if kind == "total":
        for range_type in RANGE_COMBINED:
            if range_type in by_type:
                return by_type[range_type]
        if len(by_type) == 1:
            only = next(iter(by_type))
            if only in (RANGE_EV, RANGE_ICE):
                return by_type[only]
        return None
    raise ValueError(f"Unknown range kind {kind}")


def parse_range(value: Any) -> float | int | None:
    """Range value (a string such as "106", "-" or "invalid") as a number."""
    number = parse_number(value)
    if number is None or not RANGE_MIN <= number <= RANGE_MAX:
        return None
    return _int_if_whole(number)


def range_value(powertrains: Mapping[str, Any] | None, kind: str) -> float | int | None:
    """Range of the given kind in its reported unit."""
    entry = find_range_entry(powertrains, kind)
    return parse_range(entry.get("value")) if entry else None


def range_unit(powertrains: Mapping[str, Any] | None, kind: str) -> str | None:
    """HA unit of the given range kind."""
    entry = find_range_entry(powertrains, kind)
    return distance_unit(entry.get("unit")) if entry else None


def main_battery_ratio(powertrains: Mapping[str, Any] | None) -> float | int | None:
    """remainRatio of the high-voltage ("main") battery."""
    batteries = get(powertrains, "batteries")
    if not isinstance(batteries, list):
        return None
    for battery in batteries:
        if isinstance(battery, dict) and battery.get("type") == "main":
            number = parse_number(get(battery, "remainRatio"))
            return None if number is None else _int_if_whole(number)
    return None


# Values with unit ({"value": .., "unit": ..})


def measured_value(block: Any) -> float | int | None:
    """Numeric "value" of a {"value", "unit"} block."""
    number = parse_number(get(block, "value"))
    return None if number is None else _int_if_whole(number)


def tire_pressure(raw: Any, unit: Any) -> float | int | None:
    """Convert a raw tire value: kpa x5, bar /10, psi as is; 255 = no reading."""
    number = parse_number(raw)
    if number is None or number == TIRE_INVALID or number < 0:
        return None
    match pressure_unit(unit):
        case UnitOfPressure.KPA:
            return _int_if_whole(number * 5)
        case UnitOfPressure.BAR:
            return round(number / 10, 1)
        case UnitOfPressure.PSI:
            return _int_if_whole(number)
    return None


def tire_row(status: Mapping[str, Any] | None, row: str) -> dict[str, Any] | None:
    """Tire block of "front" or "rear"."""
    block = get(status, "tire", TIRE_ROWS[row])
    return block if isinstance(block, dict) else None


def tire_value(status: Mapping[str, Any] | None, row: str, side: str) -> float | int | None:
    """Converted pressure of one tire."""
    block = tire_row(status, row)
    if block is None:
        return None
    return tire_pressure(block.get(side), block.get("unit"))


def tire_unit(status: Mapping[str, Any] | None, row: str) -> str | None:
    """HA pressure unit of a tire row."""
    block = tire_row(status, row)
    return pressure_unit(block.get("unit")) if block else None


# Status


def door_state(status: Mapping[str, Any] | None, row: str, side: str) -> str | None:
    """Door state ("locked", "closed", "open") of "front"/"back" + "left"/"right"."""
    value = get(status, "doors", DOOR_ROWS[row], side)
    return value.lower() if isinstance(value, str) else None


def door_states(status: Mapping[str, Any] | None) -> list[str]:
    """All known door states."""
    return [
        state
        for row in DOOR_ROWS
        for side in ("left", "right")
        if (state := door_state(status, row, side)) is not None
    ]


def is_open(value: Any) -> bool | None:
    """True when a state string is "open"."""
    if not isinstance(value, str) or value.lower() == INVALID:
        return None
    return value.lower() == "open"


def is_on(value: Any) -> bool | None:
    """True when a state string is "on"."""
    if not isinstance(value, str) or value.lower() == INVALID:
        return None
    return value.lower() == "on"


def is_active_level(value: Any) -> bool | None:
    """True for any level other than "off" (heaters, ventilation)."""
    if not isinstance(value, str) or value.lower() == INVALID:
        return None
    return value.lower() != "off"


def seat_heat(status: Mapping[str, Any] | None, row: str, side: str) -> str | None:
    """Seat heat level of "front"/"rear" + "left"/"right"."""
    value = get(status, "seats", SEAT_ROWS[row], side, "heat")
    return value if isinstance(value, str) else None


def warnings_list(status: Mapping[str, Any] | None) -> list[str] | None:
    """Active warnings, or None when the vehicle reports no warning list."""
    warnings = get(status, "warnings")
    if not isinstance(warnings, list):
        return None
    return [warning for warning in warnings if isinstance(warning, str)]


def has_warning(status: Mapping[str, Any] | None, name: str) -> bool | None:
    """Whether a warning is active; None without warning list."""
    warnings = warnings_list(status)
    if warnings is None:
        return None
    return name in warnings


# Batteries


def charging_status(batteries: Mapping[str, Any] | None) -> str | None:
    """Raw charge status (charging, notCharging, v2lOperating, ...)."""
    value = get(batteries, "charge", "status")
    return value if isinstance(value, str) and value else None


def is_charging(batteries: Mapping[str, Any] | None) -> bool | None:
    """Charging flag; falls back to the status string."""
    flag = get(batteries, "charge", "charging")
    if isinstance(flag, bool):
        return flag
    status = charging_status(batteries)
    if status is None:
        return None
    return status.lower() in CHARGING_STATUSES


def is_plugged_in(batteries: Mapping[str, Any] | None) -> bool | None:
    """Whether the charging cable is connected."""
    value = get(batteries, "charge", "plugin")
    if not isinstance(value, str):
        return None
    return value.lower() == "connected"


def status_contains(batteries: Mapping[str, Any] | None, *needles: str) -> bool | None:
    """Whether the charge status mentions one of the needles (v2l, v2x, ...)."""
    status = charging_status(batteries)
    if status is None:
        return None
    lowered = status.lower()
    return any(needle in lowered for needle in needles)


# Driving


def ignition_detail(driving: Mapping[str, Any] | None, kind: str) -> str | None:
    """Status of an ignitionDetails entry (ign1, ign3, acc)."""
    details = get(driving, "ignition", "ignitionDetails")
    if not isinstance(details, list):
        return None
    for detail in details:
        if isinstance(detail, dict) and detail.get("type") == kind:
            value = get(detail, "status")
            return value if isinstance(value, str) else None
    return None


def engine_running(driving: Mapping[str, Any] | None) -> bool | None:
    """ign1 on; falls back to ignition.status."""
    value = ignition_detail(driving, "ign1")
    if value is None:
        value = get(driving, "ignition", "status")
    return is_on(value)


# Location


def valid_location(locations: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Location block when it is WGS84 (type 0 or missing) with valid coordinates."""
    location = get(locations, "location")
    if not isinstance(location, dict):
        return None
    loc_type = location.get("type")
    if loc_type is not None and parse_number(loc_type) != 0:
        return None
    lat = parse_number(location.get("latitude"))
    lon = parse_number(location.get("longitude"))
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:
        return None
    return location
