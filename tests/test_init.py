"""Tests for setting up and unloading a Pleos config entry."""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hkg_pleos.const import DOMAIN

from .conftest import (
    TOKEN_URL,
    VIN,
    endpoint_url,
    register_pleos,
    sequence,
    setup_entry,
)

EXPIRED = {"error": {"code": "40003", "message": "Token expired"}}
NOT_IN_KEY = {"error": {"code": "4101", "message": "Unregistered vehicle"}}
RANGE_ENTITY = "sensor.ioniq_5_ev_range"


def _calls(aioclient_mock: AiohttpClientMocker, url: str) -> int:
    return sum(1 for call in aioclient_mock.mock_calls if str(call[1]) == url)


def _reauth_flows(hass: HomeAssistant, entry: MockConfigEntry) -> list[Any]:
    return list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))


async def _refresh(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_setup_and_unload(
    hass: HomeAssistant, mock_pleos: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """The entry loads one coordinator per vehicle and unloads cleanly."""
    assert await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert list(config_entry.runtime_data.coordinators) == [VIN]
    assert hass.states.get(RANGE_ENTITY).state == "106"
    # One login for the vehicle list and all snapshot endpoints.
    assert _calls(mock_pleos, TOKEN_URL) == 1

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(RANGE_ENTITY).state == STATE_UNAVAILABLE


async def test_setup_auth_failed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A rejected key starts reauth and raises a repair issue."""
    aioclient_mock.post(
        TOKEN_URL,
        status=HTTPStatus.UNAUTHORIZED,
        json={"error": {"code": "40001", "message": "Invalid client"}},
    )

    assert not await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass, config_entry)) == 1
    issue = issue_registry.async_get_issue(DOMAIN, f"auth_failed_{config_entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "auth_failed"
    assert issue.translation_placeholders["brand"] == "Hyundai"
    assert not issue.is_fixable


async def test_setup_auth_issue_cleared(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A working key removes an earlier auth issue."""
    issue_id = f"auth_failed_{config_entry.entry_id}"
    ir.async_create_issue(
        hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.ERROR,
        translation_key="auth_failed",
    )  # fmt: skip

    assert await setup_entry(hass, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_setup_not_reachable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """A server error retries the setup later."""
    aioclient_mock.post(TOKEN_URL, status=HTTPStatus.SERVICE_UNAVAILABLE)

    assert not await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not _reauth_flows(hass, config_entry)


async def test_vehicle_removed_from_key(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A vehicle missing from the key gets an issue and no coordinator."""
    consent_payload["data"]["vehicles"][0]["vin"] = "KMHOTHER000000009"
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)

    assert await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data.coordinators == {}
    assert hass.states.get(RANGE_ENTITY) is None
    assert _calls(aioclient_mock, endpoint_url("status")) == 0

    issue = issue_registry.async_get_issue(DOMAIN, f"vehicle_removed_{config_entry.entry_id}_{VIN}")
    assert issue is not None
    assert issue.is_fixable
    assert issue.data == {"entry_id": config_entry.entry_id, "vin": VIN}
    assert issue.translation_placeholders == {"name": "IONIQ 5", "vin_tail": VIN[-4:]}


async def test_token_expired_during_refresh(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    token_payload: dict[str, Any],
    consent_payload: dict[str, Any],
    vehicle_payloads: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An expired token (40003) on a poll logs in again and keeps the data."""
    register_pleos(aioclient_mock, token_payload, consent_payload, vehicle_payloads)
    assert await setup_entry(hass, config_entry)
    assert _calls(aioclient_mock, TOKEN_URL) == 1

    new_range = {"data": {"distanceToEmpties": [{"type": "EV", "value": "99", "unit": "km"}]}}
    aioclient_mock.clear_requests()
    aioclient_mock.post(TOKEN_URL, json={"data": {"accessToken": "fresh-token"}})
    for endpoint, payload in vehicle_payloads.items():
        if endpoint != "powertrains":
            aioclient_mock.get(endpoint_url(endpoint), json=payload)
    url = endpoint_url("powertrains")
    aioclient_mock.get(
        url,
        side_effect=sequence("GET", url, (HTTPStatus.UNAUTHORIZED, EXPIRED), (200, new_range)),
    )

    await _refresh(hass, freezer)

    coordinator = config_entry.runtime_data.coordinators[VIN]
    assert coordinator.last_update_success
    assert _calls(aioclient_mock, TOKEN_URL) == 1
    assert _calls(aioclient_mock, endpoint_url("powertrains")) == 2
    assert coordinator.client._token == "fresh-token"
    assert hass.states.get(RANGE_ENTITY).state == "99"
    assert not _reauth_flows(hass, config_entry)


async def test_key_revoked_during_refresh(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    token_payload: dict[str, Any],
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A key that is no longer accepted on a poll starts reauth."""
    assert await setup_entry(hass, config_entry)

    mock_pleos.clear_requests()
    mock_pleos.post(TOKEN_URL, status=HTTPStatus.UNAUTHORIZED, json=EXPIRED)
    for endpoint in ("batteries", "powertrains", "locations", "driving", "status"):
        mock_pleos.get(endpoint_url(endpoint), status=HTTPStatus.UNAUTHORIZED, json=EXPIRED)

    await _refresh(hass, freezer)
    assert hass.states.get(RANGE_ENTITY).state == STATE_UNAVAILABLE
    assert len(_reauth_flows(hass, config_entry)) == 1


async def test_vehicle_removed_during_refresh(
    hass: HomeAssistant,
    mock_pleos: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    issue_registry: ir.IssueRegistry,
) -> None:
    """4101 on a poll raises the fixable issue; data back clears it."""
    assert await setup_entry(hass, config_entry)
    issue_id = f"vehicle_removed_{config_entry.entry_id}_{VIN}"

    mock_pleos.clear_requests()
    mock_pleos.post(TOKEN_URL, json={"data": {"accessToken": "t"}})
    for endpoint in ("batteries", "powertrains", "locations", "driving", "status"):
        mock_pleos.get(endpoint_url(endpoint), status=HTTPStatus.NOT_FOUND, json=NOT_IN_KEY)

    await _refresh(hass, freezer)
    assert hass.states.get(RANGE_ENTITY).state == STATE_UNAVAILABLE
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None


async def test_remove_entry_deletes_issues(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Removing the entry removes its repair issues."""
    aioclient_mock.post(TOKEN_URL, status=HTTPStatus.UNAUTHORIZED, json=EXPIRED)
    await setup_entry(hass, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, f"auth_failed_{config_entry.entry_id}")

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert not [issue for (domain, _), issue in issue_registry.issues.items() if domain == DOMAIN]
