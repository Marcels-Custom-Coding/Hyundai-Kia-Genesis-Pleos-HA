"""Tests for the diagnostics of a config entry."""

from __future__ import annotations

import json

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.hkg_pleos.const import CONF_PENDING_MIGRATION
from custom_components.hkg_pleos.diagnostics import async_get_config_entry_diagnostics

from .conftest import CLIENT_ID, CLIENT_SECRET, VIN, setup_entry


async def test_diagnostics_redacted(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """No VIN, key, name or position leaves the house."""
    assert await setup_entry(hass, config_entry)

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    text = json.dumps(diagnostics)

    for secret in (VIN, VIN[-8:], CLIENT_ID, CLIENT_SECRET, "52.5", "13.4"):
        assert secret not in text, secret

    entry = diagnostics["entry"]
    assert entry["title"] == REDACTED
    assert entry["data"]["client_id"] == REDACTED
    assert entry["data"]["client_secret"] == REDACTED
    assert list(entry["data"]["vehicles"]) == ["vehicle_1"]
    assert entry["data"]["vehicles"]["vehicle_1"]["name"] == REDACTED
    assert entry["options"] == {"scan_interval": 10}

    vehicle = diagnostics["vehicles"]["vehicle_1"]
    assert vehicle["type"] == "EV"
    assert vehicle["last_update_success"] is True
    location = vehicle["data"]["locations"]["location"]
    assert location["latitude"] == REDACTED
    assert location["longitude"] == REDACTED
    assert location["heading"] == 90
    assert vehicle["data"]["status"]["hood"] == "closed"


async def test_diagnostics_not_loaded(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, config_entry: MockConfigEntry
) -> None:
    """An entry that never loaded still returns redacted data."""
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, CONF_PENDING_MIGRATION: [VIN, "OTHER"]}
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["vehicles"] == {}
    assert diagnostics["entry"]["data"][CONF_PENDING_MIGRATION] == ["vehicle_1", REDACTED]
    assert VIN not in json.dumps(diagnostics)
