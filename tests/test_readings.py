"""Unit tests for the payload parsing helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.hkg_pleos import readings as r

from .conftest import load_json


@pytest.fixture
def data() -> dict[str, dict[str, Any]]:
    """The fixture "data" blocks keyed by endpoint."""
    return {
        endpoint: load_json(endpoint)["data"]
        for endpoint in ("batteries", "powertrains", "locations", "driving", "status")
    }


# get / parse_number


def test_get() -> None:
    """Nested lookups; missing paths and "invalid" give None."""
    block = {"a": [{"b": 1}, {"b": "Invalid "}], "c": None}
    assert r.get(block, "a", 0, "b") == 1
    assert r.get(block, "a", 1, "b") is None
    assert r.get(block, "a", 5, "b") is None
    assert r.get(block, "x", "y") is None
    assert r.get(block, "c", "d") is None
    assert r.get(None, "a") is None
    assert r.get("text", "a") is None
    assert r.get(block) is block


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, 5.0),
        (2.5, 2.5),
        (" 106 ", 106.0),
        ("-3.5", -3.5),
        ("", None),
        ("-", None),
        ("invalid", None),
        ("nan", None),
        ("inf", None),
        (float("nan"), None),
        (True, None),
        (None, None),
        ([1], None),
    ],
)
def test_parse_number(value: Any, expected: float | None) -> None:
    """Numbers and numeric strings; everything else is None."""
    assert r.parse_number(value) == expected


# units


def test_units() -> None:
    """Pleos units map case-insensitively to HA units."""
    assert r.distance_unit("km") == "km"
    assert r.distance_unit("Mile") == "mi"
    assert r.distance_unit("miles") == "mi"
    assert r.distance_unit("meter") == "m"
    assert r.distance_unit("feet") == "ft"
    assert r.distance_unit("parsec") is None
    assert r.distance_unit(None) is None
    assert r.temperature_unit("C") == "°C"
    assert r.temperature_unit("f") == "°F"
    assert r.temperature_unit(1) is None
    assert r.pressure_unit("KPA") == "kPa"
    assert r.pressure_unit("bar") == "bar"
    assert r.pressure_unit("psi") == "psi"
    assert r.speed_unit("kph") == "km/h"
    assert r.speed_unit("mph") == "mph"
    assert r.speed_unit("mps") == "m/s"


# timestamps


def test_parse_timestamp() -> None:
    """ISO strings become aware datetimes; naive ones are UTC."""
    assert r.parse_timestamp("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, tzinfo=UTC)
    naive = r.parse_timestamp("2026-01-01T01:02:03")
    assert naive == datetime(2026, 1, 1, 1, 2, 3, tzinfo=UTC)
    assert r.parse_timestamp("2026-01-01T02:00:00+02:00") == datetime(2026, 1, 1, tzinfo=UTC)
    assert r.parse_timestamp("yesterday") is None
    assert r.parse_timestamp("2026-13-45T00:00:00") is None
    assert r.parse_timestamp("") is None
    assert r.parse_timestamp(1700000000) is None


def test_latest_timestamp(data: dict[str, dict[str, Any]]) -> None:
    """The newest endpoint timestamp wins; broken ones are skipped."""
    assert r.latest_timestamp(data) == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    assert r.latest_timestamp(data, ["locations"]) == datetime(2026, 1, 1, tzinfo=UTC)
    assert r.latest_timestamp({"status": {"timestamp": "invalid"}, "driving": None}) is None
    assert r.latest_timestamp(None) is None
    assert r.latest_timestamp({}) is None


# ranges


def test_ranges_ev(data: dict[str, dict[str, Any]]) -> None:
    """An EV reports only the EV range, which is also the total."""
    powertrains = data["powertrains"]
    assert r.range_value(powertrains, "ev") == 106
    assert r.range_unit(powertrains, "ev") == "km"
    assert r.range_value(powertrains, "total") == 106
    assert r.range_value(powertrains, "fuel") is None
    assert r.find_range_entry(powertrains, "fuel") is None
    assert r.range_unit(powertrains, "fuel") is None


def test_ranges_phev() -> None:
    """A PHEV: EV, ICE and the combined entry as total."""
    powertrains = {
        "distanceToEmpties": [
            {"type": "EV", "value": "40", "unit": "km"},
            {"type": "ICE", "value": "500", "unit": "km"},
            {"type": "phev", "value": "540.5", "unit": "km"},
            {"type": "invalid", "value": "1", "unit": "km"},
            "garbage",
        ]
    }
    assert r.range_value(powertrains, "ev") == 40
    assert r.range_value(powertrains, "fuel") == 500
    assert r.range_value(powertrains, "total") == 540.5
    assert len(r.range_entries(powertrains)) == 3


def test_range_total_ambiguous() -> None:
    """EV and ICE without combined entry give no total."""
    powertrains = {
        "distanceToEmpties": [
            {"type": "EV", "value": "40", "unit": "km"},
            {"type": "ICE", "value": "500", "unit": "km"},
        ]
    }
    assert r.find_range_entry(powertrains, "total") is None


def test_range_unknown_kind() -> None:
    """A wrong kind is a programming error."""
    with pytest.raises(ValueError):
        r.find_range_entry({"distanceToEmpties": []}, "warp")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("106", 106), ("12.5", 12.5), (300, 300), ("-", None), ("0", None),
     ("4095", 4095), ("4096", None), ("invalid", None), (None, None)],
)  # fmt: skip
def test_parse_range(value: Any, expected: float | None) -> None:
    """Range strings; 0 and values above 4095 are no reading."""
    assert r.parse_range(value) == expected


def test_range_entries_missing() -> None:
    """No list, no entries."""
    assert r.range_entries(None) == []
    assert r.range_entries({"distanceToEmpties": "invalid"}) == []


def test_main_battery_ratio(data: dict[str, dict[str, Any]]) -> None:
    """remainRatio of the main battery only."""
    assert r.main_battery_ratio(data["powertrains"]) == 50
    assert r.main_battery_ratio({"batteries": [{"type": "aux", "remainRatio": 80}]}) is None
    assert r.main_battery_ratio({"batteries": [{"type": "main", "remainRatio": "x"}]}) is None
    assert r.main_battery_ratio({"batteries": None}) is None


# measured values and tires


def test_measured_value() -> None:
    """{"value", "unit"} blocks."""
    assert r.measured_value({"value": 21, "unit": "C"}) == 21
    assert r.measured_value({"value": 21.5}) == 21.5
    assert r.measured_value({"value": "invalid"}) is None
    assert r.measured_value(None) is None


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        (50, "kpa", 250),
        (49.5, "kPa", 247.5),
        (24, "bar", 2.4),
        (23, "bar", 2.3),
        (36, "psi", 36),
        (255, "kpa", None),
        ("255", "psi", None),
        (-1, "kpa", None),
        (50, "atm", None),
        (50, None, None),
        ("invalid", "kpa", None),
        (None, "kpa", None),
    ],
)
def test_tire_pressure(raw: Any, unit: Any, expected: float | None) -> None:
    """kpa x5, bar /10, psi as is; 255 means no reading."""
    assert r.tire_pressure(raw, unit) == expected


def test_tire_values(data: dict[str, dict[str, Any]]) -> None:
    """Tire rows: index 0 front, 1 rear."""
    status = data["status"]
    assert r.tire_value(status, "front", "left") == 250
    assert r.tire_value(status, "rear", "left") == 245
    assert r.tire_value(status, "rear", "right") is None
    assert r.tire_unit(status, "rear") == "kPa"
    assert r.tire_value({"tire": [{"left": 50}]}, "rear", "left") is None
    assert r.tire_unit({"tire": []}, "front") is None


# status


def test_doors(data: dict[str, dict[str, Any]]) -> None:
    """Door rows: index 0 front, 1 back."""
    status = data["status"]
    assert r.door_state(status, "front", "left") == "locked"
    assert r.door_state(status, "back", "right") == "open"
    assert r.door_states(status) == ["locked", "locked", "closed", "open"]
    assert r.door_state({"doors": [{"left": "LOCKED"}]}, "front", "left") == "locked"
    assert r.door_state({"doors": [{"left": "invalid"}]}, "front", "left") is None
    assert r.door_states(None) == []


@pytest.mark.parametrize(
    ("value", "is_open", "is_on", "active"),
    [
        ("open", True, False, True),
        ("closed", False, False, True),
        ("on", False, True, True),
        ("ON", False, True, True),
        ("off", False, False, False),
        ("low", False, False, True),
        ("invalid", None, None, None),
        (None, None, None, None),
        (1, None, None, None),
    ],
)
def test_state_strings(
    value: Any, is_open: bool | None, is_on: bool | None, active: bool | None
) -> None:
    """open / on / active level checks."""
    assert r.is_open(value) is is_open
    assert r.is_on(value) is is_on
    assert r.is_active_level(value) is active


def test_seat_heat(data: dict[str, dict[str, Any]]) -> None:
    """Seat rows: index 0 front, 1 rear."""
    assert r.seat_heat(data["status"], "front", "left") == "low"
    assert r.seat_heat(data["status"], "rear", "right") == "off"
    assert r.seat_heat({"seats": []}, "front", "left") is None


def test_warnings(data: dict[str, dict[str, Any]]) -> None:
    """Warnings list; None when not reported."""
    status = data["status"]
    assert r.warnings_list(status) == ["washFluid", "tirePressureRearLeft"]
    assert r.has_warning(status, "washFluid") is True
    assert r.has_warning(status, "lowFuel") is False
    assert r.warnings_list({"warnings": ["a", 1, None]}) == ["a"]
    assert r.warnings_list({"warnings": "invalid"}) is None
    assert r.has_warning({}, "washFluid") is None


# batteries


def test_charging(data: dict[str, dict[str, Any]]) -> None:
    """Charging flag, status and plug."""
    batteries = data["batteries"]
    assert r.charging_status(batteries) == "charging"
    assert r.is_charging(batteries) is True
    assert r.is_plugged_in(batteries) is True


@pytest.mark.parametrize(
    ("charge", "charging"),
    [
        ({"status": "fastCharging"}, True),
        ({"status": "wirelessCharging"}, True),
        ({"status": "notCharging"}, False),
        ({"status": "charging", "charging": False}, False),
        ({"status": "invalid"}, None),
        ({}, None),
    ],
)
def test_is_charging_fallback(charge: dict[str, Any], charging: bool | None) -> None:
    """Without the flag the status string decides."""
    assert r.is_charging({"charge": charge}) is charging


def test_plug_and_status_helpers() -> None:
    """Plug state and status matching."""
    assert r.is_plugged_in({"charge": {"plugin": "disconnected"}}) is False
    assert r.is_plugged_in({"charge": {"plugin": "invalid"}}) is None
    assert r.is_plugged_in(None) is None
    batteries = {"charge": {"status": "v2lOperating"}}
    assert r.status_is(batteries, "v2lOperating") is True
    assert r.status_is(batteries, "v2xOperating") is False
    assert r.status_is({"charge": {"status": "v2lStop"}}, "v2lOperating") is False
    assert r.status_is({}, "v2lOperating") is None
    assert r.status_contains(batteries, "v2l") is True
    assert r.status_contains(batteries, "v2x", "v2g") is False
    assert r.status_contains(None, "v2l") is None
    assert r.charging_status({"charge": {"status": ""}}) is None


# driving


def test_ignition(data: dict[str, dict[str, Any]]) -> None:
    """ignitionDetails entries and the engine fallback."""
    driving = data["driving"]
    assert r.ignition_detail(driving, "ign3") == "on"
    assert r.ignition_detail(driving, "acc") == "off"
    assert r.ignition_detail(driving, "ign9") is None
    assert r.engine_running(driving) is False
    assert r.engine_running({"ignition": {"status": "on"}}) is True
    assert r.engine_running({"ignition": {"status": "invalid"}}) is None
    assert r.ignition_detail({"ignition": {}}, "ign1") is None


# location


def test_valid_location(data: dict[str, dict[str, Any]]) -> None:
    """WGS84 fixes with plausible coordinates only."""
    assert r.valid_location(data["locations"])["latitude"] == 52.5
    assert r.valid_location({"location": {"latitude": "52.5", "longitude": "13.4"}})
    assert r.valid_location({"location": {"latitude": 1, "longitude": 2, "type": "0"}})
    assert r.valid_location({"location": {"latitude": 1, "longitude": 2, "type": 1}}) is None
    assert r.valid_location({"location": {"latitude": 0, "longitude": 0}}) is None
    assert r.valid_location({"location": {"latitude": -91, "longitude": 0}}) is None
    assert r.valid_location({"location": {"latitude": 1, "longitude": 181}}) is None
    assert r.valid_location({"location": {"latitude": 1}}) is None
    assert r.valid_location({"location": "invalid"}) is None
    assert r.valid_location(None) is None
