"""Switch entities for Liberated Bread."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..ble.manager import LiberatedBreadManager
from ..spec.models import DeviceSpec, EntityDef
from ..wifi.manager import LiberatedBreadWifiManager
from .base import LiberatedBreadEntity
from .wifi_base import LiberatedBreadWifiEntity


async def async_setup_entry_entities(
    manager: LiberatedBreadManager | LiberatedBreadWifiManager,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create switch entities from spec declarations."""
    if isinstance(manager, LiberatedBreadWifiManager):
        async_add_entities(
            LiberatedBreadWifiSwitchEntity(manager, entity_def, device_id)
            for device_id, device in manager.devices.items()
            for entity_def in device.spec.entities
            if entity_def.platform == "switch"
        )
        return
    async_add_entities(
        LiberatedBreadSwitchEntity(address, device.name, device.spec, entity_def, manager)
        for address, device in manager.devices.items()
        for entity_def in device.spec.entities
        if entity_def.platform == "switch"
    )


class LiberatedBreadSwitchEntity(LiberatedBreadEntity, SwitchEntity):
    """Spec-driven BLE switch entity."""

    def __init__(
        self,
        device_address: str,
        device_name: str,
        device_spec: DeviceSpec,
        entity_def: EntityDef,
        manager: LiberatedBreadManager,
    ) -> None:
        super().__init__(device_address, device_name, device_spec, entity_def, manager)
        self._local_is_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            return bool(mapped)
        return self._local_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        command = self._entity_def.commands.get("turn_on")
        if command:
            await self.coordinator.write_command(
                self._device_address, None, None, command, {"value": 1, "enabled": 1}
            )
        self._local_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        command = self._entity_def.commands.get("turn_off")
        if command:
            await self.coordinator.write_command(
                self._device_address, None, None, command, {"value": 0, "enabled": 0}
            )
        self._local_is_on = False
        self.async_write_ha_state()


class LiberatedBreadWifiSwitchEntity(LiberatedBreadWifiEntity, SwitchEntity):
    """Spec-driven WiFi switch entity."""

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        super().__init__(manager, entity_def, device_id)
        self._local_is_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            return bool(mapped)
        return self._local_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._manager.execute_command(
            self._entity_def, "turn_on", value=1, enabled=1
        )
        self._local_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._manager.execute_command(
            self._entity_def, "turn_off", value=0, enabled=0
        )
        self._local_is_on = False
        self.async_write_ha_state()
