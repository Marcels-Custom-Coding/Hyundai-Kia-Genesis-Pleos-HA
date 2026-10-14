"""Data update coordinator: one per vehicle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    PleosAuthError,
    PleosClient,
    PleosConnectionError,
    PleosError,
    PleosVehicleNotFoundError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ISSUE_VEHICLE_REMOVED,
    VEHICLE_MODEL,
    VEHICLE_NAME,
    VEHICLE_TYPE,
)

_LOGGER = logging.getLogger(__name__)

type PleosConfigEntry = ConfigEntry[PleosRuntimeData]


@dataclass
class PleosRuntimeData:
    """Objects shared by the platforms of one config entry."""

    client: PleosClient
    coordinators: dict[str, PleosCoordinator] = field(default_factory=dict)


def vehicle_removed_issue_id(entry_id: str, vin: str) -> str:
    """Issue ID for "vehicle no longer in key"."""
    return f"{ISSUE_VEHICLE_REMOVED}_{entry_id}_{vin}"


def create_vehicle_removed_issue(
    hass: HomeAssistant, entry: ConfigEntry, vin: str, name: str
) -> None:
    """Raise a fixable repair issue offering to remove the vehicle."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        vehicle_removed_issue_id(entry.entry_id, vin),
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_VEHICLE_REMOVED,
        translation_placeholders={"name": name, "vin_tail": vin[-4:]},
        data={"entry_id": entry.entry_id, "vin": vin},
    )


class PleosCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any] | None]]):
    """Fetches all endpoints of one vehicle.

    ``data`` maps each endpoint name (see const.ENDPOINTS) to its "data" block,
    or None when the vehicle has not reported that block.
    """

    config_entry: PleosConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PleosConfigEntry,
        client: PleosClient,
        vin: str,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {vin[-4:]}",
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self.vin = vin
        self.vehicle_name: str = vehicle.get(VEHICLE_NAME) or vin
        self.model: str | None = vehicle.get(VEHICLE_MODEL)
        self.vehicle_type: str | None = vehicle.get(VEHICLE_TYPE)

    async def _async_update_data(self) -> dict[str, dict[str, Any] | None]:
        try:
            data = await self.client.async_get_vehicle_data(self.vin)
        except PleosAuthError as err:
            raise ConfigEntryAuthFailed("API key no longer accepted") from err
        except PleosVehicleNotFoundError as err:
            create_vehicle_removed_issue(self.hass, self.config_entry, self.vin, self.vehicle_name)
            raise UpdateFailed("Vehicle is no longer part of the API key") from err
        except PleosConnectionError as err:
            raise UpdateFailed(f"Pleos not reachable: {err}") from err
        except PleosError as err:
            raise UpdateFailed(f"Pleos error: {err}") from err
        ir.async_delete_issue(
            self.hass, DOMAIN, vehicle_removed_issue_id(self.config_entry.entry_id, self.vin)
        )
        return data
