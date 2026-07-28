"""Constants for the Liberated Bread integration."""

from __future__ import annotations

from enum import StrEnum

try:
    from homeassistant.const import Platform
except ModuleNotFoundError:  # pragma: no cover - standalone import outside HA.
    class Platform(StrEnum):
        """Fallback platform enum used when Home Assistant is not installed."""

        LIGHT = "light"
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        SWITCH = "switch"
        CLIMATE = "climate"
        FAN = "fan"
        NUMBER = "number"
        SELECT = "select"

DOMAIN = "liberated_bread"

CONF_DEVICE_ADDRESS = "device_address"
CONF_DEVICE_ADDRESSES = "device_addresses"
CONF_DEVICE_NAME = "device_name"
CONF_SPEC_NAME = "spec_name"
CONF_SPEC_SOURCES = "spec_sources"
CONF_AES_KEYS = "aes_keys"
CONF_AES_ECB_KEY = "aes_ecb_key"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_CONTROL_URLS = "control_urls"
CONF_WIFI_DEVICES = "wifi_devices"
CONF_WIFI_IDENTITY = "wifi_identity"

DATA_MANAGER = "manager"
DATA_SPECS = "specs"

DEFAULT_SCAN_TIMEOUT = 10

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
]

SERVICE_UUID_KEY = "service_uuid"
CHARACTERISTIC_UUID_KEY = "characteristic_uuid"
