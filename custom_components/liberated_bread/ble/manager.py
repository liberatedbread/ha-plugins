"""Central BLE manager for Liberated Bread devices."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

import yaml
from bleak import BleakClient

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo as HADeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import DOMAIN
from ..codec.crypto import encrypt_aes_128_ecb
from ..codec.decoder import decode_fields
from ..codec.encoder import encode_command
from ..spec.models import Characteristic, DeviceSpec
from .scanner import service_info_matches_spec

_LOGGER = logging.getLogger(__name__)


@dataclass
class LiberatedBreadDevice:
    """A discovered BLE device and its decoded state."""

    address: str
    name: str
    spec: DeviceSpec
    service_info: BluetoothServiceInfoBleak | None = None
    state: dict[str, Any] = field(default_factory=dict)


class LiberatedBreadManager(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Manage discovery, connections, commands, and decoded BLE state."""

    def __init__(
        self,
        hass: HomeAssistant,
        specs: dict[str, DeviceSpec],
        selected_addresses: set[str] | None = None,
        selected_spec_name: str | None = None,
        aes_keys: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Liberated Bread",
            update_interval=timedelta(seconds=15),
        )
        self.specs = specs
        self.selected_addresses = selected_addresses or set()
        self.selected_spec_name = selected_spec_name
        self.aes_keys = aes_keys or {}
        self.devices: dict[str, LiberatedBreadDevice] = {}
        self._entities_by_state_char: dict[str, dict[str, list[str]]] = {}
        self._clients: dict[str, BleakClient] = {}
        self._unsub: CALLBACK_TYPE | None = None
        self._notification_unsubs: dict[tuple[str, str], Callable[[], Any]] = {}
        if selected_spec_name and selected_spec_name in specs:
            spec = specs[selected_spec_name]
            for address in self.selected_addresses:
                self.devices[address] = LiberatedBreadDevice(address, spec.device.name, spec)
                self._index_state_entities(address, spec)

    async def async_start(self) -> None:
        """Start receiving BLE advertisements."""
        if self._unsub is not None:
            return
        self._unsub = bluetooth.async_register_callback(
            self.hass,
            self._advertisement_callback,
            {"connectable": True},
            BluetoothScanningMode.ACTIVE,
        )
        for service_info in bluetooth.async_discovered_service_info(self.hass):
            self._handle_service_info(service_info)

    async def async_stop(self) -> None:
        """Stop discovery and disconnect active clients."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await asyncio.gather(
            *(self.disconnect(address) for address in list(self._clients)),
            return_exceptions=True,
        )

    @callback
    def _advertisement_callback(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        if change == BluetoothChange.UNAVAILABLE:
            return
        self._handle_service_info(service_info)

    @callback
    def _handle_service_info(self, service_info: BluetoothServiceInfoBleak) -> None:
        address = service_info.address
        if self.selected_addresses and address not in self.selected_addresses:
            return
        candidate_specs = (
            [self.specs[self.selected_spec_name]]
            if self.selected_spec_name and self.selected_spec_name in self.specs
            else self.specs.values()
        )
        for spec in candidate_specs:
            if not service_info_matches_spec(service_info, spec):
                continue
            name = service_info.name or spec.device.name
            existing_state = self.devices.get(address, LiberatedBreadDevice(address, name, spec)).state
            self.devices[address] = LiberatedBreadDevice(
                address, name, spec, service_info, existing_state
            )
            self._index_state_entities(address, spec)
            self.async_set_updated_data(
                {addr: device.state for addr, device in self.devices.items()}
            )
            return

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        return {address: device.state for address, device in self.devices.items()}

    async def connect(self, device_address: str) -> BleakClient:
        """Connect to a device by address."""
        if device_address in self._clients and self._clients[device_address].is_connected:
            return self._clients[device_address]
        device = self.devices.get(device_address)
        if device is None:
            raise ValueError(f"device has not been discovered: {device_address}")
        if device.service_info is None:
            raise ValueError(f"device has not advertised yet: {device_address}")
        bleak_device = bluetooth.async_ble_device_from_address(
            self.hass, device_address, connectable=True
        )
        if bleak_device is None:
            raise ValueError(f"no connectable BLE device for address: {device_address}")
        client = BleakClient(bleak_device)
        await client.connect()
        self._clients[device_address] = client
        await self._subscribe_notifications(device)
        return client

    async def disconnect(self, device_address: str) -> None:
        """Disconnect from a device."""
        for key in list(self._notification_unsubs):
            address, char_uuid = key
            if address == device_address:
                unsub = self._notification_unsubs.pop((address, char_uuid))
                result = unsub()
                if asyncio.iscoroutine(result):
                    await result
        client = self._clients.pop(device_address, None)
        if client and client.is_connected:
            await client.disconnect()

    async def write_command(
        self,
        device_address: str,
        service_uuid: str | None,
        char_uuid: str | None,
        command_name: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Encode and write a named command to a BLE characteristic."""
        device = self.devices.get(device_address)
        if device is None:
            raise ValueError(f"unknown device: {device_address}")
        if char_uuid:
            _, characteristic = device.spec.find_characteristic(char_uuid)
            if characteristic is None or not characteristic.commands:
                raise ValueError(f"unknown command characteristic: {char_uuid}")
            command = characteristic.commands[command_name]
            target_char_uuid = characteristic.uuid
        else:
            _, characteristic, command = device.spec.find_command(command_name)
            if characteristic is None or command is None:
                raise ValueError(f"unknown command: {command_name}")
            target_char_uuid = characteristic.uuid
        payload = encode_command(command, params or {})
        if _uses_aes_ecb(characteristic):
            key = self._resolve_encryption_key(characteristic)
            payload = encrypt_aes_128_ecb(payload, key)
        client = await self.connect(device_address)
        properties = {prop.value for prop in characteristic.properties}
        response = "write" in properties or "write_without_response" not in properties
        await client.write_gatt_char(target_char_uuid, payload, response=response)

    async def read_characteristic(
        self, device_address: str, service_uuid: str | None, char_uuid: str
    ) -> bytes:
        """Read a BLE characteristic and update decoded state when possible."""
        device = self.devices.get(device_address)
        if device is None:
            raise ValueError(f"unknown device: {device_address}")
        client = await self.connect(device_address)
        raw = bytes(await client.read_gatt_char(char_uuid))
        self._decode_into_state(device, char_uuid, raw)
        return raw

    def state_for(self, device_address: str, entity_name: str, key: str) -> Any:
        """Return a decoded entity state value."""
        device = self.devices.get(device_address)
        if device is None:
            return None
        return device.state.get(entity_name, {}).get(key)

    def device_info_for(self, device_address: str) -> HADeviceInfo:
        """Return Home Assistant device info for a managed BLE device."""
        device = self.devices[device_address]
        return HADeviceInfo(
            identifiers={(DOMAIN, device_address)},
            name=device.name,
            manufacturer=device.spec.device.manufacturer,
            model=device.spec.device.name,
        )

    async def request_state(self, device_address: str, entity: Any) -> Any:
        """Refresh state for an entity if it has a readable characteristic."""
        if not getattr(entity, "state_characteristic", None):
            return None
        await self.read_characteristic(device_address, None, entity.state_characteristic)
        device = self.devices.get(device_address)
        if device is None:
            return None
        return device.state.get(entity.name, {})

    async def _subscribe_notifications(self, device: LiberatedBreadDevice) -> None:
        client = self._clients[device.address]
        for service in device.spec.services:
            for characteristic in service.characteristics:
                if characteristic.format is None:
                    continue
                if "notify" not in {prop.value for prop in characteristic.properties}:
                    continue
                key = (device.address, characteristic.uuid)
                if key in self._notification_unsubs:
                    continue

                def _handler(
                    _: int,
                    data: bytearray,
                    char_uuid: str = characteristic.uuid,
                    device_address: str = device.address,
                ) -> None:
                    current_device = self.devices.get(device_address)
                    if current_device is not None:
                        self._decode_into_state(current_device, char_uuid, bytes(data))

                await client.start_notify(characteristic.uuid, _handler)
                self._notification_unsubs[key] = (
                    lambda c=client, uuid=characteristic.uuid: c.stop_notify(uuid)
                )

    @callback
    def _decode_into_state(
        self, device: LiberatedBreadDevice, char_uuid: str, raw: bytes
    ) -> None:
        _, characteristic = device.spec.find_characteristic(char_uuid)
        if characteristic is None or not characteristic.format:
            return
        values = decode_fields(raw, characteristic.format)
        for entity in self._entities_for_characteristic(device, char_uuid):
            mapped = {
                target: values.get(source)
                for target, source in entity.state_mapping.items()
                if source in values
            }
            if not mapped and values:
                mapped = dict(values)
                mapped.setdefault("value", next(iter(values.values())))
            if mapped:
                device.state.setdefault(entity.name, {}).update(mapped)
        self.async_set_updated_data(
            {address: dev.state for address, dev in self.devices.items()}
        )

    def _index_state_entities(self, device_address: str, spec: DeviceSpec) -> None:
        index: dict[str, list[str]] = {}
        for entity in spec.entities:
            if entity.state_characteristic:
                index.setdefault(entity.state_characteristic.lower(), []).append(entity.name)
        self._entities_by_state_char[device_address] = index

    def _entities_for_characteristic(
        self, device: LiberatedBreadDevice, char_uuid: str
    ):
        index = self._entities_by_state_char.get(device.address)
        if not index:
            return [
                entity
                for entity in device.spec.entities
                if not entity.state_characteristic
                or entity.state_characteristic.lower() == char_uuid.lower()
            ]
        names = set(index.get(char_uuid.lower(), []))
        return [entity for entity in device.spec.entities if entity.name in names]

    def _resolve_encryption_key(self, characteristic: Characteristic) -> str:
        encryption = characteristic.encryption or {}
        key = encryption.get("static_key") or self.aes_keys.get(
            encryption.get("algorithm", "aes-128-ecb")
        )
        if not key:
            raise ValueError(
                f"no AES key configured for encrypted characteristic {characteristic.uuid}"
            )
        if isinstance(key, str) and key.startswith("secrets://"):
            return self._read_secret(key.removeprefix("secrets://"))
        return str(key)

    def _read_secret(self, secret_name: str) -> str:
        secrets_path = self.hass.config.path("secrets.yaml")
        try:
            with open(secrets_path, "r", encoding="utf-8") as file:
                secrets = yaml.safe_load(file) or {}
        except FileNotFoundError as err:
            raise ValueError(f"secrets.yaml not found for secret {secret_name}") from err
        value = secrets.get(secret_name)
        if value is None:
            raise ValueError(f"secret {secret_name} not found in secrets.yaml")
        return str(value)


def _uses_aes_ecb(characteristic: Characteristic) -> bool:
    encryption = characteristic.encryption or {}
    return encryption.get("algorithm") == "aes-128-ecb"
