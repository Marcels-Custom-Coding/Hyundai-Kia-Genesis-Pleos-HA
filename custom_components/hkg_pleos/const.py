"""Constants for Hyundai Kia Genesis (Pleos)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "hkg_pleos"

API_HOST: Final = "https://api.pleos.ai"
PLAYGROUND_URL: Final = "https://pleos.ai/playground"

CONF_BRAND: Final = "brand"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_VEHICLES: Final = "vehicles"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MIGRATE_VINS: Final = "migrate_vins"

DEFAULT_SCAN_INTERVAL: Final = 10  # minutes
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 120

BRAND_HYUNDAI: Final = "hyundai"
BRAND_KIA: Final = "kia"
BRAND_GENESIS: Final = "genesis"

BRAND_NAMES: Final = {
    BRAND_HYUNDAI: "Hyundai",
    BRAND_KIA: "Kia",
    BRAND_GENESIS: "Genesis",
}

# Name of the manufacturer app/account the user signs in with.
BRAND_ACCOUNTS: Final = {
    BRAND_HYUNDAI: "Hyundai Bluelink",
    BRAND_KIA: "Kia Connect",
    BRAND_GENESIS: "Genesis Connected Services",
}

# Integration that the community used before; entity ids are taken over from it.
LEGACY_DOMAIN: Final = "kia_uvo"

ENDPOINTS: Final = ("batteries", "powertrains", "locations", "driving", "status")

ISSUE_AUTH_FAILED: Final = "auth_failed"
ISSUE_VEHICLE_REMOVED: Final = "vehicle_removed"
