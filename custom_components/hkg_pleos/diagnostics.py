"""Diagnostics download, with key, VIN and position removed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_VEHICLES
from .coordinator import PleosConfigEntry

TO_REDACT = {
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    "vin",
    "latitude",
    "longitude",
    "altitude",
    "heading",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PleosConfigEntry
) -> dict[str, Any]:
    """Return what helps to analyse a problem, without personal data."""
    data = dict(entry.data)
    # VINs are dictionary keys here; replace them with a neutral number.
    data[CONF_VEHICLES] = {
        f"vehicle_{i}": vehicle
        for i, vehicle in enumerate(entry.data[CONF_VEHICLES].values(), start=1)
    }
    data.pop("migrate_vins", None)
    vehicles = {}
    for i, coordinator in enumerate(entry.runtime_data.coordinators.values(), start=1):
        vehicles[f"vehicle_{i}"] = {
            "last_update_success": coordinator.last_update_success,
            "data": async_redact_data(coordinator.data or {}, TO_REDACT),
        }
    return {
        "entry": async_redact_data(data, TO_REDACT),
        "options": dict(entry.options),
        "vehicles": vehicles,
    }
