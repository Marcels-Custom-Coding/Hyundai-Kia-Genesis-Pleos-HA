"""Read values out of the Pleos responses.

Every helper takes the coordinator data (endpoint name -> data block or None)
and returns None when the value is missing, null or reported as invalid.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.util import dt as dt_util

type VehicleData = dict[str, dict[str, Any] | None]

ROWS = {"front": 0, "rear": 1}

DISTANCE_UNITS = {
    "km": UnitOfLength.KILOMETERS,
    "miles": UnitOfLength.MILES,
    "mile": UnitOfLength.MILES,
    "meter": UnitOfLength.METERS,
    "feet": UnitOfLength.FEET,
}
PRESSURE_UNITS = {
    "psi": UnitOfPressure.PSI,
    "kpa": UnitOfPressure.KPA,
    "bar": UnitOfPressure.BAR,
}
TEMPERATURE_UNITS = {"C": UnitOfTemperature.CELSIUS, "F": UnitOfTemperature.FAHRENHEIT}
SPEED_UNITS = {
    "kph": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "mph": UnitOfSpeed.MILES_PER_HOUR,
    "mps": UnitOfSpeed.METERS_PER_SECOND,
}


def get(data: VehicleData, endpoint: str, *path: str | int) -> Any:
    """Walk into a nested response, None on any gap."""
    value: Any = data.get(endpoint)
    for key in path:
        if isinstance(key, int):
            if not isinstance(value, list) or len(value) <= key:
                return None
            value = value[key]
        else:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if value is None:
            return None
    if value == "invalid":
        return None
    return value


def number(value: Any) -> float | None:
    """Numbers sometimes come as strings (range); 'invalid' means unknown."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except TypeError, ValueError:
        return None
    return int(result) if result.is_integer() else result


def flag(value: Any, on: str = "on") -> bool | None:
    """String status to bool (on/off, open/closed …)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return value == on


# --- batteries -------------------------------------------------------------


def charge(data: VehicleData, key: str) -> Any:
    return get(data, "batteries", "charge", key)


def target_soc(data: VehicleData, kind: str) -> float | None:
    return number(get(data, "batteries", "charge", "targetStateOfCharge", kind))


def charge_status_is(data: VehicleData, status: str) -> bool | None:
    current = charge(data, "status")
    return None if current is None else current == status


def plugged_in(data: VehicleData) -> bool | None:
    plugin = charge(data, "plugin")
    return None if plugin is None else plugin == "connected"


# --- powertrains -----------------------------------------------------------


def _dte_entries(data: VehicleData) -> list[dict[str, Any]]:
    entries = get(data, "powertrains", "distanceToEmpties")
    if not isinstance(entries, list):
        return []
    return [
        e
        for e in entries
        if isinstance(e, dict)
        and e.get("type") not in (None, "invalid")
        and number(e.get("value")) is not None
    ]


FUEL_DTE_TYPES = ("ICE", "HEV", "FCEV")


def _dte(data: VehicleData, types: tuple[str, ...]) -> dict[str, Any] | None:
    for entry in _dte_entries(data):
        if entry.get("type") in types:
            return entry
    return None


def _total_dte(data: VehicleData) -> dict[str, Any] | None:
    if entry := _dte(data, ("PHEV",)):
        return entry
    entries = _dte_entries(data)
    return entries[0] if len(entries) == 1 else None


def dte_entry(data: VehicleData, which: str) -> dict[str, Any] | None:
    if which == "ev":
        return _dte(data, ("EV",))
    if which == "fuel":
        return _dte(data, FUEL_DTE_TYPES)
    return _total_dte(data)


def dte_value(data: VehicleData, which: str) -> float | None:
    entry = dte_entry(data, which)
    return None if entry is None else number(entry.get("value"))


def dte_unit(data: VehicleData, which: str) -> str | None:
    entry = dte_entry(data, which)
    return None if entry is None else DISTANCE_UNITS.get(entry.get("unit") or "")


def aux_battery(data: VehicleData) -> float | None:
    """State of charge of a non-traction battery, if Pleos reports one."""
    batteries = get(data, "powertrains", "batteries")
    if not isinstance(batteries, list):
        return None
    for battery in batteries:
        if isinstance(battery, dict) and battery.get("type") not in (None, "main"):
            return number(battery.get("remainRatio"))
    return None


# --- driving ---------------------------------------------------------------


def ignition(data: VehicleData, kind: str) -> bool | None:
    details = get(data, "driving", "ignition", "ignitionDetails")
    if not isinstance(details, list):
        return None
    for detail in details:
        if isinstance(detail, dict) and detail.get("type") == kind:
            status = detail.get("status")
            return None if status in (None, "invalid") else status == "on"
    return None


# --- status ----------------------------------------------------------------


def door(data: VehicleData, row: str, side: str) -> str | None:
    """open, closed or locked."""
    return get(data, "status", "doors", ROWS[row], side)


def door_open(data: VehicleData, row: str, side: str) -> bool | None:
    state = door(data, row, side)
    return None if state is None else state == "open"


def door_unlocked(data: VehicleData, row: str, side: str) -> bool | None:
    """Lock binary sensors are on when unlocked (Home Assistant convention)."""
    state = door(data, row, side)
    return None if state is None else state != "locked"


def any_door_unlocked(data: VehicleData) -> bool | None:
    states = [door(data, row, side) for row in ROWS for side in ("left", "right")]
    known = [s for s in states if s is not None]
    if not known:
        return None
    return any(s != "locked" for s in known)


def tire_pressure(data: VehicleData, row: str, side: str) -> float | None:
    tire = get(data, "status", "tire", ROWS[row])
    if not isinstance(tire, dict):
        return None
    raw = number(tire.get(side))
    if raw is None or raw == 255:
        return None
    unit = tire.get("unit")
    if unit == "kpa":
        return raw * 5
    if unit == "bar":
        return round(raw / 10, 1)
    return raw


def tire_unit(data: VehicleData, row: str, side: str) -> str | None:
    unit = get(data, "status", "tire", ROWS[row], "unit")
    return PRESSURE_UNITS.get(unit or "")


def warnings(data: VehicleData) -> list[str] | None:
    value = get(data, "status", "warnings")
    return value if isinstance(value, list) else None


def warning(data: VehicleData, *names: str) -> bool | None:
    active = warnings(data)
    if active is None:
        return None
    return any(name in active for name in names)


def seat(data: VehicleData, row: str, side: str, key: str) -> str | None:
    return get(data, "status", "seats", ROWS[row], side, key)


def temperature(data: VehicleData, *path: str) -> tuple[float | None, str | None]:
    block = get(data, "status", *path)
    if not isinstance(block, dict):
        return None, None
    return number(block.get("value")), TEMPERATURE_UNITS.get(block.get("unit") or "")


# --- timestamps ------------------------------------------------------------


def timestamp(data: VehicleData, endpoint: str) -> datetime | None:
    value = get(data, endpoint, "timestamp")
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def last_updated(data: VehicleData) -> datetime | None:
    stamps = [s for ep in data if (s := timestamp(data, ep)) is not None]
    return max(stamps) if stamps else None
