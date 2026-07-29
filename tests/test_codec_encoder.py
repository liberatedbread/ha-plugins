"""Tests for command encoding."""

from __future__ import annotations

import json

import pytest

from custom_components.liberated_bread.codec.encoder import (
    _bounded_int,
    _encode_value,
    encode_command,
)
from custom_components.liberated_bread.spec.models import (
    Command,
    Parameter,
    ParameterSet,
    TemplateElement,
    ValueType,
)


def test_encode_command_static_value() -> None:
    assert encode_command(Command(description="on", value=[1, 2, 255])) == b"\x01\x02\xff"


@pytest.mark.parametrize(
    ("value_type", "value", "expected"),
    [
        (ValueType.BOOL, True, b"\x01"),
        (ValueType.UINT8, 255, b"\xff"),
        (ValueType.UINT16, 513, b"\x01\x02"),
        (ValueType.UINT32, 1, b"\x01\x00\x00\x00"),
        (ValueType.INT8, -1, b"\xff"),
        (ValueType.INT16, -2, b"\xfe\xff"),
        (ValueType.INT32, -3, b"\xfd\xff\xff\xff"),
        (ValueType.STRING, "ok", b"ok"),
        (ValueType.BYTES, "0a ff", b"\x0a\xff"),
    ],
)
def test_encode_value_for_each_value_type(value_type, value, expected) -> None:
    assert _encode_value(value, value_type) == expected


def test_encode_command_template_all_scalar_value_types() -> None:
    command = Command(
        description="template",
        template=[
            TemplateElement(0xAA),
            TemplateElement("flag", True),
            TemplateElement("temp", True),
            TemplateElement("name", True),
        ],
        parameters=ParameterSet(
            params={
                "flag": Parameter(ValueType.BOOL),
                "temp": Parameter(ValueType.INT16),
                "name": Parameter(ValueType.STRING),
            }
        ),
    )
    assert encode_command(command, {"flag": 1, "temp": -10, "name": "hi"}) == b"\xaa\x01\xf6\xffhi"


def test_encode_command_json() -> None:
    command = Command(
        description="json",
        encoding="json",
        payload={"key": "settings.temperature"},
    )
    assert json.loads(encode_command(command, {"temperature": 72, "sno": 3})) == {
        "sno": 3,
        "settings": {"temperature": 72},
    }


def test_bounded_int_validation() -> None:
    assert _bounded_int("5", 0, 10) == 5
    with pytest.raises(ValueError, match="fractional"):
        _bounded_int(1.5, 0, 10)
    with pytest.raises(ValueError, match="outside range"):
        _bounded_int(11, 0, 10)


def test_encode_command_errors() -> None:
    with pytest.raises(ValueError, match="no value or template"):
        encode_command(Command(description="empty"))
    command = Command(
        description="missing",
        template=[TemplateElement("brightness", True)],
        parameters=ParameterSet(params={"brightness": Parameter(ValueType.UINT8)}),
    )
    with pytest.raises(KeyError, match="brightness"):
        encode_command(command, {})
    with pytest.raises(ValueError, match="outside range"):
        encode_command(command, {"brightness": 300})
    with pytest.raises(ValueError, match="missing key"):
        encode_command(Command(description="json", encoding="json"), {})
