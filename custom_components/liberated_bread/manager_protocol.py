"""Shared manager protocol for Liberated Bread transports."""

from __future__ import annotations

from typing import Any, Protocol

try:
    from homeassistant.helpers.device_registry import DeviceInfo as HADeviceInfo
except ModuleNotFoundError:  # pragma: no cover - standalone import outside HA.
    HADeviceInfo = dict

from .spec.models import EntityDef


class LiberatedBreadManagerProtocol(Protocol):
    """Common runtime surface implemented by BLE and WiFi managers."""

    async def async_start(self) -> None:
        """Start manager resources."""

    async def async_stop(self) -> None:
        """Stop manager resources."""

    def device_info_for(self, device_id: str) -> HADeviceInfo:
        """Return Home Assistant device info for one managed device."""

    def state_for(self, device_id: str, entity_name: str, key: str) -> Any:
        """Return cached entity state."""

    async def request_state(self, device_id: str, entity: EntityDef) -> Any:
        """Refresh entity state when the transport supports polling."""

    async def write_command(
        self,
        device_id: str,
        service_uuid: str | None,
        char_uuid: str | None,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Execute a transport command."""
