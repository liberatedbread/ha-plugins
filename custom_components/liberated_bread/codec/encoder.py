"""Command encoder for OpenGreenIoT templates."""

from __future__ import annotations

import json
from typing import Any

from ..spec.models import Command, ValueType


def encode_command(command: Command, values: dict[str, Any] | None = None) -> bytes:
    """Encode a command and parameters into a BLE payload."""
    values = values or {}
    if command.value is not None:
        return bytes(command.value)
    if command.encoding == "json":
        return _encode_json_command(command, values)
    if not command.template:
        raise ValueError("command has no value or template")

    params = command.parameters.params if command.parameters else {}
    output = bytearray()
    for element in command.template:
        if not element.is_param:
            output.append(int(element.value))
            continue
        name = str(element.value)
        if name not in values:
            raise KeyError(f"missing command parameter: {name}")
        parameter = params.get(name)
        output.extend(_encode_value(values[name], parameter.value_type if parameter else None))
    return bytes(output)


def _encode_value(value: Any, value_type: ValueType | None) -> bytes:
    """Encode a scalar according to a spec value type."""
    if value_type is None:
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
            return bytes(value)
        if isinstance(value, str):
            return value.encode()
        return int(value).to_bytes(1, "little", signed=False)

    if value_type == ValueType.BOOL:
        return (1 if bool(value) else 0).to_bytes(1, "little")
    if value_type == ValueType.UINT8:
        return _bounded_int(value, 0, 0xFF).to_bytes(1, "little")
    if value_type == ValueType.UINT16:
        return _bounded_int(value, 0, 0xFFFF).to_bytes(2, "little")
    if value_type == ValueType.UINT32:
        return _bounded_int(value, 0, 0xFFFFFFFF).to_bytes(4, "little")
    if value_type == ValueType.INT8:
        return _bounded_int(value, -0x80, 0x7F).to_bytes(1, "little", signed=True)
    if value_type == ValueType.INT16:
        return _bounded_int(value, -0x8000, 0x7FFF).to_bytes(2, "little", signed=True)
    if value_type == ValueType.INT32:
        return _bounded_int(value, -0x80000000, 0x7FFFFFFF).to_bytes(
            4, "little", signed=True
        )
    if value_type == ValueType.STRING:
        return str(value).encode()
    if value_type == ValueType.BYTES:
        if isinstance(value, str):
            return bytes.fromhex(value)
        return bytes(value)
    raise ValueError(f"unsupported value type: {value_type}")


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"value {value} is fractional")
    if isinstance(value, str) and "." in value:
        raise ValueError(f"value {value} is fractional")
    integer = int(value)
    if not minimum <= integer <= maximum:
        raise ValueError(f"value {integer} outside range {minimum}..{maximum}")
    return integer


def _encode_json_command(command: Command, values: dict[str, Any]) -> bytes:
    """Best-effort encoder for specs that declare JSON payloads."""
    payload = command.payload or {}
    key = payload.get("key")
    if not key:
        raise ValueError("json command payload is missing key")
    value = values.get("value")
    if value is None:
        value = values.get(key.rsplit(".", 1)[-1], payload.get("value"))
    document: dict[str, Any] = {"sno": int(values.get("sno", 1))}
    _set_dotted(document, key, value)
    return json.dumps(document, separators=(",", ":")).encode()


def _set_dotted(document: dict[str, Any], dotted_key: str, value: Any) -> None:
    target = document
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
