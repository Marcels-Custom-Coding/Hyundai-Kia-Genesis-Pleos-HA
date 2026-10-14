"""Repair flows for Hyundai Kia Genesis (Pleos)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr, issue_registry as ir
import voluptuous as vol

from .config_flow import entry_title
from .const import (
    CONF_BRAND,
    CONF_PENDING_MIGRATION,
    CONF_VEHICLES,
    DOMAIN,
    ISSUE_VEHICLE_REMOVED,
    VEHICLE_NAME,
)


class VehicleRemovedRepairFlow(RepairsFlow):
    """Offer to remove a car that is no longer part of the API key."""

    def __init__(self, entry_id: str, vin: str) -> None:
        """Initialize the flow."""
        self._entry_id = entry_id
        self._vin = vin

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Start with the confirmation."""
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask, then remove the car from the entry and the device registry."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
            return self.async_abort(reason="entry_not_found")

        vehicles: dict[str, Any] = dict(entry.data.get(CONF_VEHICLES, {}))
        name = (vehicles.get(self._vin) or {}).get(VEHICLE_NAME) or self._vin[-4:]

        if user_input is not None:
            vehicles.pop(self._vin, None)
            data = {**entry.data, CONF_VEHICLES: vehicles}
            if pending := data.get(CONF_PENDING_MIGRATION):
                data[CONF_PENDING_MIGRATION] = [v for v in pending if v != self._vin]
            self.hass.config_entries.async_update_entry(
                entry,
                title=entry_title(entry.data[CONF_BRAND], vehicles),
                data=data,
            )

            device_registry = dr.async_get(self.hass)
            if device := device_registry.async_get_device(identifiers={(DOMAIN, self._vin)}):
                device_registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )

            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"name": name, "vin_tail": self._vin[-4:]},
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a repair issue."""
    if (
        issue_id.startswith(ISSUE_VEHICLE_REMOVED)
        and data
        and isinstance(data.get("entry_id"), str)
        and isinstance(data.get("vin"), str)
    ):
        return VehicleRemovedRepairFlow(str(data["entry_id"]), str(data["vin"]))
    return ConfirmRepairFlow()
