"""YAML spec loader for Liberated Bread device specs.

Loads from the git-subtree'd protocol-specs/devices/ directory (flat layout).
Protocol is read from ``device.protocol`` in each YAML file — unsupported
transports (uart, can, obd2) are skipped silently.  WiFi devices are loaded
before BLE devices so that name-collision priority goes to WiFi.

HA-specific overrides (entity mappings for Wemo variants, BLE identification
drift) are applied from ``ha_overrides.json`` after loading.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from .models import DeviceSpec

_LOGGER = logging.getLogger(__name__)

# Git-subtree'd protocol-specs root — devices live in .../devices/*.yaml.
SPEC_DIR = Path(__file__).resolve().parents[1] / "protocol_specs"

# Protocols that are explicitly unsupported — skip them without a warning.
_UNSUPPORTED_PROTOCOLS = frozenset({"uart", "can", "obd2"})

# Cached HA overrides, populated on first load.
_OVERRIDES: dict | None = None


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _construct_mapping(
    loader: UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict:
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_specs(spec_dir: Path = SPEC_DIR) -> dict[str, DeviceSpec]:
    """Load bundled YAML specs keyed by device name.

    Scans ``protocol_specs/devices/`` (flat directory).  Reads the protocol
    from ``device.protocol`` inside each YAML — unsupported transports
    (uart, can, obd2) are skipped gracefully.  WiFi devices are loaded first
    so they take priority over BLE in the event of a name collision.
    """
    global _OVERRIDES

    specs: dict[str, DeviceSpec] = {}

    devices_dir = spec_dir / "device-specs" / "devices"
    if not devices_dir.is_dir():
        # Backward compat: tests and older layouts use devices/ directly.
        devices_dir = spec_dir / "devices"
    if not devices_dir.is_dir():
        _LOGGER.warning("Device specs directory does not exist: %s", devices_dir)
        return specs

    paths = sorted(devices_dir.glob("*.yaml"))

    # Split by protocol so WiFi is processed first (WiFi-over-BLE priority).
    wifi_paths: list[Path] = []
    ble_paths: list[Path] = []
    skipped: list[str] = []

    for path in paths:
        proto = _read_protocol(path)
        if proto is None:
            continue  # unreadable — logged inside _read_protocol
        if proto in _UNSUPPORTED_PROTOCOLS:
            skipped.append(path.name)
            continue
        if proto == "wifi":
            wifi_paths.append(path)
        elif proto in {"ble", "zigbee", "zwave"}:
            ble_paths.append(path)
        else:
            # Future unknown protocol — still try to load it.
            _LOGGER.debug("Unknown protocol '%s' in %s; loading anyway", proto, path.name)
            ble_paths.append(path)

    if skipped:
        _LOGGER.debug(
            "Skipped %d unsupported-protocol specs: %s",
            len(skipped),
            ", ".join(skipped),
        )

    # Load WiFi first (first-write-wins → WiFi priority on collisions).
    for path in wifi_paths + ble_paths:
        spec = _load_one_spec(path)
        if spec is None:
            continue
        name = spec.device.name
        if name in specs:
            _LOGGER.debug(
                "Spec %s already loaded (WiFi priority); skipping %s",
                name,
                path,
            )
            continue
        specs[name] = spec

    _apply_overrides(specs)
    return specs


def _read_protocol(path: Path) -> str | None:
    """Extract the ``device.protocol`` value from a YAML file without full parse."""
    try:
        with path.open("r", encoding="utf-8") as file:
            raw = yaml.load(file, Loader=UniqueKeyLoader) or {}
        device = raw.get("device")
        if not isinstance(device, dict):
            _LOGGER.warning("Skipping %s: no 'device' mapping found", path.name)
            return None
        return str(device.get("protocol", "")).strip().lower()
    except Exception:  # noqa: BLE001 - malformed specs must not break HA.
        _LOGGER.warning("Skipping unreadable spec %s", path.name, exc_info=True)
        return None


def _load_one_spec(path: Path) -> DeviceSpec | None:
    """Parse one YAML spec file, returning None on any error."""
    try:
        with path.open("r", encoding="utf-8") as file:
            raw = yaml.load(file, Loader=UniqueKeyLoader) or {}
        return DeviceSpec.from_dict(raw)
    except Exception as err:  # noqa: BLE001 - malformed specs should not break HA.
        _LOGGER.warning("Skipping malformed device spec %s: %s", path.name, err)
        return None


# ---------------------------------------------------------------------------
# HA overrides — inject entity mappings and identification drift without
# forking the upstream YAML.
# ---------------------------------------------------------------------------

def _load_overrides() -> dict:
    """Load ``ha_overrides.json``, caching the result."""
    global _OVERRIDES
    if _OVERRIDES is not None:
        return _OVERRIDES

    overrides_path = Path(__file__).resolve().parent.parent / "ha_overrides.json"
    try:
        with overrides_path.open("r", encoding="utf-8") as fh:
            _OVERRIDES = json.load(fh)
    except FileNotFoundError:
        _LOGGER.debug("No ha_overrides.json found at %s", overrides_path)
        _OVERRIDES = {}
    except json.JSONDecodeError:
        _LOGGER.warning("ha_overrides.json is not valid JSON; ignoring overrides")
        _OVERRIDES = {}
    return _OVERRIDES


def _apply_overrides(specs: dict[str, DeviceSpec]) -> None:
    """Merge HA entity/identification overrides into already-loaded specs."""
    overrides = _load_overrides()
    if not overrides:
        return

    for device_name, device_overrides in overrides.items():
        spec = specs.get(device_name)
        if spec is None:
            continue

        # --- Normalize variants from spec extensions into device.variants ---
        if device_overrides.get("normalize_variants_from_extensions"):
            raw_variants = spec.extensions.pop("variants", None)
            if raw_variants is not None:
                spec.device.variants = raw_variants

        # --- Inject per-variant entity blocks ---
        variant_entities = device_overrides.get("variant_entities")
        if variant_entities and spec.device.variants:
            for idx_str, raw_entities in variant_entities.items():
                idx = int(idx_str)
                if 0 <= idx < len(spec.device.variants):
                    from .models import EntityDef
                    spec.device.variants[idx]["entities"] = [
                        EntityDef.from_dict(item) for item in raw_entities
                    ]

        # --- Merge identification overrides (BLE name_prefix drift) ---
        ident_overrides = device_overrides.get("identification")
        if ident_overrides and spec.device.identification is not None:
            for key, value in ident_overrides.items():
                if hasattr(spec.device.identification, key):
                    setattr(spec.device.identification, key, value)
