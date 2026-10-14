"""Tests for the config, reconfigure, reauth and options flows."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hkg_pleos.api import (
    PleosAuthError,
    PleosConnectionError,
    PleosRegionError,
)
from custom_components.hkg_pleos.const import (
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PENDING_MIGRATION,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LEGACY_DOMAIN,
    VEHICLE_MODEL,
    VEHICLE_NAME,
    VEHICLE_TYPE,
)

from .conftest import BRAND, CLIENT_ID, CLIENT_SECRET, VIN

pytestmark = pytest.mark.usefixtures("mock_setup_entry")

VIN2 = "KMHTEST0000000002"
VEHICLE1 = {"vin": VIN, "nickname": "IONIQ 5", "sellname": "IONIQ 5", "type": "EV"}
VEHICLE2 = {"vin": VIN2, "name": "SX2(SX2)", "sellname": "KONA", "type": "HV"}
CREDENTIALS = {CONF_CLIENT_ID: CLIENT_ID, CONF_CLIENT_SECRET: CLIENT_SECRET}
NEW_CREDENTIALS = {CONF_CLIENT_ID: "new-client-id", CONF_CLIENT_SECRET: "new-secret"}
DASH = "\N{EN DASH}"


@contextmanager
def pleos_key(
    vehicles: list[dict[str, Any]] | None = None, error: Exception | None = None
) -> Generator[None]:
    """Patch the client: login fails with ``error`` or returns ``vehicles``."""
    with (
        patch(
            "custom_components.hkg_pleos.api.PleosClient.async_login",
            AsyncMock(side_effect=error),
        ),
        patch(
            "custom_components.hkg_pleos.api.PleosClient.async_get_vehicles",
            AsyncMock(return_value=[VEHICLE1] if vehicles is None else vehicles),
        ),
    ):
        yield


async def _credentials_step(hass: HomeAssistant, brand: str = BRAND) -> FlowResult:
    """Start the user flow and go straight to the credentials form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_BRAND: brand})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "credentials"}
    )
    assert result["step_id"] == "credentials"
    return result


async def _submit_key(
    hass: HomeAssistant,
    flow_id: str,
    vehicles: list[dict[str, Any]] | None = None,
    error: Exception | None = None,
    credentials: dict[str, str] = CREDENTIALS,
) -> FlowResult:
    with pleos_key(vehicles, error):
        return await hass.config_entries.flow.async_configure(flow_id, credentials)


def _schema_keys(result: FlowResult) -> list[str]:
    return [str(key) for key in result["data_schema"].schema]


def _add_legacy_device(hass: HomeAssistant, vin: str) -> None:
    legacy = MockConfigEntry(domain=LEGACY_DOMAIN)
    legacy.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=legacy.entry_id,
        identifiers={(LEGACY_DOMAIN, "abc123"), (LEGACY_DOMAIN, f"vin:{vin}")},
    )


# ------------------------------------------------------------------ user flow


async def test_full_flow(hass: HomeAssistant) -> None:
    """Brand, menu, guide, credentials, vehicles and finish create the entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_BRAND: BRAND})
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "key_menu"
    assert result["menu_options"] == ["credentials", "guide"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "guide"}
    )
    assert result["step_id"] == "guide"
    assert result["description_placeholders"]["account"] == "Bluelink"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "credentials"

    result = await _submit_key(
        hass,
        result["flow_id"],
        [VEHICLE1, VEHICLE2],
        credentials={CONF_CLIENT_ID: f" {CLIENT_ID} ", CONF_CLIENT_SECRET: CLIENT_SECRET},
    )
    assert result["step_id"] == "vehicle"
    assert result["description_placeholders"]["index"] == "1"
    assert result["description_placeholders"]["count"] == "2"
    assert result["description_placeholders"]["vin_tail"] == VIN[-4:]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": True, "name": "My Ioniq"}
    )
    assert result["step_id"] == "vehicle"
    assert result["description_placeholders"]["index"] == "2"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": True, "name": "  "}
    )
    assert result["step_id"] == "finish"
    assert "migrate" not in _schema_keys(result)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 15}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # An empty name falls back to the sellname, not the model code in "name".
    assert result["title"] == f"Hyundai {DASH} My Ioniq, KONA"
    entry = result["result"]
    assert entry.unique_id == f"{BRAND}_{CLIENT_ID}"
    assert entry.data == {
        CONF_BRAND: BRAND,
        CONF_CLIENT_ID: CLIENT_ID,
        CONF_CLIENT_SECRET: CLIENT_SECRET,
        CONF_VEHICLES: {
            VIN: {VEHICLE_NAME: "My Ioniq", VEHICLE_MODEL: "IONIQ 5", VEHICLE_TYPE: "EV"},
            VIN2: {VEHICLE_NAME: "KONA", VEHICLE_MODEL: "KONA", VEHICLE_TYPE: "HV"},
        },
    }
    assert entry.options == {CONF_SCAN_INTERVAL: 15}


@pytest.mark.parametrize(
    ("error", "vehicles", "expected"),
    [
        (PleosAuthError(), None, "invalid_auth"),
        (PleosRegionError("region"), None, "region_unsupported"),
        (PleosConnectionError("timeout"), None, "cannot_connect"),
        (RuntimeError("boom"), None, "unknown"),
        (None, [], "no_vehicles"),
    ],
)
async def test_credentials_errors(
    hass: HomeAssistant,
    error: Exception | None,
    vehicles: list[dict[str, Any]] | None,
    expected: str,
) -> None:
    """Key problems are shown on the credentials form; a fixed key continues."""
    result = await _credentials_step(hass)

    result = await _submit_key(hass, result["flow_id"], vehicles, error)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "credentials"
    assert result["errors"] == {"base": expected}

    result = await _submit_key(hass, result["flow_id"])
    assert result["step_id"] == "vehicle"


async def test_already_configured(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The same brand and client ID abort."""
    result = await _credentials_step(hass)
    result = await _submit_key(hass, result["flow_id"])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_vehicle_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A new key with only vehicles of other entries is refused."""
    result = await _credentials_step(hass)
    result = await _submit_key(hass, result["flow_id"], credentials=NEW_CREDENTIALS)
    assert result["errors"] == {"base": "vehicle_already_configured"}


async def test_no_vehicle_selected(hass: HomeAssistant) -> None:
    """Skipping every vehicle shows an error on the last vehicle form."""
    result = await _credentials_step(hass)
    result = await _submit_key(hass, result["flow_id"], [VEHICLE1, VEHICLE2])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": False, "name": "x"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": False, "name": "x"}
    )
    assert result["step_id"] == "vehicle"
    assert result["errors"] == {"base": "no_vehicle_selected"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": True, "name": "Kona"}
    )
    assert result["step_id"] == "finish"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL}
    )
    assert list(result["result"].data[CONF_VEHICLES]) == [VIN2]


async def test_migrate_checkbox_with_legacy_device(hass: HomeAssistant) -> None:
    """The takeover question appears only for vehicles with a kia_uvo device."""
    _add_legacy_device(hass, VIN)

    result = await _credentials_step(hass)
    result = await _submit_key(hass, result["flow_id"], [VEHICLE1])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": True, "name": "IONIQ 5"}
    )
    assert result["step_id"] == "finish"
    assert "migrate" in _schema_keys(result)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 10, "migrate": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].data[CONF_PENDING_MIGRATION] == [VIN]


async def test_migrate_checkbox_hidden_for_other_vehicle(hass: HomeAssistant) -> None:
    """A kia_uvo device of another vehicle does not show the question."""
    _add_legacy_device(hass, VIN2)

    result = await _credentials_step(hass)
    result = await _submit_key(hass, result["flow_id"], [VEHICLE1])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": True, "name": "IONIQ 5"}
    )
    assert "migrate" not in _schema_keys(result)


async def test_migrate_declined(hass: HomeAssistant) -> None:
    """Without the checkbox ticked nothing is taken over."""
    _add_legacy_device(hass, VIN)

    result = await _credentials_step(hass)
    result = await _submit_key(hass, result["flow_id"], [VEHICLE1])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": True, "name": "IONIQ 5"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 10, "migrate": False}
    )
    assert CONF_PENDING_MIGRATION not in result["result"].data


# ---------------------------------------------------------------- reconfigure


async def _reconfigure(hass: HomeAssistant, entry: MockConfigEntry, step: str) -> FlowResult:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["add_vehicle", "change_key", "rename"]
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": step})


async def test_reconfigure_add_vehicle(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """A new key with an extra vehicle adds it and replaces the key."""
    _add_legacy_device(hass, VIN2)
    result = await _reconfigure(hass, config_entry, "add_vehicle")
    assert result["step_id"] == "add_vehicle"

    result = await _submit_key(
        hass, result["flow_id"], [VEHICLE1, VEHICLE2], credentials=NEW_CREDENTIALS
    )
    assert result["step_id"] == "vehicle"
    assert result["description_placeholders"]["count"] == "1"
    assert result["description_placeholders"]["vin_tail"] == VIN2[-4:]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"include": True, "name": "Kona"}
    )
    assert result["step_id"] == "finish"
    assert "migrate" in _schema_keys(result)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 20, "migrate": True}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.unique_id == f"{BRAND}_new-client-id"
    assert config_entry.data[CONF_CLIENT_ID] == "new-client-id"
    assert config_entry.data[CONF_CLIENT_SECRET] == "new-secret"
    assert list(config_entry.data[CONF_VEHICLES]) == [VIN, VIN2]
    assert config_entry.data[CONF_PENDING_MIGRATION] == [VIN2]
    assert config_entry.title == f"Hyundai {DASH} IONIQ 5, Kona"
    assert config_entry.options[CONF_SCAN_INTERVAL] == 20


async def test_reconfigure_add_vehicle_no_new_vehicles(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A key without unknown vehicles is refused."""
    result = await _reconfigure(hass, config_entry, "add_vehicle")
    result = await _submit_key(hass, result["flow_id"], [VEHICLE1], credentials=NEW_CREDENTIALS)
    assert result["step_id"] == "add_vehicle"
    assert result["errors"] == {"base": "no_new_vehicles"}


async def test_reconfigure_add_vehicle_key_in_use(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The key of another entry cannot be used."""
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{BRAND}_new-client-id",
        data={CONF_BRAND: BRAND, CONF_VEHICLES: {}},
    )
    other.add_to_hass(hass)
    result = await _reconfigure(hass, config_entry, "add_vehicle")
    result = await _submit_key(
        hass, result["flow_id"], [VEHICLE1, VEHICLE2], credentials=NEW_CREDENTIALS
    )
    assert result["errors"] == {"base": "key_in_use"}


async def test_reconfigure_change_key(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """A key of the same account replaces the stored one."""
    result = await _reconfigure(hass, config_entry, "change_key")
    assert result["step_id"] == "change_key"

    result = await _submit_key(hass, result["flow_id"], [VEHICLE1], credentials=NEW_CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_CLIENT_ID] == "new-client-id"
    assert config_entry.data[CONF_CLIENT_SECRET] == "new-secret"
    assert config_entry.unique_id == f"{BRAND}_new-client-id"
    assert list(config_entry.data[CONF_VEHICLES]) == [VIN]


async def test_reconfigure_change_key_wrong_account(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A key without any configured vehicle is refused."""
    result = await _reconfigure(hass, config_entry, "change_key")
    result = await _submit_key(hass, result["flow_id"], [VEHICLE2], credentials=NEW_CREDENTIALS)
    assert result["step_id"] == "change_key"
    assert result["errors"] == {"base": "wrong_account"}
    assert config_entry.data[CONF_CLIENT_ID] == CLIENT_ID

    result = await _submit_key(
        hass, result["flow_id"], error=PleosAuthError(), credentials=NEW_CREDENTIALS
    )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_rename(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Vehicles can be renamed and the interval changed."""
    result = await _reconfigure(hass, config_entry, "rename")
    assert result["step_id"] == "rename"
    label = f"Name …{VIN[-4:]} (IONIQ 5)"
    assert _schema_keys(result) == [label, CONF_SCAN_INTERVAL]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {label: " Blue car ", CONF_SCAN_INTERVAL: 30}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_VEHICLES][VIN][VEHICLE_NAME] == "Blue car"
    assert config_entry.title == f"Hyundai {DASH} Blue car"
    assert config_entry.options[CONF_SCAN_INTERVAL] == 30


async def test_reconfigure_rename_empty_name_kept(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An empty name keeps the old one."""
    result = await _reconfigure(hass, config_entry, "rename")
    label = f"Name …{VIN[-4:]} (IONIQ 5)"
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {label: "", CONF_SCAN_INTERVAL: 10}
    )
    assert config_entry.data[CONF_VEHICLES][VIN][VEHICLE_NAME] == "IONIQ 5"


# --------------------------------------------------------------------- reauth


async def _reauth(hass: HomeAssistant, entry: MockConfigEntry) -> FlowResult:
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    return result


async def test_reauth(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """A renewed key of the same account is stored."""
    assert config_entry.data[CONF_CLIENT_ID] == CLIENT_ID
    result = await _reauth(hass, config_entry)

    result = await _submit_key(hass, result["flow_id"], [VEHICLE1], credentials=NEW_CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_CLIENT_ID] == "new-client-id"
    assert config_entry.data[CONF_CLIENT_SECRET] == "new-secret"
    assert config_entry.unique_id == f"{BRAND}_new-client-id"


async def test_reauth_wrong_account(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """A key of another account is refused."""
    result = await _reauth(hass, config_entry)

    result = await _submit_key(hass, result["flow_id"], [VEHICLE2], credentials=NEW_CREDENTIALS)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "wrong_account"}
    assert config_entry.data[CONF_CLIENT_ID] == CLIENT_ID


async def test_reauth_source_context(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The reauth flow is listed as such."""
    await _reauth(hass, config_entry)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


# -------------------------------------------------------------------- options


async def test_options_flow(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The gear icon renames vehicles and changes the interval."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    label = f"Name …{VIN[-4:]} (IONIQ 5)"
    assert _schema_keys(result) == [label, CONF_SCAN_INTERVAL]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {label: "Daily", CONF_SCAN_INTERVAL: 7}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SCAN_INTERVAL: 7}
    assert config_entry.data[CONF_VEHICLES][VIN][VEHICLE_NAME] == "Daily"
    assert config_entry.title == f"Hyundai {DASH} Daily"
