"""Liberated Bread Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Liberated Bread from a config entry."""
    from .ble.manager import LiberatedBreadManager
    from .const import (
        CONF_AES_KEYS,
        CONF_CONTROL_URLS,
        CONF_DEVICE_ADDRESSES,
        CONF_HOST,
        CONF_PORT,
        CONF_SPEC_NAME,
        CONF_WIFI_DEVICES,
        DATA_MANAGER,
        DATA_SPECS,
        DOMAIN,
        PLATFORMS,
    )
    from .spec.loader import load_specs
    from .spec.models import Protocol
    from .wifi.manager import LiberatedBreadWifiManager

    specs = await hass.async_add_executor_job(load_specs)
    spec_name = entry.data.get(CONF_SPEC_NAME)
    spec = specs.get(spec_name)
    if spec is not None and spec.device.protocol == Protocol.WIFI:
        wifi_devices = entry.data.get(CONF_WIFI_DEVICES) or []
        device_data = wifi_devices[0] if wifi_devices else {}
        host = device_data.get("host") or entry.data.get(CONF_HOST)
        if not host:
            return False
        port = int(device_data.get("port") or entry.data.get(CONF_PORT) or 80)
        device_id = device_data.get("device_id") or f"{host}_{port}"
        control_urls = dict(
            device_data.get("control_urls") or entry.data.get(CONF_CONTROL_URLS, {})
        )
        manager = LiberatedBreadWifiManager(
            hass,
            spec,
            str(device_id),
            str(host),
            port,
            control_urls,
        )
    else:
        selected = set(
            entry.options.get(
                CONF_DEVICE_ADDRESSES, entry.data.get(CONF_DEVICE_ADDRESSES, [])
            )
        )
        manager = LiberatedBreadManager(
            hass,
            specs,
            selected,
            spec_name,
            dict(entry.data.get(CONF_AES_KEYS, {})),
        )
    await manager.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_MANAGER: manager,
        DATA_SPECS: specs,
    }
    _async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .const import DATA_MANAGER, DOMAIN, PLATFORMS

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        await data[DATA_MANAGER].async_stop()
    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level command services once."""
    import voluptuous as vol

    from .const import (
        CHARACTERISTIC_UUID_KEY,
        DATA_MANAGER,
        DOMAIN,
        SERVICE_UUID_KEY,
    )

    if hass.services.has_service(DOMAIN, "send_command"):
        return

    async def _send_command(call) -> None:
        data: dict[str, Any] = dict(call.data)
        entry_id = data.pop("entry_id", None)
        managers = hass.data.get(DOMAIN, {})
        if entry_id:
            manager = managers[entry_id][DATA_MANAGER]
        else:
            manager = next(iter(managers.values()))[DATA_MANAGER]
        params = data.get("params") or {}
        if hasattr(manager, "write_command"):
            await manager.write_command(
                data["device_address"],
                data.get(SERVICE_UUID_KEY),
                data.get(CHARACTERISTIC_UUID_KEY),
                data["command"],
                params,
            )
        else:
            raise ValueError("send_command service is only supported for BLE entries")

    hass.services.async_register(
        DOMAIN,
        "send_command",
        _send_command,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): str,
                vol.Required("device_address"): str,
                vol.Optional(SERVICE_UUID_KEY): str,
                vol.Optional(CHARACTERISTIC_UUID_KEY): str,
                vol.Required("command"): str,
                vol.Optional("params", default={}): dict,
            }
        ),
    )
