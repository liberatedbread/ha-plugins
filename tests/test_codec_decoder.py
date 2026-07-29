"""Tests for binary state decoding."""

from __future__ import annotations

from custom_components.liberated_bread.codec.decoder import decode_fields
from custom_components.liberated_bread.spec.models import FormatField, ValueType


def test_decode_fields_for_each_value_type() -> None:
    fields = [
        FormatField(0, 1, "bool", ValueType.BOOL),
        FormatField(1, 1, "u8", ValueType.UINT8),
        FormatField(2, 2, "u16", ValueType.UINT16),
        FormatField(4, 4, "u32", ValueType.UINT32),
        FormatField(8, 1, "i8", ValueType.INT8),
        FormatField(9, 2, "i16", ValueType.INT16),
        FormatField(11, 4, "i32", ValueType.INT32),
        FormatField(15, 4, "string", ValueType.STRING),
        FormatField(19, 2, "bytes", ValueType.BYTES),
    ]
    raw = b"\x01\xff\x01\x02\x01\x00\x00\x00\xff\xfe\xff\xfd\xff\xff\xffhi\x00x\xaa\xbb"
    assert decode_fields(raw, fields) == {
        "bool": True,
        "u8": 255,
        "u16": 513,
        "u32": 1,
        "i8": -1,
        "i16": -2,
        "i32": -3,
        "string": "hi\x00x",
        "bytes": b"\xaa\xbb",
    }


def test_out_of_bounds_field_is_skipped() -> None:
    assert decode_fields(b"\x01", [FormatField(1, 2, "missing", ValueType.UINT16)]) == {}


def test_string_null_termination_trims_trailing_nulls() -> None:
    fields = [FormatField(0, 5, "name", ValueType.STRING)]
    assert decode_fields(b"abc\x00\x00", fields)["name"] == "abc"


def test_bool_decoding_empty_and_nonzero() -> None:
    assert decode_fields(b"\x00\x02", [FormatField(0, 1, "a", ValueType.BOOL), FormatField(1, 1, "b", ValueType.BOOL)]) == {"a": False, "b": True}
