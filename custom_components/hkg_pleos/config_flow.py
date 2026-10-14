"""Setup dialog: brand, how to get a key, key, cars, take-over of old entities."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import PleosAuthError, PleosClient, PleosConnectionError, PleosError
from .const import (
    BRAND_ACCOUNTS,
    BRAND_NAMES,
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_MIGRATE_VINS,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PLAYGROUND_URL,
)
from .migrate import legacy_vins

_LOGGER = logging.getLogger(__name__)

CONF_SELECTED = "selected"


def _entry_title(brand: str, vehicles: Mapping[str, Mapping[str, Any]]) -> str:
    names = ", ".join(v["name"] for v in vehicles.values())
    return f"{BRAND_NAMES[brand]} – {names}" if names else BRAND_NAMES[brand]


def _vehicle_label(vehicle: Mapping[str, Any]) -> str:
    model = vehicle.get("sellname") or vehicle.get("model") or vehicle.get("name") or ""
    return f"{model} (…{vehicle['vin'][-4:]})".strip()


def _default_name(vehicle: Mapping[str, Any]) -> str:
    return (
        vehicle.get("nickname")
        or vehicle.get("sellname")
        or vehicle.get("name")
        or vehicle["vin"][-4:]
    )


def _credentials_schema(client_id: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CLIENT_ID, default=client_id): TextSelector(),
            vol.Required(CONF_CLIENT_SECRET): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


def _interval_field(default: int) -> dict[Any, Any]:
    return {
        vol.Required(CONF_SCAN_INTERVAL, default=default): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="min",
            )
        )
    }


def _name_fields(labels: Mapping[str, str], names: Mapping[str, str]) -> dict[Any, Any]:
    """One text field per car; the label (model + VIN end) is the field name."""
    return {
        vol.Required(label, default=names[vin]): TextSelector()
        for label, vin in labels.items()
    }


async def _async_fetch_vehicles(
    hass: HomeAssistant, brand: str, client_id: str, client_secret: str
) -> tuple[list[dict[str, Any]], str | None]:
    """Log in and read the cars. Returns (cars, error key)."""
    client = PleosClient(async_get_clientsession(hass), brand, client_id, client_secret)
    try:
        vehicles = await client.async_get_vehicles()
    except PleosAuthError:
        return [], "invalid_auth"
    except PleosConnectionError:
        return [], "cannot_connect"
    except PleosError:
        _LOGGER.exception("Unexpected answer from Pleos")
        return [], "unknown"
    if not vehicles:
        return [], "no_vehicles"
    return vehicles, None


def _placeholders(brand: str) -> dict[str, str]:
    return {
        "brand": BRAND_NAMES[brand],
        "account": BRAND_ACCOUNTS[brand],
        "url": PLAYGROUND_URL,
    }


class PleosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guided setup for people without technical background."""

    VERSION = 1

    def __init__(self) -> None:
        self._brand: str = ""
        self._client_id: str = ""
        self._client_secret: str = ""
        self._found: list[dict[str, Any]] = []
        self._labels: dict[str, str] = {}
        self._vehicles: dict[str, dict[str, Any]] = {}
        self._interval: int = DEFAULT_SCAN_INTERVAL
        self._legacy: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PleosOptionsFlow:
        return PleosOptionsFlow()

    # --- first setup -------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Welcome and brand."""
        if user_input is not None:
            self._brand = user_input[CONF_BRAND]
            return await self.async_step_key_menu()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BRAND): SelectSelector(
                        SelectSelectorConfig(
                            options=list(BRAND_NAMES),
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_BRAND,
                        )
                    )
                }
            ),
        )

    async def async_step_key_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Does the user already have a key?"""
        return self.async_show_menu(
            step_id="key_menu",
            menu_options=["credentials", "guide"],
            description_placeholders=_placeholders(self._brand),
        )

    async def async_step_guide(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step-by-step instructions for getting a key."""
        if user_input is not None:
            return await self.async_step_credentials()
        return self.async_show_form(
            step_id="guide",
            data_schema=vol.Schema({}),
            description_placeholders=_placeholders(self._brand),
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter and check the key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            client_secret = user_input[CONF_CLIENT_SECRET].strip()
            await self.async_set_unique_id(f"{self._brand}_{client_id}")
            self._abort_if_unique_id_configured()
            found, error = await _async_fetch_vehicles(
                self.hass, self._brand, client_id, client_secret
            )
            if error:
                errors["base"] = error
            else:
                self._client_id, self._client_secret = client_id, client_secret
                self._found = found
                return await self.async_step_vehicles()
        return self.async_show_form(
            step_id="credentials",
            data_schema=self.add_suggested_values_to_schema(
                _credentials_schema(), user_input or {}
            ),
            errors=errors,
            description_placeholders=_placeholders(self._brand),
        )

    def _prepare_labels(self, vehicles: list[dict[str, Any]]) -> None:
        self._labels = {}
        for vehicle in vehicles:
            label = _vehicle_label(vehicle)
            while label in self._labels:
                label += " "
            self._labels[label] = vehicle["vin"]

    def _vehicle_record(self, vin: str, name: str) -> dict[str, Any]:
        found = next(v for v in self._found if v["vin"] == vin)
        return {
            "name": name.strip() or _default_name(found),
            "model": found.get("sellname") or found.get("name") or "",
            "model_code": found.get("name") or "",
            "type": found.get("type") or "",
        }

    async def async_step_vehicles(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick cars, name them, choose the interval."""
        if not self._labels:
            self._prepare_labels(self._found)
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = user_input.get(CONF_SELECTED) or []
            if not selected:
                errors["base"] = "no_selection"
            else:
                by_vin = {vin: label for label, vin in self._labels.items()}
                self._vehicles = {
                    vin: self._vehicle_record(vin, user_input[by_vin[vin]])
                    for vin in selected
                }
                self._interval = int(user_input[CONF_SCAN_INTERVAL])
                self._legacy = legacy_vins(self.hass, self._vehicles)
                if self._legacy:
                    return await self.async_step_migrate()
                return self._async_create(migrate=False)

        names = {v["vin"]: _default_name(v) for v in self._found}
        schema = {
            vol.Required(CONF_SELECTED, default=list(names)): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=vin, label=label)
                        for label, vin in self._labels.items()
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            **_name_fields(self._labels, names),
            **_interval_field(DEFAULT_SCAN_INTERVAL),
        }
        return self.async_show_form(
            step_id="vehicles",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input or {}
            ),
            errors=errors,
            description_placeholders={"count": str(len(self._found))},
        )

    async def async_step_migrate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to take over the entity ids of Hyundai / Kia Connect."""
        names = ", ".join(self._vehicles[vin]["name"] for vin in self._legacy)
        return self.async_show_menu(
            step_id="migrate",
            menu_options=["migrate_yes", "migrate_no"],
            description_placeholders={"names": names},
        )

    async def async_step_migrate_yes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self._async_create(migrate=True)

    async def async_step_migrate_no(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self._async_create(migrate=False)

    def _async_create(self, *, migrate: bool) -> ConfigFlowResult:
        if self.source == "reconfigure":
            return self._async_save_added(migrate=migrate)
        data: dict[str, Any] = {
            CONF_BRAND: self._brand,
            CONF_CLIENT_ID: self._client_id,
            CONF_CLIENT_SECRET: self._client_secret,
            CONF_VEHICLES: self._vehicles,
        }
        if migrate:
            data[CONF_MIGRATE_VINS] = self._legacy
        return self.async_create_entry(
            title=_entry_title(self._brand, self._vehicles),
            data=data,
            options={CONF_SCAN_INTERVAL: self._interval},
        )

    # --- key expired or revoked -------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._brand = entry_data[CONF_BRAND]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter a new key for the same cars."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_check_new_key(entry, user_input, errors)
            if result is not None:
                return result
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(entry.data[CONF_CLIENT_ID]),
            errors=errors,
            description_placeholders={
                **_placeholders(self._brand),
                "title": entry.title,
            },
        )

    async def _async_check_new_key(
        self, entry: ConfigEntry, user_input: dict[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        client_id = user_input[CONF_CLIENT_ID].strip()
        client_secret = user_input[CONF_CLIENT_SECRET].strip()
        unique_id = f"{self._brand}_{client_id}"
        other = self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, unique_id
        )
        if other is not None and other.entry_id != entry.entry_id:
            return self.async_abort(reason="already_configured")
        found, error = await _async_fetch_vehicles(
            self.hass, self._brand, client_id, client_secret
        )
        if error:
            errors["base"] = error
            return None
        if not set(entry.data[CONF_VEHICLES]) & {v["vin"] for v in found}:
            errors["base"] = "other_vehicles"
            return None
        return self.async_update_reload_and_abort(
            entry,
            unique_id=unique_id,
            data_updates={CONF_CLIENT_ID: client_id, CONF_CLIENT_SECRET: client_secret},
        )

    # --- reconfigure: add a car, change key, rename -----------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        self._brand = entry.data[CONF_BRAND]
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["add_vehicle", "change_key", "rename"],
            description_placeholders={"title": entry.title},
        )

    async def async_step_add_vehicle(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Instructions: add the car in the app, then get a new key."""
        if user_input is not None:
            return await self.async_step_add_credentials()
        return self.async_show_form(
            step_id="add_vehicle",
            data_schema=vol.Schema({}),
            description_placeholders=_placeholders(self._brand),
        )

    async def async_step_add_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            client_secret = user_input[CONF_CLIENT_SECRET].strip()
            other = self.hass.config_entries.async_entry_for_domain_unique_id(
                DOMAIN, f"{self._brand}_{client_id}"
            )
            found, error = await _async_fetch_vehicles(
                self.hass, self._brand, client_id, client_secret
            )
            new = [v for v in found if v["vin"] not in entry.data[CONF_VEHICLES]]
            if other is not None and other.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")
            if error:
                errors["base"] = error
            elif not new:
                errors["base"] = "no_new_vehicles"
            else:
                self._client_id, self._client_secret = client_id, client_secret
                self._found = new
                return await self.async_step_vehicles()
        return self.async_show_form(
            step_id="add_credentials",
            data_schema=_credentials_schema(),
            errors=errors,
            description_placeholders=_placeholders(self._brand),
        )

    def _async_save_added(self, *, migrate: bool) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        vehicles = {**entry.data[CONF_VEHICLES], **self._vehicles}
        data = {
            **entry.data,
            CONF_CLIENT_ID: self._client_id,
            CONF_CLIENT_SECRET: self._client_secret,
            CONF_VEHICLES: vehicles,
        }
        if migrate:
            data[CONF_MIGRATE_VINS] = self._legacy
        return self.async_update_reload_and_abort(
            entry,
            unique_id=f"{self._brand}_{self._client_id}",
            title=_entry_title(self._brand, vehicles),
            data=data,
            options={**entry.options, CONF_SCAN_INTERVAL: self._interval},
            reason="vehicle_added",
        )

    async def async_step_change_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """New key for the same cars (e.g. after revoking the old one)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_check_new_key(entry, user_input, errors)
            if result is not None:
                return result
        return self.async_show_form(
            step_id="change_key",
            data_schema=_credentials_schema(entry.data[CONF_CLIENT_ID]),
            errors=errors,
            description_placeholders=_placeholders(self._brand),
        )

    async def async_step_rename(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        labels = _labels_for_entry(entry)
        if user_input is not None:
            vehicles, options = _apply_names(entry, labels, user_input)
            return self.async_update_reload_and_abort(
                entry,
                title=_entry_title(self._brand, vehicles),
                data={**entry.data, CONF_VEHICLES: vehicles},
                options=options,
                reason="reconfigure_successful",
            )
        return self.async_show_form(
            step_id="rename", data_schema=_rename_schema(entry, labels)
        )


def _labels_for_entry(entry: ConfigEntry) -> dict[str, str]:
    labels: dict[str, str] = {}
    for vin, vehicle in entry.data[CONF_VEHICLES].items():
        label = _vehicle_label({"vin": vin, "sellname": vehicle.get("model")})
        while label in labels:
            label += " "
        labels[label] = vin
    return labels


def _rename_schema(entry: ConfigEntry, labels: dict[str, str]) -> vol.Schema:
    names = {vin: v["name"] for vin, v in entry.data[CONF_VEHICLES].items()}
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    return vol.Schema({**_name_fields(labels, names), **_interval_field(interval)})


def _apply_names(
    entry: ConfigEntry, labels: dict[str, str], user_input: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    vehicles = {vin: dict(v) for vin, v in entry.data[CONF_VEHICLES].items()}
    for label, vin in labels.items():
        if name := str(user_input.get(label, "")).strip():
            vehicles[vin]["name"] = name
    options = {
        **entry.options,
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
    }
    return vehicles, options


class PleosOptionsFlow(OptionsFlow):
    """Gear icon: names and polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        labels = _labels_for_entry(entry)
        if user_input is not None:
            vehicles, options = _apply_names(entry, labels, user_input)
            self.hass.config_entries.async_update_entry(
                entry,
                title=_entry_title(entry.data[CONF_BRAND], vehicles),
                data={**entry.data, CONF_VEHICLES: vehicles},
            )
            return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="init", data_schema=_rename_schema(entry, labels)
        )
