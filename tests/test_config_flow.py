"""Setup dialog."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_MIGRATE_VINS,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLES,
    DOMAIN,
    LEGACY_DOMAIN,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import CLIENT_ID, CLIENT_SECRET, VIN, error, load, mock_pleos

LABEL = "IONIQ 5 (…7890)"
CREDENTIALS = {CONF_CLIENT_ID: f" {CLIENT_ID} ", CONF_CLIENT_SECRET: CLIENT_SECRET}


async def _to_credentials(hass: HomeAssistant, via_guide: bool = False) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"brand": "hyundai"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["description_placeholders"]["account"] == "Hyundai Bluelink"
    if via_guide:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "guide"}
        )
        assert result["step_id"] == "guide"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    else:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "credentials"}
        )
    assert result["step_id"] == "credentials"
    return result["flow_id"]


async def test_full_setup(hass: HomeAssistant, pleos: AiohttpClientMocker) -> None:
    flow_id = await _to_credentials(hass, via_guide=True)
    result = await hass.config_entries.flow.async_configure(flow_id, CREDENTIALS)
    assert result["step_id"] == "vehicles"
    schema = result["data_schema"].schema
    assert LABEL in schema
    with patch("custom_components.hkg_pleos.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {"selected": [VIN], LABEL: "Ioni", CONF_SCAN_INTERVAL: 15}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hyundai – Ioni"
    assert result["data"][CONF_CLIENT_ID] == CLIENT_ID
    assert result["data"][CONF_VEHICLES] == {
        VIN: {"name": "Ioni", "model": "IONIQ 5", "model_code": "NE(NE)", "type": "EV"}
    }
    assert result["options"] == {CONF_SCAN_INTERVAL: 15}
    assert result["result"].unique_id == f"hyundai_{CLIENT_ID}"


async def test_wrong_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_pleos(aioclient_mock, token_status=404, token_json=error("40404"))
    flow_id = await _to_credentials(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, CREDENTIALS)
    assert result["errors"] == {"base": "invalid_auth"}

    mock_pleos(aioclient_mock, consent={"data": {"vehicles": []}})
    result = await hass.config_entries.flow.async_configure(flow_id, CREDENTIALS)
    assert result["errors"] == {"base": "no_vehicles"}

    mock_pleos(aioclient_mock, token_status=502, token_json=error("50201"))
    result = await hass.config_entries.flow.async_configure(flow_id, CREDENTIALS)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_already_configured(
    hass: HomeAssistant, pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    flow_id = await _to_credentials(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_offers_take_over(
    hass: HomeAssistant, pleos: AiohttpClientMocker
) -> None:
    old_entry = MockConfigEntry(domain=LEGACY_DOMAIN)
    old_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=old_entry.entry_id,
        identifiers={(LEGACY_DOMAIN, "abc"), (LEGACY_DOMAIN, f"vin:{VIN}")},
        name="My Car",
    )
    er.async_get(hass).async_get_or_create(
        "sensor",
        LEGACY_DOMAIN,
        "kia_uvo_abc_ev_battery_percentage",
        device_id=device.id,
        config_entry=old_entry,
    )
    flow_id = await _to_credentials(hass)
    await hass.config_entries.flow.async_configure(flow_id, CREDENTIALS)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"selected": [VIN], LABEL: "My Car", CONF_SCAN_INTERVAL: 10}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "migrate"
    with patch("custom_components.hkg_pleos.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {"next_step_id": "migrate_yes"}
        )
    assert result["data"][CONF_MIGRATE_VINS] == [VIN]


async def test_reauth(
    hass: HomeAssistant, pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch("custom_components.hkg_pleos.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CLIENT_ID: "new-id", CONF_CLIENT_SECRET: "new"}
        )
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_CLIENT_ID] == "new-id"
    assert config_entry.unique_id == "hyundai_new-id"


async def test_add_vehicle(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    consent = load("consent")
    consent["data"]["vehicles"].append(
        {
            "vin": "KNATEST0000000002",
            "nickname": "Zweiter",
            "name": "EV",
            "sellname": "EV6",
        }
    )
    mock_pleos(aioclient_mock, consent=consent)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "add_vehicle"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "add_credentials"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CLIENT_ID: "id-2", CONF_CLIENT_SECRET: "s"}
    )
    assert result["step_id"] == "vehicles"
    # Only the new car is offered.
    assert "EV6 (…0002)" in result["data_schema"].schema
    assert LABEL not in result["data_schema"].schema
    with patch("custom_components.hkg_pleos.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "selected": ["KNATEST0000000002"],
                "EV6 (…0002)": "Zweiter",
                CONF_SCAN_INTERVAL: 10,
            },
        )
    assert result["reason"] == "vehicle_added"
    assert set(config_entry.data[CONF_VEHICLES]) == {VIN, "KNATEST0000000002"}
    assert config_entry.title == "Hyundai – My Car, Zweiter"
    assert config_entry.unique_id == "hyundai_id-2"


async def test_options_rename(
    hass: HomeAssistant, pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    with patch("custom_components.hkg_pleos.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {LABEL: "Neu", CONF_SCAN_INTERVAL: 20}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_SCAN_INTERVAL] == 20
    assert config_entry.data[CONF_VEHICLES][VIN]["name"] == "Neu"
    assert config_entry.title == "Hyundai – Neu"
