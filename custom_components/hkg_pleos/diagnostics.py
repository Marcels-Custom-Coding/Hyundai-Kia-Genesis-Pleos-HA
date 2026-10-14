"""Diagnostics of a Pleos config entry."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_PENDING_MIGRATION, CONF_VEHICLES
from .coordinator import PleosConfigEntry

TO_REDACT = {
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    "vin",
    "VIN",
    "latitude",
    "longitude",
    "nickname",
    "name",
}


def _vehicle_aliases(vins: list[str]) -> dict[str, str]:
    """Stable placeholder per VIN ("vehicle_1", ...)."""
    return {vin: f"vehicle_{index}" for index, vin in enumerate(vins, start=1)}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PleosConfigEntry
) -> dict[str, Any]:
    """Return redacted entry data and the latest vehicle data."""
    vins = list(entry.data.get(CONF_VEHICLES, {}))
    runtime = getattr(entry, "runtime_data", None)
    coordinators = runtime.coordinators if runtime is not None else {}
    vins += [vin for vin in coordinators if vin not in vins]
    aliases = _vehicle_aliases(vins)

    data = dict(entry.data)
    if CONF_VEHICLES in data:
        data[CONF_VEHICLES] = {
            aliases[vin]: vehicle for vin, vehicle in data[CONF_VEHICLES].items()
        }
    if CONF_PENDING_MIGRATION in data:
        data[CONF_PENDING_MIGRATION] = [
            aliases.get(vin, REDACTED) for vin in data[CONF_PENDING_MIGRATION]
        ]

    vehicles = {
        aliases[vin]: {
            "type": coordinator.vehicle_type,
            "model": coordinator.model,
            "last_update_success": coordinator.last_update_success,
            "data": coordinator.data,
        }
        for vin, coordinator in coordinators.items()
    }

    return {
        "entry": {
            "title": REDACTED,
            "data": async_redact_data(data, TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "vehicles": async_redact_data(vehicles, TO_REDACT),
    }
