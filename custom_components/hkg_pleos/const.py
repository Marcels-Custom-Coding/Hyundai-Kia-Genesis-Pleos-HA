"""Constants for the Hyundai Kia Genesis (Pleos) integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "hkg_pleos"
LEGACY_DOMAIN: Final = "kia_uvo"

API_HOST: Final = "https://api.pleos.ai"
PLAYGROUND_URL: Final = "https://pleos.ai/playground"
DOCS_URL: Final = "https://github.com/Marcels-Custom-Coding/Hyundai-Kia-Genesis-Pleos-HA"

BRAND_HYUNDAI: Final = "hyundai"
BRAND_KIA: Final = "kia"
BRAND_GENESIS: Final = "genesis"

BRANDS: Final = {
    BRAND_HYUNDAI: "Hyundai",
    BRAND_KIA: "Kia",
    BRAND_GENESIS: "Genesis",
}

# Name of the brand's own app/account the key is issued with.
BRAND_ACCOUNTS: Final = {
    BRAND_HYUNDAI: "Bluelink",
    BRAND_KIA: "Kia Connect",
    BRAND_GENESIS: "Genesis Connected Services",
}

CONF_BRAND: Final = "brand"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_VEHICLES: Final = "vehicles"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_PENDING_MIGRATION: Final = "pending_migration"

# Keys inside each entry of CONF_VEHICLES (keyed by VIN).
VEHICLE_NAME: Final = "name"
VEHICLE_MODEL: Final = "model"
VEHICLE_TYPE: Final = "type"

DEFAULT_SCAN_INTERVAL: Final = 10  # minutes
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 1440

# Vehicle types reported by /v1/vehicles/consent.
TYPE_ICE: Final = "GN"
TYPE_EV: Final = "EV"
TYPE_HEV: Final = "HV"
TYPE_PHEV: Final = "PE"
TYPE_FCEV: Final = "FV"
TYPES_WITHOUT_FUEL: Final = (TYPE_EV, TYPE_FCEV)

# Snapshot endpoints polled per vehicle: /v1/vehicles/{vin}/<endpoint>
ENDPOINTS: Final = ("batteries", "powertrains", "locations", "driving", "status")

UPDATE_INTERVAL_DEFAULT: Final = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

ISSUE_AUTH_FAILED: Final = "auth_failed"
ISSUE_VEHICLE_REMOVED: Final = "vehicle_removed"
