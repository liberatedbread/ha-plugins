"""WiFi manager for Liberated Bread devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import TYPE_CHECKING, Any

try:
    from homeassistant.helpers.device_registry import DeviceInfo as HADeviceInfo
except ModuleNotFoundError:  # pragma: no cover - standalone import outside HA.
    HADeviceInfo = dict

from ..const import (
    CONF_CONTROL_URLS,
    CONF_HOST,
    CONF_PORT,
    CONF_WIFI_DEVICES,
    CONF_WIFI_IDENTITY,
    DOMAIN,
)
from ..spec.models import DeviceSpec, EntityDef, HttpEndpoint
from .http_client import LiberatedBreadHttpClient
from .identity import identity_matches

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_REDISCOVERY_COOLDOWN = 300  # seconds before another SSDP re-resolution attempt.


@dataclass
class LiberatedBreadWifiDevice:
    """A configured WiFi device and its cached state."""

    device_id: str
    name: str
    spec: DeviceSpec
    host: str
    port: int
    control_urls: dict[str, str] = field(default_factory=dict)
    state: dict[str, dict[str, Any]] = field(default_factory=dict)


class LiberatedBreadWifiManager:
    """Manages WiFi device connections and state polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        spec: DeviceSpec,
        device_id: str,
        host: str,
        port: int,
        control_urls: dict[str, str],
        identity: dict[str, str] | None = None,
        entry: ConfigEntry | None = None,
    ) -> None:
        self.hass = hass
        self.spec = spec
        self.device_id = device_id
        self.port = port
        self.control_urls = control_urls
        self._identity: dict[str, str] = dict(identity or {})
        self._entry: ConfigEntry | None = entry
        self.client = LiberatedBreadHttpClient(host, port, hass)
        self.host = self.client.host
        self.devices = {
            device_id: LiberatedBreadWifiDevice(
                device_id,
                spec.device.name,
                spec,
                host,
                port,
                control_urls,
            )
        }
        self._ready = False
        self._available = False
        self._last_success: datetime | None = None
        self._last_error: str | None = None
        self._last_rediscovery: float = 0.0

    async def async_start(self) -> None:
        """Start the WiFi manager."""
        self._ready = True
        self._available = True
        self._last_rediscovery = 0.0

    async def async_stop(self) -> None:
        """Stop the WiFi manager."""
        self._ready = False
        self._available = False

    @property
    def device_info(self) -> HADeviceInfo:
        return self.device_info_for(self.device_id)

    def device_info_for(self, device_id: str) -> HADeviceInfo:
        """Return Home Assistant device info for a managed WiFi device."""
        return HADeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=self.spec.device.name,
            manufacturer=self.spec.device.manufacturer,
            model=self.spec.device.name,
            configuration_url=f"{self._scheme}://{self.host}:{self.port}",
        )

    @property
    def ready(self) -> bool:
        return self._ready and self._available

    @property
    def _scheme(self) -> str:
        return "https" if self.client.use_ssl else "http"

    @property
    def last_success(self) -> datetime | None:
        """Return the last successful HTTP request timestamp."""
        return self._last_success

    @property
    def last_error(self) -> str | None:
        """Return the last WiFi request error."""
        return self._last_error

    async def request_state(
        self, device_id_or_entity: str | EntityDef, entity: EntityDef | None = None
    ) -> Any:
        """Read state for a spec entity and update the local state cache."""
        device_id = (
            self.device_id if isinstance(device_id_or_entity, EntityDef) else device_id_or_entity
        )
        entity = device_id_or_entity if isinstance(device_id_or_entity, EntityDef) else entity
        if entity is None:
            return None
        try:
            endpoint = self._endpoint_for_state(entity, device_id)
            if endpoint is not None:
                raw = await self.client.request(endpoint, **self._path_params(device_id))
            else:
                raw = await self._request_state_fallback(entity, device_id)
            mapped = self._map_state(entity, raw)
            self.devices[device_id].state[entity.name] = mapped
            self._mark_success()
            return mapped
        except Exception as err:
            if self._can_attempt_rediscovery():
                self._last_rediscovery = time.monotonic()
                _LOGGER.debug(
                    "Request failed for %s; attempting rediscovery", self.device_id
                )
                if await self.rediscover():
                    try:
                        if endpoint is not None:
                            raw = await self.client.request(
                                endpoint, **self._path_params(device_id)
                            )
                        else:
                            raw = await self._request_state_fallback(
                                entity, device_id
                            )
                        mapped = self._map_state(entity, raw)
                        self.devices[device_id].state[entity.name] = mapped
                        self._mark_success()
                        return mapped
                    except Exception as retry_err:
                        self._mark_failure(retry_err)
                        raise
            self._mark_failure(err)
            raise

    async def execute_command(
        self, entity: EntityDef, command_name: str, **params: Any
    ) -> bool:
        """Execute a command for a spec entity."""
        command = entity.commands.get(command_name, command_name)
        endpoint = self._endpoint_for_command(command)
        try:
            if endpoint is None:
                await self.client.send_command(entity, command, **params)
            else:
                await self.client.request(
                    endpoint, **self._path_params(self.device_id), payload=params
                )
            self._mark_success()
            return True
        except Exception as err:
            if self._can_attempt_rediscovery():
                self._last_rediscovery = time.monotonic()
                _LOGGER.debug(
                    "Command failed for %s; attempting rediscovery",
                    self.device_id,
                )
                if await self.rediscover():
                    try:
                        if endpoint is None:
                            await self.client.send_command(
                                entity, command, **params
                            )
                        else:
                            await self.client.request(
                                endpoint,
                                **self._path_params(self.device_id),
                                payload=params,
                            )
                        self._mark_success()
                        return True
                    except Exception as retry_err:
                        self._mark_failure(retry_err)
                        raise
            self._mark_failure(err)
            raise

    async def write_command(
        self,
        device_id: str,
        service_uuid: str | None,
        char_uuid: str | None,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Protocol-compatible command entry point."""
        entity = self._entity_for_command(command)
        if entity is None:
            raise ValueError(f"unknown command: {command}")
        await self.execute_command(entity, command, **(params or {}))

    def state_for(
        self, device_id_or_entity_name: str, entity_name_or_key: str, key: str | None = None
    ) -> Any:
        """Return a cached mapped state value."""
        if key is None:
            device_id = self.device_id
            entity_name = device_id_or_entity_name
            state_key = entity_name_or_key
        else:
            device_id = device_id_or_entity_name
            entity_name = entity_name_or_key
            state_key = key
        device = self.devices.get(device_id)
        if device is None:
            return None
        return device.state.get(entity_name, {}).get(state_key)

    def _endpoint_for_state(self, entity: EntityDef, device_id: str | None = None):
        if not entity.state_topic:
            return None
        state_path = entity.state_topic.format(device_id=device_id or self.device_id)
        normalized_state_path = _normalize_path(state_path)
        entity_name = _normalize_name(entity.name)
        for endpoint in self.spec.http_endpoints:
            endpoint_name = _normalize_name(endpoint.name)
            endpoint_path = _normalize_path(endpoint.path)
            if endpoint.name == entity.state_topic or endpoint.path == state_path:
                return endpoint
            if endpoint_path == normalized_state_path:
                return endpoint
            if endpoint_name == entity_name:
                return endpoint
            if "state" in entity_name and "state" in endpoint_name:
                return endpoint
        return None

    async def _request_state_fallback(self, entity: EntityDef, device_id: str) -> Any:
        if not entity.state_topic:
            return None
        if _looks_like_relative_state_topic(entity.state_topic):
            _LOGGER.debug(
                "No HTTP endpoint maps state topic %s for entity %s",
                entity.state_topic,
                entity.name,
            )
            return self.devices[device_id].state.get(entity.name, {})
        return await self.client.request(
            HttpEndpoint(
                method="GET",
                path=entity.state_topic.format(device_id=device_id),
                name=entity.name,
            )
        )

    def _endpoint_for_command(self, command: str):
        for endpoint in self.spec.http_endpoints:
            if endpoint.name == command or endpoint.path == command:
                return endpoint
        return None

    def _entity_for_command(self, command: str) -> EntityDef | None:
        for entity in self.spec.entities:
            if command in entity.commands.values() or command in entity.commands:
                return entity
        return None

    def _map_state(self, entity: EntityDef, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {"value": raw}
        if not entity.state_mapping:
            return dict(raw)
        mapped = {
            target: raw.get(source)
            for target, source in entity.state_mapping.items()
            if source in raw
        }
        if not mapped and "value" in raw:
            mapped["value"] = raw["value"]
        return mapped

    def _path_params(self, device_id: str) -> dict[str, str]:
        return {
            "device_id": device_id,
            "applianceId": device_id,
        }

    def _mark_success(self) -> None:
        self._available = True
        self._last_success = datetime.now(timezone.utc)
        self._last_error = None
        self._last_rediscovery = 0.0

    def _mark_failure(self, err: Exception) -> None:
        self._available = False
        self._last_error = str(err)

    def mark_unavailable(self, err: Exception) -> None:
        """Mark this WiFi device unavailable after an entity-level failure."""
        self._mark_failure(err)

    def _can_attempt_rediscovery(self) -> bool:
        """Return True when enough time has passed since the last rediscovery attempt."""
        return (time.monotonic() - self._last_rediscovery) >= _REDISCOVERY_COOLDOWN

    async def rediscover(self) -> bool:
        """Attempt SSDP re-resolution using stored identity keys.

        Returns True if a new host:port was found and applied.
        """
        if not self._identity:
            _LOGGER.debug("No identity keys stored; cannot rediscover %s", self.device_id)
            return False
        discovery = self.spec.device.discovery
        if discovery is None:
            _LOGGER.debug("No discovery config for %s; cannot rediscover", self.device_id)
            return False
        try:
            from .discovery import WifiDiscovery

            found = await WifiDiscovery(discovery, self.hass).discover(timeout=15)
        except Exception:
            _LOGGER.warning(
                "SSDP re-resolution failed for %s", self.device_id, exc_info=True
            )
            return False

        matched = self._match_identity(found)
        if matched is None:
            _LOGGER.debug(
                "Rediscovery could not match identity %s for %s",
                self._identity,
                self.device_id,
            )
            return False

        new_host = matched.host
        new_port = int(matched.port)
        if new_host == self.host and new_port == self.port:
            _LOGGER.debug(
                "Rediscovery for %s found same host:port %s:%s",
                self.device_id,
                new_host,
                new_port,
            )
            return False

        _LOGGER.info(
            "Rediscovered %s at %s:%s (was %s:%s)",
            self.device_id,
            new_host,
            new_port,
            self.host,
            self.port,
        )
        self.host = new_host
        self.port = new_port
        self.client = LiberatedBreadHttpClient(new_host, new_port, self.hass)
        self.control_urls = dict(matched.control_urls)
        device = self.devices.get(self.device_id)
        if device is not None:
            device.host = new_host
            device.port = new_port
            device.control_urls = dict(matched.control_urls)
        self._available = True
        self._last_error = None

        # Persist the new host:port to the config entry so the next restart
        # uses the resolved address without re-discovering.
        if self._entry is not None:
            new_data = dict(self._entry.data)
            new_data[CONF_HOST] = new_host
            new_data[CONF_PORT] = new_port
            new_data[CONF_CONTROL_URLS] = dict(matched.control_urls)
            new_identity = dict(self._identity)
            for key in ("udn", "serial", "mac"):
                if key in matched.identity and key not in new_identity:
                    new_identity[key] = str(matched.identity[key])
            new_data[CONF_WIFI_IDENTITY] = new_identity
            # Update the wifi_devices list too.
            wifi_devices = new_data.get(CONF_WIFI_DEVICES) or []
            if wifi_devices:
                wifi_devices[0] = {
                    **wifi_devices[0],
                    "host": new_host,
                    "port": new_port,
                    "control_urls": matched.control_urls,
                    "needs_resolution": False,
                }
                new_data[CONF_WIFI_DEVICES] = wifi_devices
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)

        return True

    def _match_identity(self, devices: list[Any]) -> Any | None:
        """Match a list of discovered devices against stored identity.

        Uses canonical keys (udn, serial, mac) with normalization so that
        ``94:10:3e:aa:bb:cc`` matches ``94103EAABBCC`` and case differences
        in UDN/serial values are handled correctly.
        """
        if not devices:
            return None
        for device in devices:
            dev_identity: dict[str, str] = getattr(device, "identity", {})
            if identity_matches(self._identity, dev_identity):
                return device
        return None


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _normalize_path(value: str) -> str:
    return value.strip("/")


def _looks_like_relative_state_topic(value: str) -> bool:
    return not value.startswith(("/", "http://", "https://"))
