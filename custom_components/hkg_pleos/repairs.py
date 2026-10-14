"""Repair issues: expired key and vehicles that left the key."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .const import (
    BRAND_NAMES,
    CONF_BRAND,
    CONF_VEHICLES,
    DOMAIN,
    ISSUE_AUTH_FAILED,
    ISSUE_VEHICLE_REMOVED,
    PLAYGROUND_URL,
)
from .migrate import find_device


def _auth_issue_id(entry: ConfigEntry) -> str:
    return f"{ISSUE_AUTH_FAILED}_{entry.entry_id}"


def _vehicle_issue_id(entry: ConfigEntry, vin: str) -> str:
    return f"{ISSUE_VEHICLE_REMOVED}_{entry.entry_id}_{vin}"


@callback
def async_create_auth_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Point the user to the reauthentication."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _auth_issue_id(entry),
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_AUTH_FAILED,
        translation_placeholders={
            "brand": BRAND_NAMES.get(entry.data.get(CONF_BRAND, ""), ""),
            "title": entry.title,
            "playground_url": PLAYGROUND_URL,
        },
        learn_more_url=PLAYGROUND_URL,
    )


@callback
def async_delete_auth_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, _auth_issue_id(entry))


@callback
def async_create_vehicle_removed_issue(
    hass: HomeAssistant, entry: ConfigEntry, vin: str, name: str
) -> None:
    """Offer to remove a car that is no longer shared with the key."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _vehicle_issue_id(entry, vin),
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_VEHICLE_REMOVED,
        translation_placeholders={"name": name, "vin_end": vin[-4:]},
        data={"entry_id": entry.entry_id, "vin": vin},
    )


@callback
def async_delete_vehicle_removed_issue(
    hass: HomeAssistant, entry: ConfigEntry, vin: str
) -> None:
    ir.async_delete_issue(hass, DOMAIN, _vehicle_issue_id(entry, vin))


class VehicleRemovedRepairFlow(RepairsFlow):
    """Remove the car and its entities after confirmation."""

    def __init__(self, entry_id: str, vin: str) -> None:
        self._entry_id = entry_id
        self._vin = vin

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is not None:
                vehicles = dict(entry.data.get(CONF_VEHICLES, {}))
                vehicles.pop(self._vin, None)
                device = find_device(self.hass, (DOMAIN, self._vin))
                if device is not None:
                    dr.async_get(self.hass).async_update_device(
                        device.id, remove_config_entry_id=entry.entry_id
                    )
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_VEHICLES: vehicles}
                )
            return self.async_create_entry(data={})
        issue = ir.async_get(self.hass).async_get_issue(self.handler, self.issue_id)
        placeholders = dict(issue.translation_placeholders or {}) if issue else {}
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the flow behind a fixable issue."""
    assert data is not None
    return VehicleRemovedRepairFlow(str(data["entry_id"]), str(data["vin"]))
