"""Tests for YAML spec loading."""

from __future__ import annotations

import pytest
import yaml

from custom_components.liberated_bread.spec.loader import (
    UniqueKeyLoader,
    load_specs,
)

VALID_SPEC_BLE = """
device:
  name: Test Device
  manufacturer: Test Maker
  manufacturer_status: active
  protocol: ble
entities:
  - platform: sensor
    name: Value
"""

VALID_SPEC_WIFI = """
device:
  name: Test Device
  manufacturer: Test Maker
  manufacturer_status: active
  protocol: wifi
entities:
  - platform: switch
    name: Power
"""

UART_SPEC = """
device:
  name: Motor Controller
  manufacturer: Test Maker
  manufacturer_status: active
  protocol: uart
"""


def test_load_specs_empty_or_missing_directory(tmp_path) -> None:
    assert load_specs(tmp_path / "missing") == {}
    # Directory exists but has no 'devices' subdirectory.
    assert load_specs(tmp_path) == {}


def test_load_specs_valid_yaml_files(tmp_path) -> None:
    devices_dir = tmp_path / "devices"
    devices_dir.mkdir(parents=True)
    (devices_dir / "test.yaml").write_text(VALID_SPEC_BLE, encoding="utf-8")

    specs = load_specs(tmp_path)

    assert list(specs) == ["Test Device"]
    assert specs["Test Device"].entities[0].name == "Value"


def test_unique_key_loader_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate YAML key"):
        yaml.load("a: 1\na: 2\n", Loader=UniqueKeyLoader)


def test_unsupported_protocols_skipped_silently(tmp_path, caplog) -> None:
    """uart, can, obd2 protocols should be skipped without a warning."""
    devices_dir = tmp_path / "devices"
    devices_dir.mkdir(parents=True)
    (devices_dir / "motor.yaml").write_text(UART_SPEC, encoding="utf-8")

    specs = load_specs(tmp_path)
    assert specs == {}
    # Must not contain "malformed" for unsupported protocols.
    assert "malformed" not in caplog.text.lower()


def test_wifi_priority_over_ble_on_name_collision(tmp_path) -> None:
    """When WiFi and BLE specs share a name, WiFi wins."""
    devices_dir = tmp_path / "devices"
    devices_dir.mkdir(parents=True)

    # BLE spec alphabetically first, but WiFi should win.
    (devices_dir / "a_ble_spec.yaml").write_text(VALID_SPEC_BLE, encoding="utf-8")
    (devices_dir / "z_wifi_spec.yaml").write_text(VALID_SPEC_WIFI, encoding="utf-8")

    specs = load_specs(tmp_path)
    # WiFi spec has "switch" entity, BLE has "sensor".
    assert specs["Test Device"].entities[0].platform == "switch"


def test_malformed_yaml_warns(tmp_path, caplog) -> None:
    devices_dir = tmp_path / "devices"
    devices_dir.mkdir(parents=True)
    (devices_dir / "broken.yaml").write_text("not: valid: yaml: [", encoding="utf-8")

    specs = load_specs(tmp_path)
    assert specs == {}
    assert "malformed" in caplog.text.lower()


def test_ha_overrides_wemo_variants_and_entities(tmp_path, monkeypatch) -> None:
    """Wemo upstream has variants in extensions and no entities; overrides fix both."""
    import custom_components.liberated_bread.spec.loader as loader_mod

    devices_dir = tmp_path / "devices"
    devices_dir.mkdir(parents=True)

    # Simulate upstream Wemo: variants at top level (→ extensions), no entities.
    wemo_yaml = """
device:
  name: Belkin Wemo Smart Devices
  manufacturer: Belkin
  manufacturer_status: shutdown
  protocol: wifi
  transport: upnp
variants:
  - model: F7C063
    name: Wemo Mini Smart Plug
    identification:
      device_type: urn:Belkin:device:controllee:1
  - model: F7C029
    name: Wemo Insight Smart Plug
    identification:
      device_type: urn:Belkin:device:insight:1
"""
    (devices_dir / "wemo-devices.yaml").write_text(wemo_yaml, encoding="utf-8")

    # Inject overrides directly into the cache.
    overrides = {
        "Belkin Wemo Smart Devices": {
            "normalize_variants_from_extensions": True,
            "variant_entities": {
                "0": [
                    {
                        "platform": "switch",
                        "name": "Relay",
                        "commands": {"turn_on": "SetBinaryState", "turn_off": "SetBinaryState"},
                        "state_topic": "GetBinaryState",
                    }
                ],
                "1": [
                    {
                        "platform": "switch",
                        "name": "Relay",
                        "commands": {"turn_on": "SetBinaryState", "turn_off": "SetBinaryState"},
                        "state_topic": "GetBinaryState",
                    }
                ],
            },
        }
    }
    monkeypatch.setattr(loader_mod, "_OVERRIDES", overrides)

    try:
        specs = load_specs(tmp_path)
        wemo = specs["Belkin Wemo Smart Devices"]
        # Variants should now be on device.variants (not just extensions).
        assert wemo.device.variants is not None
        assert len(wemo.device.variants) == 2
        # Variant 0 (Mini) should have the switch entity.
        assert wemo.device.variants[0]["entities"][0].name == "Relay"
        # Variant 1 (Insight) should also have it.
        assert wemo.device.variants[1]["entities"][0].name == "Relay"
    finally:
        loader_mod._OVERRIDES = None


def test_ha_overrides_ble_identification(tmp_path, monkeypatch) -> None:
    """BLE specs missing local_name_prefix upstream get it from overrides."""
    import custom_components.liberated_bread.spec.loader as loader_mod

    devices_dir = tmp_path / "devices"
    devices_dir.mkdir(parents=True)

    # Upstream: identification block without local_name_prefix.
    magic_yaml = """
device:
  name: Magic Display
  manufacturer: tirohk
  manufacturer_status: abandoned
  protocol: ble
  identification:
    service_uuids:
      - "0000fee9-0000-1000-8000-00805f9b34fb"
"""
    (devices_dir / "magic-display.yaml").write_text(magic_yaml, encoding="utf-8")

    overrides = {
        "Magic Display": {
            "identification": {
                "local_name_prefix": ""
            }
        }
    }
    monkeypatch.setattr(loader_mod, "_OVERRIDES", overrides)

    try:
        specs = load_specs(tmp_path)
        magic = specs["Magic Display"]
        assert magic.device.identification is not None
        assert magic.device.identification.local_name_prefix == ""
    finally:
        loader_mod._OVERRIDES = None
