"""Hyundai Kia Genesis (Pleos) integration: vehicle data via the Pleos API."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PleosAuthError, PleosClient, PleosError, PleosRegionError
from .const import (
    BRANDS,
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PENDING_MIGRATION,
    CONF_VEHICLES,
    DOMAIN,
    ISSUE_AUTH_FAILED,
    VEHICLE_NAME,
)
from .coordinator import (
    PleosConfigEntry,
    PleosCoordinator,
    PleosRuntimeData,
    create_vehicle_removed_issue,
    vehicle_removed_issue_id,
)
from .migrate import async_migrate_legacy_entities

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
]


def auth_issue_id(entry_id: str) -> str:
    """Issue ID for "API key no longer valid"."""
    return f"{ISSUE_AUTH_FAILED}_{entry_id}"


def _raise_auth_issue(hass: HomeAssistant, entry: PleosConfigEntry) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        auth_issue_id(entry.entry_id),
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_AUTH_FAILED,
        translation_placeholders={"brand": BRANDS.get(entry.data[CONF_BRAND], "")},
    )


async def async_setup_entry(hass: HomeAssistant, entry: PleosConfigEntry) -> bool:
    """Set up one Pleos API key (one brand, one or more vehicles)."""
    client = PleosClient(
        async_get_clientsession(hass),
        entry.data[CONF_BRAND],
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
    )

    try:
        vehicles = await client.async_get_vehicles()
    except (PleosAuthError, PleosRegionError) as err:
        _raise_auth_issue(hass, entry)
        raise ConfigEntryAuthFailed("API key no longer accepted") from err
    except PleosError as err:
        raise ConfigEntryNotReady(f"Pleos not reachable: {err}") from err

    ir.async_delete_issue(hass, DOMAIN, auth_issue_id(entry.entry_id))

    available = {vehicle["vin"] for vehicle in vehicles}
    runtime = PleosRuntimeData(client=client)

    for vin, vehicle in entry.data.get(CONF_VEHICLES, {}).items():
        if vin not in available:
            create_vehicle_removed_issue(
                hass, entry, vin, vehicle.get(VEHICLE_NAME) or vin[-4:]
            )
            continue
        ir.async_delete_issue(hass, DOMAIN, vehicle_removed_issue_id(entry.entry_id, vin))
        runtime.coordinators[vin] = PleosCoordinator(hass, entry, client, vin, vehicle)

    for coordinator in runtime.coordinators.values():
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = runtime

    if pending := entry.data.get(CONF_PENDING_MIGRATION):
        await async_migrate_legacy_entities(hass, entry, runtime, list(pending))
        hass.config_entries.async_update_entry(
            entry,
            data={k: v for k, v in entry.data.items() if k != CONF_PENDING_MIGRATION},
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: PleosConfigEntry) -> None:
    """Reload when options (interval, names) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PleosConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: PleosConfigEntry) -> None:
    """Clean up repair issues of a removed entry."""
    ir.async_delete_issue(hass, DOMAIN, auth_issue_id(entry.entry_id))
    for vin in entry.data.get(CONF_VEHICLES, {}):
        ir.async_delete_issue(hass, DOMAIN, vehicle_removed_issue_id(entry.entry_id, vin))
