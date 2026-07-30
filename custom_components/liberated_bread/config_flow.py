"""Config flow for Liberated Bread."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .ble.scanner import service_info_matches_spec
from .const import (
    CONF_AES_ECB_KEY,
    CONF_AES_KEYS,
    CONF_CONTROL_URLS,
    CONF_DEVICE_ADDRESSES,
    CONF_HOST,
    CONF_PORT,
    CONF_SPEC_NAME,
    CONF_WIFI_DEVICES,
    CONF_WIFI_IDENTITY,
    CONF_WIFI_VARIANT,
    DEFAULT_SCAN_TIMEOUT,
    DOMAIN,
)
from .spec.loader import load_specs
from .spec.models import DeviceSpec, Protocol
from .wifi.discovery import DiscoveredDevice, WifiDiscovery
from .wifi.identity import (
    derive_device_key,
    normalize_identity,
)


class LiberatedBreadConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Liberated Bread."""

    VERSION = 2

    def __init__(self) -> None:
        self._specs: dict[str, DeviceSpec] = {}
        self._spec_name: str | None = None
        self._aes_keys: dict[str, str] = {}
        self._matches: dict[str, BluetoothServiceInfoBleak] = {}
        self._wifi_matches: dict[str, DiscoveredDevice] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Select the supported device family to configure."""
        self._specs = await self.hass.async_add_executor_job(load_specs)
        if not self._specs:
            return self.async_abort(reason="no_specs")

        if user_input is not None:
            self._spec_name = user_input[CONF_SPEC_NAME]
            spec = self._specs[self._spec_name]
            if spec.device.protocol == Protocol.WIFI:
                if _spec_is_cloud_only(spec):
                    return await self.async_step_cloud_auth()
                return await self.async_step_wifi_discovery()
            if _spec_needs_aes_ecb_key(spec):
                return await self.async_step_encryption()
            return await self.async_step_scan()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SPEC_NAME): vol.In(
                        {name: name for name in sorted(self._specs)}
                    )
                }
            ),
        )

    async def async_step_scan(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Scan for matching BLE devices and let the user select devices."""
        if self._spec_name is None:
            return await self.async_step_user()
        spec = self._specs[self._spec_name]

        if user_input is not None and CONF_DEVICE_ADDRESSES in user_input:
            selected = list(user_input[CONF_DEVICE_ADDRESSES])
            await self.async_set_unique_id(f"{DOMAIN}_{self._spec_name}")
            self._abort_if_unique_id_configured()
            data = {
                CONF_SPEC_NAME: self._spec_name,
                CONF_DEVICE_ADDRESSES: selected,
            }
            if self._aes_keys:
                data[CONF_AES_KEYS] = self._aes_keys
            return self.async_create_entry(
                title=f"Liberated Bread {self._spec_name}",
                data=data,
                options={CONF_DEVICE_ADDRESSES: selected},
            )

        self._matches = await _scan_for_matches(self.hass, spec, DEFAULT_SCAN_TIMEOUT)
        if not self._matches:
            return self.async_show_form(
                step_id="scan",
                data_schema=vol.Schema({}),
                errors={"base": "no_devices_found"},
                description_placeholders={"device_type": self._spec_name},
            )

        choices = {
            address: f"{info.name or spec.device.name} ({address})"
            for address, info in sorted(self._matches.items())
        }
        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ADDRESSES): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=value, label=label)
                                for value, label in choices.items()
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            description_placeholders={"device_type": self._spec_name},
        )

    async def async_step_wifi_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Discover matching WiFi devices or accept manual host details."""
        if self._spec_name is None:
            return await self.async_step_user()
        spec = self._specs[self._spec_name]

        if user_input is not None:
            selected_key = user_input.get("wifi_device")
            if selected_key and selected_key in self._wifi_matches:
                device = self._wifi_matches[selected_key]
                return await self._create_wifi_entry(spec, device)
            host = (user_input.get(CONF_HOST) or "").strip()
            if host:
                port = int(user_input.get(CONF_PORT) or _default_wifi_port(spec))

                # Accept MAC address (xx:xx:xx:xx:xx:xx) or UDN string as well as IP.
                identity_from_manual: dict[str, str] = {}
                if _is_mac_address(host):
                    identity_from_manual = {"mac": host.lower()}
                elif host.lower().startswith("uuid:"):
                    identity_from_manual = {"udn": host}
                else:
                    identity_from_manual = {"host": host}

                # When user enters a MAC/UDN (no routable host), set an empty host
                # so the next startup attempts SSDP re-resolution.
                needs_res = _is_mac_address(host) or host.lower().startswith("uuid:")
                device = DiscoveredDevice(
                    identity=identity_from_manual,
                    display_name=host,
                    host="" if needs_res else host,
                    port=port,
                    control_urls={},
                    raw_info={
                        "manual": True,
                        "needs_resolution": needs_res,
                    },
                )
                return await self._create_wifi_entry(spec, device)

        discovery = spec.device.discovery
        self._wifi_matches = {}
        if discovery is not None:
            devices = await WifiDiscovery(discovery, self.hass).discover(
                DEFAULT_SCAN_TIMEOUT
            )
            self._wifi_matches = {
                derive_device_key(device.identity, device.host, device.port): device
                for device in devices
            }

        schema_fields: dict[Any, Any] = {
            vol.Optional(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=_default_wifi_port(spec)): int,
        }
        if self._wifi_matches:
            schema_fields[
                vol.Optional("wifi_device")
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=value,
                            label=f"{device.display_name} ({device.host}:{device.port})",
                        )
                        for value, device in sorted(self._wifi_matches.items())
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        return self.async_show_form(
            step_id="wifi_discovery",
            data_schema=vol.Schema(schema_fields),
            errors={} if self._wifi_matches else {"base": "no_devices_found"},
            description_placeholders={"device_type": self._spec_name},
        )

    async def async_step_cloud_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle cloud-only specs that need OAuth2 before discovery."""
        if user_input is not None:
            return self.async_abort(reason="cloud_auth_not_implemented")
        return self.async_show_form(
            step_id="cloud_auth",
            data_schema=vol.Schema({}),
            errors={"base": "cloud_auth_required"},
            description_placeholders={"device_type": self._spec_name or ""},
        )

    async def async_step_encryption(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect encryption key material for specs that require it."""
        if self._spec_name is None:
            return await self.async_step_user()
        if user_input is not None:
            key = (user_input.get(CONF_AES_ECB_KEY) or "").strip()
            if not key:
                return self.async_show_form(
                    step_id="encryption",
                    data_schema=vol.Schema({vol.Required(CONF_AES_ECB_KEY): str}),
                    errors={"base": "missing_key"},
                )
            self._aes_keys["aes-128-ecb"] = key
            return await self.async_step_scan()

        return self.async_show_form(
            step_id="encryption",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AES_ECB_KEY,
                        default="secrets://shining_mask_key",
                    ): str
                }
            ),
            description_placeholders={"device_type": self._spec_name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return OptionsFlow(config_entry)

    async def _create_wifi_entry(
        self, spec: DeviceSpec, device: DiscoveredDevice
    ) -> FlowResult:
        device_id = derive_device_key(device.identity, device.host, device.port)
        unique_id = f"{DOMAIN}_{self._spec_name}_{device_id}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Normalise to canonical identity keys (udn, serial, mac) only.
        identity = normalize_identity(device.identity)
        needs_resolution = not bool(device.host)

        # Persist the matched variant key (deviceType) for entity filtering.
        variant = (device.raw_info.get("variant") or "").strip() or None

        data: dict[str, Any] = {
            CONF_SPEC_NAME: self._spec_name,
            CONF_HOST: device.host,
            CONF_PORT: device.port,
            CONF_CONTROL_URLS: device.control_urls,
            CONF_WIFI_IDENTITY: identity,
            CONF_WIFI_VARIANT: variant,
            CONF_WIFI_DEVICES: [
                {
                    "device_id": device_id,
                    "host": device.host,
                    "port": device.port,
                    "control_urls": device.control_urls,
                    "identity": identity,
                    "variant": variant,
                }
            ],
        }
        # Include needs_resolution only when True (avoids cruft for normal entries).
        if needs_resolution:
            data[CONF_WIFI_DEVICES][0]["needs_resolution"] = True
        return self.async_create_entry(
            title=f"{spec.device.name} {device.display_name or device_id}",
            data=data,
        )


class OptionsFlow(config_entries.OptionsFlow):
    """Options flow for changing managed devices."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        self._matches: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        specs = await self.hass.async_add_executor_job(load_specs)
        spec = specs.get(self._entry.data[CONF_SPEC_NAME])
        if spec is None:
            return self.async_abort(reason="unknown_spec")
        if spec.device.protocol == Protocol.WIFI:
            return self.async_create_entry(title="", data={})
        self._matches = await _scan_for_matches(self.hass, spec, DEFAULT_SCAN_TIMEOUT)
        choices = {
            address: f"{info.name or spec.device.name} ({address})"
            for address, info in sorted(self._matches.items())
        }
        existing = self._entry.options.get(
            CONF_DEVICE_ADDRESSES, self._entry.data.get(CONF_DEVICE_ADDRESSES, [])
        )
        for address in existing:
            choices.setdefault(address, address)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEVICE_ADDRESSES, default=existing
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=value, label=label)
                                for value, label in choices.items()
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )


async def _scan_for_matches(
    hass: HomeAssistant, spec: DeviceSpec, timeout: int
) -> dict[str, BluetoothServiceInfoBleak]:
    """Collect currently known and newly advertised devices matching a spec."""
    matches: dict[str, BluetoothServiceInfoBleak] = {}
    for service_info in bluetooth.async_discovered_service_info(hass):
        if service_info_matches_spec(service_info, spec):
            matches[service_info.address] = service_info

    event = asyncio.Event()

    @callback
    def _callback(service_info: BluetoothServiceInfoBleak, _change: object) -> None:
        if service_info_matches_spec(service_info, spec):
            matches[service_info.address] = service_info
            event.set()

    unsub = bluetooth.async_register_callback(
        hass,
        _callback,
        {"connectable": True},
        bluetooth.BluetoothScanningMode.ACTIVE,
    )
    try:
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            pass
    finally:
        unsub()
    return matches


def _spec_needs_aes_ecb_key(spec: DeviceSpec) -> bool:
    """Return true when a spec has AES-ECB characteristics without static keys."""
    for service in spec.services:
        for characteristic in service.characteristics:
            encryption = characteristic.encryption or {}
            if (
                encryption.get("algorithm") == "aes-128-ecb"
                and "static_key" not in encryption
            ):
                return True
    return False


def _default_wifi_port(spec: DeviceSpec) -> int:
    discovery = spec.device.discovery
    if discovery:
        for method in discovery.methods:
            if method.port:
                return int(method.port)
            if method.port_fallback:
                return int(method.port_fallback[0])
    if spec.device.identification and spec.device.identification.default_port:
        return int(spec.device.identification.default_port)
    return 80


_MAC_RE = re.compile(
    r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$"
)


def _is_mac_address(value: str) -> bool:
    """Return True when *value* looks like a MAC address."""
    return bool(_MAC_RE.match(value.strip()))


def _spec_is_cloud_only(spec: DeviceSpec) -> bool:
    discovery = spec.device.discovery
    if discovery is None or not discovery.methods:
        return False
    return all(method.type == "cloud" for method in discovery.methods)
