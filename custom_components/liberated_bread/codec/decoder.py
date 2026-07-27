"""Notification/read value decoder."""

from __future__ import annotations

import logging
from typing import Any

from ..spec.models import FormatField, ValueType

_LOGGER = logging.getLogger(__name__)


def decode_fields(raw: bytes | bytearray, fields: list[FormatField]) -> dict[str, Any]:
    """Decode raw bytes according to format fields."""
    data = bytes(raw)
    decoded: dict[str, Any] = {}
    for field in fields:
        end = field.offset + field.length
        if field.offset < 0 or field.length < 0 or end > len(data):
            _LOGGER.warning(
                "Skipping out-of-bounds field %s at offset %s length %s for payload length %s",
                field.name,
                field.offset,
                field.length,
                len(data),
            )
            continue
        chunk = data[field.offset:end]
        decoded[field.name] = _decode_value(chunk, field.field_type)
    return decoded


def _decode_value(chunk: bytes, value_type: ValueType) -> Any:
    if value_type == ValueType.BOOL:
        return bool(chunk[0]) if chunk else False
    if value_type == ValueType.UINT8:
        return int.from_bytes(chunk[:1], "little", signed=False)
    if value_type == ValueType.UINT16:
        return int.from_bytes(chunk[:2], "little", signed=False)
    if value_type == ValueType.UINT32:
        return int.from_bytes(chunk[:4], "little", signed=False)
    if value_type == ValueType.INT8:
        return int.from_bytes(chunk[:1], "little", signed=True)
    if value_type == ValueType.INT16:
        return int.from_bytes(chunk[:2], "little", signed=True)
    if value_type == ValueType.INT32:
        return int.from_bytes(chunk[:4], "little", signed=True)
    if value_type == ValueType.STRING:
        return chunk.rstrip(b"\x00").decode(errors="replace")
    if value_type == ValueType.BYTES:
        return chunk
    raise ValueError(f"unsupported value type: {value_type}")
