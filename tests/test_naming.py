"""Entity names: complete translations and the same names as kia_uvo.

The reference in fixtures/kia_uvo_reference.json is a pinned copy of the
names and translation keys of the "Hyundai / Kia Connect" (kia_uvo)
integration, so taken-over entities keep their names. No network needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.hkg_pleos.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
from custom_components.hkg_pleos.device_tracker import TRACKER_DESCRIPTIONS
from custom_components.hkg_pleos.entity import PleosEntityDescription
from custom_components.hkg_pleos.sensor import SENSOR_DESCRIPTIONS

from .conftest import FIXTURES

TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / "hkg_pleos" / "translations"
LANGUAGES = ("en", "de")
PLATFORMS: dict[str, tuple[PleosEntityDescription, ...]] = {
    "sensor": SENSOR_DESCRIPTIONS,
    "binary_sensor": BINARY_SENSOR_DESCRIPTIONS,
    "device_tracker": TRACKER_DESCRIPTIONS,
}
CASES = [
    pytest.param(platform, description, id=f"{platform}.{description.key}")
    for platform, descriptions in PLATFORMS.items()
    for description in descriptions
]
LEGACY_CASES = [case for case in CASES if case.values[1].legacy_key is not None]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


REFERENCE = _load(FIXTURES / "kia_uvo_reference.json")
OUR_NAMES = {lang: _load(TRANSLATIONS / f"{lang}.json")["entity"] for lang in LANGUAGES}


def _our_name(lang: str, platform: str, description: PleosEntityDescription) -> str | None:
    return OUR_NAMES[lang].get(platform, {}).get(str(description.translation_key), {}).get("name")


def test_keys_unique() -> None:
    """Keys are unique per platform (they form the unique_id)."""
    for descriptions in PLATFORMS.values():
        keys = [description.key for description in descriptions]
        assert len(keys) == len(set(keys))


@pytest.mark.parametrize(("platform", "description"), CASES)
def test_translated(platform: str, description: PleosEntityDescription) -> None:
    """Every entity has an English and a German name."""
    assert description.translation_key, description.key
    for lang in LANGUAGES:
        name = _our_name(lang, platform, description)
        assert isinstance(name, str), f"{lang}: {description.translation_key}"
        assert name.strip(), f"{lang}: {description.translation_key}"


@pytest.mark.parametrize(("platform", "description"), LEGACY_CASES)
def test_legacy_names(platform: str, description: PleosEntityDescription) -> None:
    """Entities with a kia_uvo counterpart keep its translation key and names."""
    reference = REFERENCE[platform]["legacy"].get(description.legacy_key)
    assert reference is not None, f"{description.legacy_key} not in the kia_uvo reference"
    assert reference["translation_key"] == description.translation_key
    for lang in LANGUAGES:
        assert _our_name(lang, platform, description) == reference[lang], lang


@pytest.mark.parametrize(
    ("platform", "description"),
    [case for case in CASES if case.values[1].legacy_key is None],
)
def test_new_entities_do_not_reuse_kia_uvo_keys(
    platform: str, description: PleosEntityDescription
) -> None:
    """Entities without counterpart use translation keys kia_uvo does not have."""
    assert description.translation_key not in REFERENCE[platform]["translation_keys"]


def test_reference_has_only_used_keys() -> None:
    """The pinned reference holds exactly the legacy keys in use."""
    for platform, descriptions in PLATFORMS.items():
        used = {d.legacy_key for d in descriptions if d.legacy_key is not None}
        assert set(REFERENCE[platform]["legacy"]) == used, platform
