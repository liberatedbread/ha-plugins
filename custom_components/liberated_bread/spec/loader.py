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
    """Load bundled YAML specs keyed by device name."""
    specs: dict[str, DeviceSpec] = {}
    if not spec_dir.exists():
        _LOGGER.warning("Device specs directory does not exist: %s", spec_dir)
        return specs

    for path in sorted(spec_dir.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as file:
                raw = yaml.load(file, Loader=UniqueKeyLoader) or {}
            spec = DeviceSpec.from_dict(raw)
        except Exception as err:  # noqa: BLE001 - malformed specs should not break HA.
            _LOGGER.warning("Skipping malformed device spec %s: %s", path.name, err)
            continue
        specs[spec.device.name] = spec
    return specs
