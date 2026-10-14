"""Hyundai Kia Genesis (Pleos): vehicle data from the Pleos Vehicle Data API."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PleosAuthError, PleosClient, PleosError
from .const import (
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_MIGRATE_VINS,
    CONF_VEHICLES,
    DOMAIN,
)
from .coordinator import PleosConfigEntry, PleosCoordinator, PleosRuntimeData
from .migrate import async_take_over
from .repairs import (
    async_create_auth_issue,
    async_create_vehicle_removed_issue,
    async_delete_auth_issue,
    async_delete_vehicle_removed_issue,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: PleosConfigEntry) -> bool:
    """Log in, check which cars are still shared and start polling."""
    client = PleosClient(
        async_get_clientsession(hass),
        entry.data[CONF_BRAND],
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
    )
    try:
        shared = {v["vin"] for v in await client.async_get_vehicles()}
    except PleosAuthError as err:
        async_create_auth_issue(hass, entry)
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="auth_failed"
        ) from err
    except PleosError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    async_delete_auth_issue(hass, entry)

    if vins := entry.data.get(CONF_MIGRATE_VINS):
        async_take_over(hass, entry.entry_id, vins)
        data = {k: v for k, v in entry.data.items() if k != CONF_MIGRATE_VINS}
        hass.config_entries.async_update_entry(entry, data=data)

    runtime = PleosRuntimeData(client)
    for vin, vehicle in entry.data[CONF_VEHICLES].items():
        if vin not in shared:
            async_create_vehicle_removed_issue(hass, entry, vin, vehicle["name"])
            continue
        async_delete_vehicle_removed_issue(hass, entry, vin)
        runtime.coordinators[vin] = PleosCoordinator(hass, entry, client, vin)

    for coordinator in runtime.coordinators.values():
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: PleosConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PleosConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: PleosConfigEntry, device: object
) -> bool:
    """Allow deleting a car's device only when it is no longer configured."""
    vins = set(entry.data[CONF_VEHICLES])
    identifiers = getattr(device, "identifiers", set())
    return not any(domain == DOMAIN and ident in vins for domain, ident in identifiers)
