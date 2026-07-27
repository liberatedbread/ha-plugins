"""Dataclass models for OpenGreenIoT device specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self


class ManufacturerStatus(StrEnum):
    """Known manufacturer support states."""

    ABANDONED = "abandoned"
    ACTIVE = "active"
    SHUTDOWN = "shutdown"
    UNSUPPORTED = "unsupported"


class Protocol(StrEnum):
    """Primary transport protocol."""

    BLE = "ble"
    WIFI = "wifi"
    ZIGBEE = "zigbee"
    ZWAVE = "zwave"


class CharacteristicProperty(StrEnum):
    """BLE GATT characteristic property."""

    READ = "read"
    WRITE = "write"
    WRITE_WITHOUT_RESPONSE = "write_without_response"
    NOTIFY = "notify"
    INDICATE = "indicate"


class ValueType(StrEnum):
    """Supported scalar/binary value types."""

    BOOL = "bool"
    UINT8 = "uint8"
    UINT16 = "uint16"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    UINT32 = "uint32"
    BYTES = "bytes"
    STRING = "string"

    @property
    def fixed_byte_size(self) -> int | None:
        """Return the required byte width for fixed-size types."""
        return {
            ValueType.BOOL: 1,
            ValueType.UINT8: 1,
            ValueType.INT8: 1,
            ValueType.UINT16: 2,
            ValueType.INT16: 2,
            ValueType.INT32: 4,
            ValueType.UINT32: 4,
        }.get(self)

    @property
    def integer_range(self) -> tuple[int, int] | None:
        """Return the valid integer range for bounded integer types."""
        return {
            ValueType.BOOL: (0, 1),
            ValueType.UINT8: (0, 0xFF),
            ValueType.UINT16: (0, 0xFFFF),
            ValueType.UINT32: (0, 0xFFFFFFFF),
            ValueType.INT8: (-0x80, 0x7F),
            ValueType.INT16: (-0x8000, 0x7FFF),
            ValueType.INT32: (-0x80000000, 0x7FFFFFFF),
        }.get(self)


@dataclass(frozen=True)
class TemplateElement:
    """A byte literal or a named parameter reference in a command template."""

    value: int | str
    is_param: bool = False

    @classmethod
    def from_yaml(cls, raw: Any) -> Self:
        """Parse an integer byte or a string like ``"{brightness}"``."""
        if isinstance(raw, int):
            if not 0 <= raw <= 255:
                raise ValueError(f"template byte out of range: {raw}")
            return cls(raw, False)
        if isinstance(raw, str):
            if raw.startswith("{") and raw.endswith("}") and len(raw) > 2:
                return cls(raw[1:-1], True)
            raise ValueError(f"template parameter must be wrapped in braces: {raw}")
        raise TypeError(f"unsupported template element: {raw!r}")


@dataclass
class Parameter:
    """A named command parameter definition."""

    value_type: ValueType
    min: int | None = None
    max: int | None = None
    allowed: list[int] | None = None
    labels: list[str] | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        value_type = ValueType(data["type"])
        minimum = data.get("min")
        maximum = data.get("max")
        value_range = value_type.integer_range
        if value_range is not None:
            range_min, range_max = value_range
            if minimum is not None and not range_min <= int(minimum) <= range_max:
                raise ValueError(
                    f"parameter min {minimum} outside {value_type} range "
                    f"{range_min}..{range_max}"
                )
            if maximum is not None and not range_min <= int(maximum) <= range_max:
                raise ValueError(
                    f"parameter max {maximum} outside {value_type} range "
                    f"{range_min}..{range_max}"
                )
            if minimum is not None and maximum is not None and int(minimum) > int(maximum):
                raise ValueError(f"parameter min {minimum} greater than max {maximum}")
        return cls(
            value_type=value_type,
            min=data.get("min"),
            max=data.get("max"),
            allowed=data.get("allowed"),
            labels=data.get("labels"),
            notes=data.get("notes"),
        )


@dataclass
class ParameterSet:
    """Parameter definitions for a template command."""

    color_order: str | None = None
    params: dict[str, Parameter] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self:
        if not data:
            return cls()
        params = {
            key: Parameter.from_dict(value)
            for key, value in data.items()
            if key != "color_order" and isinstance(value, dict) and "type" in value
        }
        return cls(color_order=data.get("color_order"), params=params)


@dataclass
class Command:
    """A named command for a writable characteristic."""

    description: str
    value: list[int] | None = None
    template: list[TemplateElement] | None = None
    parameters: ParameterSet | None = None
    setting_id: str | None = None
    encoding: str | None = None
    payload: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        template = data.get("template")
        value = data.get("value")
        if value is not None:
            for byte in value:
                if not isinstance(byte, int) or not 0 <= byte <= 255:
                    raise ValueError(f"command byte out of range: {byte!r}")
        return cls(
            description=data.get("description", ""),
            value=value,
            template=[TemplateElement.from_yaml(item) for item in template]
            if template is not None
            else None,
            parameters=ParameterSet.from_dict(data.get("parameters")),
            setting_id=data.get("setting_id"),
            encoding=data.get("encoding"),
            payload=data.get("payload"),
        )


@dataclass
class FormatField:
    """A binary field decoded from a readable/notifiable characteristic."""

    offset: int
    length: int
    name: str
    field_type: ValueType
    mock_default: Any = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        offset = int(data["offset"])
        length = int(data["length"])
        if offset < 0 or length < 0:
            raise ValueError(f"format field {data.get('name')} has negative offset/length")
        if offset + length < offset:
            raise ValueError(f"format field {data.get('name')} offset overflow")
        field_type = ValueType(data["type"])
        fixed_size = field_type.fixed_byte_size
        if fixed_size is not None and length < fixed_size:
            raise ValueError(
                f"format field {data.get('name')} length {length} is smaller than "
                f"{field_type} width {fixed_size}"
            )
        return cls(
            offset=offset,
            length=length,
            name=str(data["name"]),
            field_type=field_type,
            mock_default=data.get("mock_default"),
        )


@dataclass
class Characteristic:
    """A BLE GATT characteristic."""

    uuid: str
    name: str
    properties: list[CharacteristicProperty]
    commands: dict[str, Command] | None = None
    format: list[FormatField] | None = None
    notes: str | None = None
    encryption: dict[str, Any] | None = None
    framing: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        commands = data.get("commands")
        fmt = data.get("format")
        parsed_format = (
            [FormatField.from_dict(item) for item in fmt] if isinstance(fmt, list) else None
        )
        if parsed_format is not None:
            _reject_duplicates([field.name for field in parsed_format], "format field")
        return cls(
            uuid=str(data["uuid"]).lower(),
            name=str(data["name"]),
            properties=[
                CharacteristicProperty(prop) for prop in data.get("properties", [])
            ],
            commands={name: Command.from_dict(cmd) for name, cmd in commands.items()}
            if isinstance(commands, dict)
            else None,
            format=parsed_format,
            notes=data.get("notes"),
            encryption=data.get("encryption"),
            framing=data.get("framing"),
        )


@dataclass
class Service:
    """A BLE GATT service."""

    uuid: str
    name: str
    characteristics: list[Characteristic] = field(default_factory=list)
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            uuid=str(data["uuid"]).lower(),
            name=str(data["name"]),
            characteristics=[
                Characteristic.from_dict(item)
                for item in data.get("characteristics", [])
            ],
            notes=data.get("notes"),
        )


@dataclass
class DiscoveryMethod:
    """A single machine-readable device discovery method."""

    type: str
    multicast_group: str | None = None
    multicast_port: int | None = None
    search_targets: list[str] = field(default_factory=list)
    response_mapping: dict[str, Any] | None = None
    port_fallback: list[int] = field(default_factory=list)
    service_type: str | None = None
    port: int | None = None
    txt_record_keys: list[str] = field(default_factory=list)
    identity_mapping: dict[str, Any] | None = None
    provider: str | None = None
    auth_method: str | None = None
    device_list_endpoint: dict[str, Any] | None = None
    local_name: str | None = None
    service_uuids: list[str] = field(default_factory=list)
    manufacturer_data: dict[str, Any] | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        method_type = str(data.get("type", "")).strip()
        section = data.get(method_type)
        if not isinstance(section, dict):
            section = data
        valid_types = {"ble_scan", "ssdp", "mdns", "cloud"}
        known = {
            "type",
            "ssdp",
            "mdns",
            "cloud",
            "ble_scan",
            "multicast_group",
            "multicast_port",
            "search_targets",
            "response_mapping",
            "port_fallback",
            "service_type",
            "port",
            "txt_record_keys",
            "identity_mapping",
            "provider",
            "auth_method",
            "device_list_endpoint",
            "local_name",
            "service_uuids",
            "manufacturer_data",
        }
        extensions = {key: value for key, value in data.items() if key not in known}
        extensions.update({key: value for key, value in section.items() if key not in known})
        if method_type not in valid_types:
            extensions["unknown_type"] = method_type
        return cls(
            type=method_type,
            multicast_group=section.get("multicast_group"),
            multicast_port=section.get("multicast_port"),
            search_targets=list(section.get("search_targets") or []),
            response_mapping=section.get("response_mapping"),
            port_fallback=list(section.get("port_fallback") or []),
            service_type=section.get("service_type"),
            port=section.get("port"),
            txt_record_keys=list(section.get("txt_record_keys") or []),
            identity_mapping=section.get("identity_mapping"),
            provider=section.get("provider"),
            auth_method=section.get("auth_method"),
            device_list_endpoint=section.get("device_list_endpoint"),
            local_name=section.get("local_name"),
            service_uuids=[
                str(uuid).lower() for uuid in section.get("service_uuids") or []
            ],
            manufacturer_data=section.get("manufacturer_data"),
            extensions=extensions,
        )


@dataclass
class DiscoveryIdentity:
    """Stable and display identity fields for discovered devices."""

    stable_keys: list[str] = field(default_factory=list)
    display: str = "name"
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self:
        if not data:
            return cls()
        known = {"stable_keys", "display"}
        return cls(
            stable_keys=list(data.get("stable_keys") or []),
            display=str(data.get("display") or "name"),
            extensions={key: value for key, value in data.items() if key not in known},
        )


@dataclass
class Discovery:
    """Machine-readable discovery metadata for a device family."""

    methods: list[DiscoveryMethod] = field(default_factory=list)
    identity: DiscoveryIdentity = field(default_factory=DiscoveryIdentity)
    static_ip_required: bool = False
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        known = {"methods", "identity", "static_ip_required"}
        return cls(
            methods=[
                DiscoveryMethod.from_dict(item)
                for item in data.get("methods") or []
                if isinstance(item, dict)
            ],
            identity=DiscoveryIdentity.from_dict(data.get("identity")),
            static_ip_required=bool(data.get("static_ip_required", False)),
            extensions={key: value for key, value in data.items() if key not in known},
        )


@dataclass
class Identification:
    """Discovery hints for BLE/Wi-Fi devices."""

    local_name_prefix: str | None = None
    service_uuids: list[str] | None = None
    mdns_service_type: str | None = None
    ssid_prefix: str | None = None
    default_port: int | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        known = {
            "local_name_prefix",
            "service_uuids",
            "mdns_service_type",
            "ssid_prefix",
            "default_port",
        }
        return cls(
            local_name_prefix=data.get("local_name_prefix"),
            service_uuids=[uuid.lower() for uuid in data.get("service_uuids") or []],
            mdns_service_type=data.get("mdns_service_type"),
            ssid_prefix=data.get("ssid_prefix"),
            default_port=data.get("default_port"),
            extensions={key: value for key, value in data.items() if key not in known},
        )


@dataclass
class DeviceInfo:
    """Device metadata and identification."""

    name: str
    manufacturer: str
    manufacturer_status: ManufacturerStatus
    protocol: Protocol
    notes: str | None = None
    identification: Identification | None = None
    discovery: Discovery | None = None
    variants: Any = None
    protobuf: Any = None
    state_machine: Any = None
    version_fields: Any = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=str(data["name"]),
            manufacturer=str(data["manufacturer"]),
            manufacturer_status=ManufacturerStatus(data["manufacturer_status"]),
            protocol=Protocol(data["protocol"]),
            notes=data.get("notes"),
            identification=Identification.from_dict(data.get("identification")),
            discovery=Discovery.from_dict(data.get("discovery")),
            variants=data.get("variants"),
            protobuf=data.get("protobuf"),
            state_machine=data.get("state_machine"),
            version_fields=data.get("version_fields"),
        )


@dataclass
class EntityDef:
    """Home Assistant entity declaration from a device spec."""

    platform: str
    name: str
    features: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)
    state_mapping: dict[str, str] = field(default_factory=dict)
    state_characteristic: str | None = None
    state_topic: str | None = None
    device_class: str | None = None
    unit: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        known = {
            "platform",
            "name",
            "features",
            "commands",
            "state_mapping",
            "state_characteristic",
            "state_topic",
            "device_class",
            "unit",
        }
        return cls(
            platform=str(data["platform"]),
            name=str(data["name"]),
            features=list(data.get("features") or []),
            commands=dict(data.get("commands") or {}),
            state_mapping=dict(data.get("state_mapping") or {}),
            state_characteristic=str(data["state_characteristic"]).lower()
            if data.get("state_characteristic")
            else None,
            state_topic=data.get("state_topic"),
            device_class=data.get("device_class"),
            unit=data.get("unit"),
            extensions={key: value for key, value in data.items() if key not in known},
        )


@dataclass
class HttpEndpoint:
    """HTTP REST endpoint declared by a device spec."""

    method: str
    path: str
    name: str
    description: str | None = None
    request_body: dict[str, Any] | None = None
    response_body: dict[str, Any] | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        known = {
            "method",
            "path",
            "name",
            "description",
            "request_body",
            "response_body",
        }
        return cls(
            method=str(data.get("method", "GET")).upper(),
            path=str(data["path"]),
            name=str(data["name"]),
            description=data.get("description"),
            request_body=data.get("request_body"),
            response_body=data.get("response_body"),
            extensions={key: value for key, value in data.items() if key not in known},
        )


@dataclass
class MqttTopic:
    """MQTT topic declared by a device spec."""

    topic: str
    name: str
    direction: str
    description: str | None = None
    qos: int | None = None
    payload_format: dict[str, Any] | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        known = {
            "topic",
            "name",
            "direction",
            "description",
            "qos",
            "payload_format",
        }
        return cls(
            topic=str(data["topic"]),
            name=str(data["name"]),
            direction=str(data["direction"]),
            description=data.get("description"),
            qos=data.get("qos"),
            payload_format=data.get("payload_format"),
            extensions={key: value for key, value in data.items() if key not in known},
        )


@dataclass
class DeviceSpec:
    """Top-level OpenGreenIoT device specification."""

    device: DeviceInfo
    services: list[Service] = field(default_factory=list)
    entities: list[EntityDef] = field(default_factory=list)
    http_endpoints: list[HttpEndpoint] = field(default_factory=list)
    mqtt_topics: list[MqttTopic] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        known = {"device", "services", "entities", "http_endpoints", "mqtt_topics"}
        return cls(
            device=DeviceInfo.from_dict(data["device"]),
            services=[Service.from_dict(item) for item in data.get("services") or []],
            entities=[
                EntityDef.from_dict(item) for item in data.get("entities") or []
            ],
            http_endpoints=[
                HttpEndpoint.from_dict(item)
                for item in data.get("http_endpoints") or []
                if isinstance(item, dict)
            ],
            mqtt_topics=[
                MqttTopic.from_dict(item)
                for item in data.get("mqtt_topics") or []
                if isinstance(item, dict)
            ],
            extensions={key: value for key, value in data.items() if key not in known},
        )

    def find_characteristic(
        self, uuid: str
    ) -> tuple[Service, Characteristic] | tuple[None, None]:
        """Find a characteristic by UUID across all services."""
        normalized = uuid.lower()
        for service in self.services:
            for characteristic in service.characteristics:
                if characteristic.uuid.lower() == normalized:
                    return service, characteristic
        return None, None

    def find_command(
        self, command_name: str
    ) -> tuple[Service, Characteristic, Command] | tuple[None, None, None]:
        """Find a command by name across all writable characteristics."""
        for service in self.services:
            for characteristic in service.characteristics:
                if characteristic.commands and command_name in characteristic.commands:
                    return service, characteristic, characteristic.commands[command_name]
        return None, None, None


def _reject_duplicates(values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {label} name: {value}")
        seen.add(value)
