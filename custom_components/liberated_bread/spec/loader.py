"""YAML spec loader for bundled Liberated Bread device specs."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .models import DeviceSpec

_LOGGER = logging.getLogger(__name__)

SPEC_DIR = Path(__file__).resolve().parents[1] / "device_specs"


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

    Scans wifi/ first, then ble/, then flat-root.  First-write-wins so WiFi
    devices get priority when a name collision occurs.
    """
    specs: dict[str, DeviceSpec] = {}
    if not spec_dir.exists():
        _LOGGER.warning("Device specs directory does not exist: %s", spec_dir)
        return specs

    for subdir in ("wifi", "ble"):
        subdir_path = spec_dir / subdir
        if not subdir_path.is_dir():
            continue
        for path in sorted(subdir_path.glob("*.yaml")):
            spec = _load_one_spec(path)
            if spec is None:
                continue
            name = spec.device.name
            # Check protocol-vs-directory consistency.
            expected_proto = subdir  # "wifi" or "ble"
            actual_proto = spec.device.protocol.value
            if expected_proto != actual_proto:
                _LOGGER.warning(
                    "Spec %s declares protocol '%s' but lives in %s/ — "
                    "may be misfiled",
                    path.name,
                    actual_proto,
                    subdir,
                )
            # First-write-wins (WiFi scanned first = WiFi priority).
            if name in specs:
                _LOGGER.debug(
                    "Spec %s already loaded (from earlier pass); skipping %s",
                    name,
                    path,
                )
                continue
            specs[name] = spec

    # Flat-root fallback: legacy layout with *.yaml at device_specs/ root.
    for path in sorted(spec_dir.glob("*.yaml")):
        spec = _load_one_spec(path)
        if spec is None:
            continue
        name = spec.device.name
        _LOGGER.warning(
            "Spec %s found in flat root %s — move it to "
            "device_specs/wifi/ or device_specs/ble/",
            path.name,
            path.parent,
        )
        if name in specs:
            _LOGGER.debug("Spec %s already loaded; skipping flat-root copy", name)
            continue
        specs[name] = spec

    return specs


def _load_one_spec(path: Path) -> DeviceSpec | None:
    """Parse one YAML spec file, returning None on any error."""
    try:
        with path.open("r", encoding="utf-8") as file:
            raw = yaml.load(file, Loader=UniqueKeyLoader) or {}
        return DeviceSpec.from_dict(raw)
    except Exception as err:  # noqa: BLE001 - malformed specs should not break HA.
        _LOGGER.warning("Skipping malformed device spec %s: %s", path.name, err)
        return None
