"""Liberated Bread Home Assistant integration."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

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
        CONF_WIFI_IDENTITY,
        CONF_WIFI_VARIANT,
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
    if spec is None:
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.error("Unknown spec %s for config entry %s", spec_name, entry.entry_id)
        return False

    if spec.device.protocol == Protocol.WIFI:
        import logging

        _LOGGER = logging.getLogger(__name__)

        wifi_devices = entry.data.get(CONF_WIFI_DEVICES) or []
        device_data = wifi_devices[0] if wifi_devices else {}
        host = device_data.get("host") or entry.data.get(CONF_HOST)
        resolved = False  # True when SSDP re-resolution succeeded this startup.

        if not host:
            # Try SSDP re-resolution using stored identity before giving up.
            from .wifi.identity import normalize_identity

            wifi_identity_raw: dict[str, str] = dict(
                device_data.get("identity")
                or entry.data.get(CONF_WIFI_IDENTITY, {})
            )
            if wifi_identity_raw and spec.device.discovery is not None:
                from .wifi.discovery import WifiDiscovery

                _LOGGER.debug(
                    "No host for %s; attempting SSDP re-resolution with identity %s",
                    spec_name,
                    wifi_identity_raw,
                )
                try:
                    found = await WifiDiscovery(spec.device.discovery, hass).discover(
                        timeout=15
                    )
                except Exception:
                    found = []
                    _LOGGER.warning(
                        "SSDP re-resolution failed for %s", spec_name, exc_info=True
                    )
                matched = _match_device_by_identity(found, wifi_identity_raw)
                if matched:
                    host = matched.host
                    port = int(matched.port)
                    control_urls = matched.control_urls
                    wifi_identity = normalize_identity(matched.identity)
                    wifi_variant = (matched.raw_info.get("variant") or "").strip() or None
                    resolved = True
                    _LOGGER.info(
                        "Re-resolved %s to %s:%s", spec_name, host, port
                    )
                    # Persist the resolved host:port so next restart is fast.
                    # IMPORTANT: device_id is IMMUTABLE after entry creation to
                    # avoid orphaning existing entity unique_ids.
                    device_id = device_data.get("device_id") or f"{host}_{port}"
                    new_data = dict(entry.data)
                    new_data[CONF_HOST] = host
                    new_data[CONF_PORT] = port
                    if control_urls:
                        new_data[CONF_CONTROL_URLS] = control_urls
                    if wifi_identity:
                        new_data[CONF_WIFI_IDENTITY] = wifi_identity
                    if wifi_variant:
                        new_data[CONF_WIFI_VARIANT] = wifi_variant
                    new_wifi_devices = [
                        {
                            **device_data,
                            "host": host,
                            "port": port,
                            "device_id": device_id,
                            "control_urls": control_urls,
                            "identity": wifi_identity,
                            "variant": wifi_variant or device_data.get("variant"),
                            "needs_resolution": False,
                        }
                    ]
                    new_data[CONF_WIFI_DEVICES] = new_wifi_devices
                    hass.config_entries.async_update_entry(entry, data=new_data)
                else:
                    _LOGGER.warning(
                        "SSDP re-resolution could not match identity for %s",
                        spec_name,
                    )
                    from homeassistant.exceptions import ConfigEntryNotReady
                    raise ConfigEntryNotReady(
                        f"Could not resolve host for {spec_name}"
                    )
            else:
                from homeassistant.exceptions import ConfigEntryNotReady
                raise ConfigEntryNotReady(
                    f"No identity or discovery config for {spec_name}"
                )

        if not resolved:
            # Use data from the config entry as-is (no re-resolution happened).
            port = int(device_data.get("port") or entry.data.get(CONF_PORT) or 80)
            device_id = device_data.get("device_id") or f"{host}_{port}"
            control_urls = dict(
                device_data.get("control_urls") or entry.data.get(CONF_CONTROL_URLS, {})
            )
            wifi_identity = dict(
                device_data.get("identity")
                or entry.data.get(CONF_WIFI_IDENTITY, {})
            )
            wifi_variant = entry.data.get(CONF_WIFI_VARIANT) or device_data.get("variant")

        manager = LiberatedBreadWifiManager(
            hass,
            spec,
            str(device_id),
            str(host),
            port,
            control_urls,
            identity=wifi_identity,
            variant_key=wifi_variant if resolved else (entry.data.get(CONF_WIFI_VARIANT) or device_data.get("variant")),
            entry=entry,
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the latest version.

    HA calls this MODULE-LEVEL function (not the config_flow method)
    before async_setup_entry when the entry version is stale.
    """
    from .const import CONF_SPEC_NAME, CONF_WIFI_DEVICES, DOMAIN
    from .wifi.discovery import DiscoveredDevice
    from .wifi.identity import derive_device_key

    if entry.version == 1:
        # V1→V2: device_id prefix and identity format changed.
        wifi_devices = entry.data.get(CONF_WIFI_DEVICES) or []
        if wifi_devices:
            old_id = wifi_devices[0].get("device_id", "")
            identity = wifi_devices[0].get("identity") or {}
            try:
                fake_device = DiscoveredDevice(
                    identity=identity,
                    display_name="",
                    host=wifi_devices[0].get("host", ""),
                    port=int(wifi_devices[0].get("port", 80)),
                    control_urls={},
                )
                new_id = derive_device_key(
                    fake_device.identity, fake_device.host, fake_device.port
                )
            except Exception:
                new_id = old_id

            new_data = dict(entry.data)
            new_data[CONF_WIFI_DEVICES] = [
                {**wifi_devices[0], "device_id": new_id}
            ]

            # Construct the new unique_id so duplicates are detected.
            spec_name = entry.data.get(CONF_SPEC_NAME, "")
            new_unique_id = f"{DOMAIN}_{spec_name}_{new_id}"

            hass.config_entries.async_update_entry(
                entry, data=new_data, unique_id=new_unique_id, version=2
            )
        else:
            hass.config_entries.async_update_entry(entry, version=2)
        return True
    return False


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _match_device_by_identity(
    devices: list[object], identity: dict[str, str]
) -> object | None:
    """Match a discovered device against stored identity using canonical keys."""
    from .wifi.identity import identity_matches

    if not devices or not identity:
        return None

    for device in devices:
        dev_identity: dict[str, str] = getattr(device, "identity", {})
        if identity_matches(identity, dev_identity):
            return device
    return None


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
