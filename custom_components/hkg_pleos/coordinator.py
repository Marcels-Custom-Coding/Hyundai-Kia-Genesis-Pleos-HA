"""One update coordinator per vehicle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    PleosAuthError,
    PleosClient,
    PleosConnectionError,
    PleosError,
    PleosVehicleGoneError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_VEHICLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENDPOINTS,
)
from .data import VehicleData
from .repairs import async_create_auth_issue, async_create_vehicle_removed_issue

_LOGGER = logging.getLogger(__name__)


@dataclass
class PleosRuntimeData:
    """Shared objects of one config entry."""

    client: PleosClient
    coordinators: dict[str, PleosCoordinator] = field(default_factory=dict)


type PleosConfigEntry = ConfigEntry[PleosRuntimeData]


class PleosCoordinator(DataUpdateCoordinator[VehicleData]):
    """Polls all Pleos endpoints of one vehicle."""

    config_entry: PleosConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PleosConfigEntry,
        client: PleosClient,
        vin: str,
    ) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} …{vin[-4:]}",
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self.vin = vin

    @property
    def vehicle(self) -> dict[str, Any]:
        """Stored vehicle settings (name, model, type)."""
        return self.config_entry.data[CONF_VEHICLES][self.vin]

    async def _async_update_data(self) -> VehicleData:
        results = await asyncio.gather(
            *(self.client.async_get_endpoint(self.vin, ep) for ep in ENDPOINTS),
            return_exceptions=True,
        )
        previous = self.data or {}
        data: VehicleData = {}
        failures: list[BaseException] = []
        for endpoint, result in zip(ENDPOINTS, results, strict=True):
            if isinstance(result, PleosAuthError):
                async_create_auth_issue(self.hass, self.config_entry)
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="auth_failed"
                ) from result
            if isinstance(result, PleosVehicleGoneError):
                async_create_vehicle_removed_issue(
                    self.hass, self.config_entry, self.vin, self.vehicle["name"]
                )
                raise UpdateFailed(
                    translation_domain=DOMAIN, translation_key="vehicle_removed"
                ) from result
            if isinstance(result, BaseException):
                if not isinstance(result, PleosError):
                    raise result
                _LOGGER.debug("%s for …%s failed: %s", endpoint, self.vin[-4:], result)
                failures.append(result)
                # Keep the last known values of this endpoint.
                data[endpoint] = previous.get(endpoint)
            else:
                data[endpoint] = result
        if len(failures) == len(ENDPOINTS):
            key = (
                "cannot_connect"
                if isinstance(failures[0], PleosConnectionError)
                else "update_failed"
            )
            raise UpdateFailed(translation_domain=DOMAIN, translation_key=key)
        return data
