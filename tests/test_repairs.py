"""Tests for the repair flows."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.const import (
    CONF_PENDING_MIGRATION,
    CONF_VEHICLES,
    DOMAIN,
    VEHICLE_MODEL,
    VEHICLE_NAME,
    VEHICLE_TYPE,
)

from .conftest import VIN, entry_data, register_pleos, setup_entry

VIN2 = "KMHTEST0000000002"


@pytest.fixture
def two_vehicle_entry(hass: HomeAssistant) -> MockConfigEntry:
    """An entry with the fixture vehicle and a second one."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **entry_data(
                **{
                    VIN: {VEHICLE_NAME: "IONIQ 5", VEHICLE_MODEL: "IONIQ 5", VEHICLE_TYPE: "EV"},
                    VIN2: {VEHICLE_NAME: "Kona", VEHICLE_MODEL: "KONA", VEHICLE_TYPE: "HV"},
                }
            ),
            CONF_PENDING_MIGRATION: [VIN2],
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _start_fix(hass: HomeAssistant, issue_id: str) -> dict[str, Any]:
    assert await async_setup_component(hass, "repairs", {})
    manager = hass.data["repairs"]["flow_manager"]
    return await manager.async_init(DOMAIN, data={"issue_id": issue_id})


async def test_remove_vehicle_fix_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    two_vehicle_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Confirming removes the vehicle from the entry and its device."""
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, two_vehicle_entry)
    issue_id = f"vehicle_removed_{two_vehicle_entry.entry_id}_{VIN2}"
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None
    # A device left over from earlier, when the car was still in the key.
    gone = device_registry.async_get_or_create(
        config_entry_id=two_vehicle_entry.entry_id, identifiers={(DOMAIN, VIN2)}
    )

    result = await _start_fix(hass, issue_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {"name": "Kona", "vin_tail": VIN2[-4:]}

    manager = hass.data["repairs"]["flow_manager"]
    result = await manager.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert list(two_vehicle_entry.data[CONF_VEHICLES]) == [VIN]
    assert two_vehicle_entry.data.get(CONF_PENDING_MIGRATION, []) == []
    assert two_vehicle_entry.title == "Hyundai \N{EN DASH} IONIQ 5"
    assert device_registry.async_get(gone.id) is None
    assert device_registry.async_get_device(identifiers={(DOMAIN, VIN)}) is not None
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
    # The remaining vehicle keeps working after the reload.
    assert hass.states.get("sensor.ioniq_5_ev_range").state == "106"


async def test_fix_flow_entry_gone(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """An issue of a removed entry is dropped."""
    assert await setup_entry(hass, config_entry)
    issue_id = f"vehicle_removed_missing_{VIN}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="vehicle_removed",
        translation_placeholders={"name": "x", "vin_tail": VIN[-4:]},
        data={"entry_id": "missing", "vin": VIN},
    )

    result = await _start_fix(hass, issue_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_found"
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
