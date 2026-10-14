"""Config flow for Hyundai Kia Genesis (Pleos) - EU."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import (
    PleosAuthError,
    PleosClient,
    PleosConnectionError,
    PleosRegionError,
    vehicle_display_name,
    vehicle_model,
)
from .const import (
    BRAND_ACCOUNTS,
    BRANDS,
    CONF_BRAND,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PENDING_MIGRATION,
    CONF_SCAN_INTERVAL,
    CONF_VEHICLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PLAYGROUND_URL,
    VEHICLE_MODEL,
    VEHICLE_NAME,
    VEHICLE_TYPE,
)
from .migrate import legacy_device_vins

_LOGGER = logging.getLogger(__name__)

CONF_INCLUDE = "include"
CONF_NAME = "name"
CONF_MIGRATE = "migrate"

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): TextSelector(),
        vol.Required(CONF_CLIENT_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

SCAN_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_SCAN_INTERVAL,
        max=MAX_SCAN_INTERVAL,
        step=1,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="min",
    )
)


def entry_title(brand: str, vehicles: Mapping[str, Mapping[str, Any]]) -> str:
    """Title of a config entry: "<Brand> - <name1>, <name2>" (with an en dash)."""
    names = ", ".join(v.get(VEHICLE_NAME) or vin[-4:] for vin, v in vehicles.items())
    return f"{BRANDS.get(brand, brand)} \N{EN DASH} {names}"


def _placeholders(brand: str) -> dict[str, str]:
    return {
        "brand": BRANDS.get(brand, brand),
        "account": BRAND_ACCOUNTS.get(brand, ""),
        "url": PLAYGROUND_URL,
    }


def _vehicle_label(vin: str, vehicle: Mapping[str, Any]) -> str:
    """Field label of a vehicle in the rename form (shown as is)."""
    model = vehicle.get(VEHICLE_MODEL)
    label = f"Name …{vin[-4:]}"
    return f"{label} ({model})" if model else label


def _names_schema(entry: ConfigEntry) -> tuple[vol.Schema, dict[str, str]]:
    """Form with one name field per vehicle plus the interval.

    Returns the schema and a mapping field label -> VIN.
    """
    fields: dict[Any, Any] = {}
    labels: dict[str, str] = {}
    for vin, vehicle in entry.data.get(CONF_VEHICLES, {}).items():
        label = _vehicle_label(vin, vehicle)
        labels[label] = vin
        fields[vol.Required(label, default=vehicle.get(VEHICLE_NAME) or "")] = TextSelector()
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    fields[vol.Required(CONF_SCAN_INTERVAL, default=interval)] = SCAN_INTERVAL_SELECTOR
    return vol.Schema(fields), labels


def _apply_names(
    entry: ConfigEntry, labels: Mapping[str, str], user_input: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """New entry data (names) and options (interval) from the rename form."""
    vehicles = {vin: dict(v) for vin, v in entry.data.get(CONF_VEHICLES, {}).items()}
    for label, vin in labels.items():
        name = str(user_input.get(label, "")).strip()
        if name and vin in vehicles:
            vehicles[vin][VEHICLE_NAME] = name
    data = {**entry.data, CONF_VEHICLES: vehicles}
    options = {
        **entry.options,
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
    }
    return data, options


def _legacy_vins(hass: HomeAssistant, vins: list[str]) -> list[str]:
    """VINs with a "Hyundai / Kia Connect" device whose entities can be taken over."""
    found = legacy_device_vins(hass, vins)
    return [vin for vin in vins if vin in found]


class PleosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one Pleos API key (one brand, one or more cars)."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._brand: str | None = None
        self._client_id = ""
        self._client_secret = ""
        self._found: list[dict[str, Any]] = []
        self._index = 0
        self._selected: dict[str, dict[str, Any]] = {}
        self._adding = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PleosOptionsFlow:
        """Options flow (gear icon)."""
        return PleosOptionsFlow()

    # ------------------------------------------------------------------ helpers

    @property
    def _ph(self) -> dict[str, str]:
        return _placeholders(self._brand or "")

    async def _async_check_key(
        self, user_input: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Log in with the key and fetch its vehicles. Returns (vehicles, errors)."""
        assert self._brand is not None
        self._client_id = str(user_input[CONF_CLIENT_ID]).strip()
        self._client_secret = str(user_input[CONF_CLIENT_SECRET]).strip()
        client = PleosClient(
            async_get_clientsession(self.hass),
            self._brand,
            self._client_id,
            self._client_secret,
        )
        try:
            await client.async_login()
            vehicles = await client.async_get_vehicles()
        except PleosRegionError:
            return [], {"base": "region_unsupported"}
        except PleosAuthError:
            return [], {"base": "invalid_auth"}
        except PleosConnectionError:
            return [], {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error while checking the Pleos key")
            return [], {"base": "unknown"}
        if not vehicles:
            return [], {"base": "no_vehicles"}
        return vehicles, {}

    def _key_in_use(self, current: ConfigEntry | None) -> bool:
        """True when another entry already uses this brand + client ID."""
        unique_id = f"{self._brand}_{self._client_id}"
        return any(
            entry.unique_id == unique_id
            for entry in self._async_current_entries(include_ignore=False)
            if current is None or entry.entry_id != current.entry_id
        )

    def _vins_elsewhere(self, current: ConfigEntry | None) -> set[str]:
        """VINs configured in other entries of the same brand."""
        vins: set[str] = set()
        for entry in self._async_current_entries(include_ignore=False):
            if current is not None and entry.entry_id == current.entry_id:
                continue
            if entry.data.get(CONF_BRAND) == self._brand:
                vins.update(entry.data.get(CONF_VEHICLES, {}))
        return vins

    def _credentials_data(self) -> dict[str, Any]:
        return {
            CONF_CLIENT_ID: self._client_id,
            CONF_CLIENT_SECRET: self._client_secret,
        }

    # --------------------------------------------------------------- user flow

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Welcome text and brand selection."""
        if user_input is not None:
            self._brand = user_input[CONF_BRAND]
            return await self.async_step_key_menu()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BRAND): SelectSelector(
                        SelectSelectorConfig(
                            options=list(BRANDS),
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_BRAND,
                        )
                    )
                }
            ),
            last_step=False,
        )

    async def async_step_key_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether the user already has an API key."""
        return self.async_show_menu(
            step_id="key_menu",
            menu_options=["credentials", "guide"],
            description_placeholders=self._ph,
        )

    async def async_step_guide(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step-by-step guide to get an API key."""
        if user_input is not None:
            return await self.async_step_credentials()
        return self.async_show_form(
            step_id="guide",
            data_schema=vol.Schema({}),
            description_placeholders=self._ph,
            last_step=False,
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter client ID and secret; check them and fetch the cars."""
        errors: dict[str, str] = {}
        if user_input is not None:
            vehicles, errors = await self._async_check_key(user_input)
            if not errors:
                await self.async_set_unique_id(f"{self._brand}_{self._client_id}")
                self._abort_if_unique_id_configured()
                taken = self._vins_elsewhere(None)
                vehicles = [v for v in vehicles if v["vin"] not in taken]
                if not vehicles:
                    errors["base"] = "vehicle_already_configured"
                else:
                    self._start_vehicles(vehicles, adding=False)
                    return await self.async_step_vehicle()

        return self.async_show_form(
            step_id="credentials",
            data_schema=self.add_suggested_values_to_schema(CREDENTIALS_SCHEMA, user_input),
            errors=errors,
            description_placeholders=self._ph,
            last_step=False,
        )

    def _start_vehicles(self, vehicles: list[dict[str, Any]], *, adding: bool) -> None:
        self._found = vehicles
        self._index = 0
        self._selected = {}
        self._adding = adding

    async def async_step_vehicle(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask once per found car: include it, and under which name."""
        errors: dict[str, str] = {}
        vehicle = self._found[self._index]
        vin: str = vehicle["vin"]
        default_name = vehicle_display_name(vehicle)

        if user_input is not None:
            if user_input.get(CONF_INCLUDE, True):
                name = str(user_input.get(CONF_NAME, "")).strip() or default_name
                self._selected[vin] = {
                    VEHICLE_NAME: name,
                    VEHICLE_MODEL: vehicle_model(vehicle),
                    VEHICLE_TYPE: vehicle.get("type"),
                }
            else:
                self._selected.pop(vin, None)

            if self._index + 1 < len(self._found):
                self._index += 1
                return await self.async_step_vehicle()
            if self._selected:
                return await self.async_step_finish()
            errors["base"] = "no_vehicle_selected"

        schema = vol.Schema(
            {
                vol.Required(CONF_INCLUDE, default=True): BooleanSelector(),
                vol.Required(CONF_NAME, default=default_name): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="vehicle",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders={
                **self._ph,
                "model": vehicle_model(vehicle) or default_name,
                "vin_tail": vin[-4:],
                "index": str(self._index + 1),
                "count": str(len(self._found)),
            },
            last_step=False,
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Interval and (if old kia_uvo devices exist) the takeover question."""
        legacy = _legacy_vins(self.hass, list(self._selected))
        entry = self._get_reconfigure_entry() if self._adding else None

        if user_input is not None:
            interval = int(user_input[CONF_SCAN_INTERVAL])
            pending = legacy if legacy and user_input.get(CONF_MIGRATE) else []
            if entry is None:
                assert self._brand is not None
                data: dict[str, Any] = {
                    CONF_BRAND: self._brand,
                    **self._credentials_data(),
                    CONF_VEHICLES: self._selected,
                }
                if pending:
                    data[CONF_PENDING_MIGRATION] = pending
                return self.async_create_entry(
                    title=entry_title(self._brand, self._selected),
                    data=data,
                    options={CONF_SCAN_INTERVAL: interval},
                )

            vehicles = {**entry.data.get(CONF_VEHICLES, {}), **self._selected}
            new_data = {
                **entry.data,
                **self._credentials_data(),
                CONF_VEHICLES: vehicles,
            }
            new_data.pop(CONF_PENDING_MIGRATION, None)
            if pending:
                new_data[CONF_PENDING_MIGRATION] = pending
            return self.async_update_reload_and_abort(
                entry,
                unique_id=f"{self._brand}_{self._client_id}",
                title=entry_title(entry.data[CONF_BRAND], vehicles),
                data=new_data,
                options={**entry.options, CONF_SCAN_INTERVAL: interval},
            )

        interval_default = (
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if entry is not None
            else DEFAULT_SCAN_INTERVAL
        )
        fields: dict[Any, Any] = {
            vol.Required(CONF_SCAN_INTERVAL, default=interval_default): SCAN_INTERVAL_SELECTOR
        }
        if legacy:
            fields[vol.Required(CONF_MIGRATE, default=False)] = BooleanSelector()
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema(fields),
            description_placeholders=self._ph,
        )

    # ------------------------------------------------------------- reconfigure

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu: add a car, change the key, rename / interval."""
        self._brand = self._get_reconfigure_entry().data[CONF_BRAND]
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["add_vehicle", "change_key", "rename"],
            description_placeholders=self._ph,
        )

    async def async_step_add_vehicle(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """New key that contains an additional car."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            vehicles, errors = await self._async_check_key(user_input)
            if not errors and self._key_in_use(entry):
                errors["base"] = "key_in_use"
            if not errors:
                known = set(entry.data.get(CONF_VEHICLES, {})) | self._vins_elsewhere(entry)
                new = [v for v in vehicles if v["vin"] not in known]
                if not new:
                    errors["base"] = "no_new_vehicles"
                else:
                    self._start_vehicles(new, adding=True)
                    return await self.async_step_vehicle()

        return self.async_show_form(
            step_id="add_vehicle",
            data_schema=self.add_suggested_values_to_schema(CREDENTIALS_SCHEMA, user_input),
            errors=errors,
            description_placeholders=self._ph,
            last_step=False,
        )

    async def _async_replace_key(
        self, entry: ConfigEntry, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Shared by change_key and reauth_confirm."""
        errors: dict[str, str] = {}
        if user_input is not None:
            vehicles, errors = await self._async_check_key(user_input)
            if not errors and self._key_in_use(entry):
                errors["base"] = "key_in_use"
            if not errors:
                configured = set(entry.data.get(CONF_VEHICLES, {}))
                if not configured & {v["vin"] for v in vehicles}:
                    errors["base"] = "wrong_account"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=f"{self._brand}_{self._client_id}",
                        data_updates=self._credentials_data(),
                    )

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(CREDENTIALS_SCHEMA, user_input),
            errors=errors,
            description_placeholders=self._ph,
        )

    async def async_step_change_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace client ID and secret."""
        return await self._async_replace_key(
            self._get_reconfigure_entry(), "change_key", user_input
        )

    async def async_step_rename(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Rename cars and change the interval."""
        entry = self._get_reconfigure_entry()
        schema, labels = _names_schema(entry)
        if user_input is not None:
            data, options = _apply_names(entry, labels, user_input)
            return self.async_update_reload_and_abort(
                entry,
                title=entry_title(entry.data[CONF_BRAND], data[CONF_VEHICLES]),
                data=data,
                options=options,
            )
        return self.async_show_form(
            step_id="rename", data_schema=schema, description_placeholders=self._ph
        )

    # ------------------------------------------------------------------ reauth

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The stored key is no longer accepted."""
        self._brand = entry_data[CONF_BRAND]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter a renewed key."""
        return await self._async_replace_key(self._get_reauth_entry(), "reauth_confirm", user_input)


class PleosOptionsFlow(OptionsFlow):
    """Gear icon: car names and interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Rename cars and change the interval."""
        entry = self.config_entry
        schema, labels = _names_schema(entry)
        if user_input is not None:
            data, options = _apply_names(entry, labels, user_input)
            self.hass.config_entries.async_update_entry(
                entry,
                title=entry_title(entry.data[CONF_BRAND], data[CONF_VEHICLES]),
                data=data,
                options=options,
            )
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders=_placeholders(entry.data.get(CONF_BRAND, "")),
        )
