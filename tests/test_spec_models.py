"""Tests for spec dataclasses."""

from __future__ import annotations

import pytest

from custom_components.liberated_bread.spec.models import (
    CharacteristicProperty,
    Command,
    DeviceInfo,
    DeviceSpec,
    Discovery,
    DiscoveryMethod,
    EntityDef,
    FormatField,
    ManufacturerStatus,
    Parameter,
    Protocol,
    ValueType,
    _reject_duplicates,
)


def test_entity_def_from_dict() -> None:
    entity = EntityDef.from_dict({"platform": "sensor", "name": "Temp", "extra": 1})
    assert entity.platform == "sensor"
    assert entity.name == "Temp"
    assert entity.extensions == {"extra": 1}


def test_command_from_dict_value_template_and_both() -> None:
    assert Command.from_dict({"value": [1]}).value == [1]
    templated = Command.from_dict({"template": [1, "{value}"], "parameters": {"value": {"type": "uint8"}}})
    assert templated.template[1].is_param is True
    both = Command.from_dict({"value": [2], "template": [3]})
    assert both.value == [2]
    assert both.template[0].value == 3


def test_parameter_from_dict_range_validation() -> None:
    parameter = Parameter.from_dict({"type": "uint8", "min": 1, "max": 10})
    assert parameter.value_type == ValueType.UINT8
    with pytest.raises(ValueError, match="greater than max"):
        Parameter.from_dict({"type": "uint8", "min": 10, "max": 1})
    with pytest.raises(ValueError, match="outside"):
        Parameter.from_dict({"type": "uint8", "max": 300})


def test_characteristic_service_device_spec_from_dict() -> None:
    raw = {
        "device": {
            "name": "Device",
            "manufacturer": "Maker",
            "manufacturer_status": "active",
            "protocol": "ble",
        },
        "services": [
            {
                "uuid": "ABCD",
                "name": "Svc",
                "characteristics": [
                    {
                        "uuid": "DCBA",
                        "name": "Char",
                        "properties": ["read", "write"],
                        "commands": {"turn_on": {"value": [1]}},
                        "format": [{"offset": 0, "length": 1, "name": "value", "type": "bool"}],
                    }
                ],
            }
        ],
        "entities": [{"platform": "switch", "name": "Power"}],
    }
    spec = DeviceSpec.from_dict(raw)
    assert spec.device.protocol == Protocol.BLE
    service, characteristic = spec.find_characteristic("DCBA")
    assert service.name == "Svc"
    assert characteristic.properties == [CharacteristicProperty.READ, CharacteristicProperty.WRITE]
    _, found_char, command = spec.find_command("turn_on")
    assert found_char == characteristic
    assert command.value == [1]


def test_discovery_methods_and_device_info() -> None:
    discovery = Discovery.from_dict({"methods": [{"type": "ssdp", "ssdp": {"port_fallback": [49153]}}, {"type": "mdns", "service_type": "_x._tcp.local."}, {"type": "ble_scan", "service_uuids": ["ABCD"]}]})
    assert [method.type for method in discovery.methods] == ["ssdp", "mdns", "ble_scan"]
    assert DiscoveryMethod.from_dict({"type": "unknown"}).extensions["unknown_type"] == "unknown"
    info = DeviceInfo.from_dict({"name": "Device", "manufacturer": "Maker", "manufacturer_status": "abandoned", "protocol": "wifi", "transport": "upnp"})
    assert info.manufacturer_status == ManufacturerStatus.ABANDONED
    assert info.transport == "upnp"


def test_format_field_and_value_type_helpers() -> None:
    field = FormatField.from_dict({"offset": 1, "length": 2, "name": "temp", "type": "int16"})
    assert field.field_type.fixed_byte_size == 2
    assert ValueType.UINT8.integer_range == (0, 255)
    with pytest.raises(ValueError, match="smaller"):
        FormatField.from_dict({"offset": 0, "length": 1, "name": "bad", "type": "uint16"})


def test_reject_duplicates_helper() -> None:
    _reject_duplicates(["a", "b"], "field")
    with pytest.raises(ValueError, match="duplicate field"):
        _reject_duplicates(["a", "a"], "field")
