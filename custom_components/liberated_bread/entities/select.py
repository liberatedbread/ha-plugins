"""Select entities for Liberated Bread."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Create select entities from spec declarations."""
    if isinstance(manager, LiberatedBreadWifiManager):
        async_add_entities(
            LiberatedBreadWifiSelectEntity(manager, entity_def, device_id)
            for device_id, device in manager.devices.items()
            for entity_def in device.entities
            if entity_def.platform == "select"
        )
        return
    async_add_entities(
        LiberatedBreadSelectEntity(
            address, device.name, device.spec, entity_def, manager
        )
        for address, device in manager.devices.items()
        for entity_def in device.spec.entities
        if entity_def.platform == "select"
    )


class LiberatedBreadSelectEntity(LiberatedBreadEntity, SelectEntity):
    """Spec-driven BLE select entity."""

    def __init__(
        self,
        device_address: str,
        device_name: str,
        device_spec: DeviceSpec,
        entity_def: EntityDef,
        manager: LiberatedBreadManager,
    ) -> None:
        super().__init__(device_address, device_name, device_spec, entity_def, manager)
        self._command_name = entity_def.commands.get("select_option")
        self._param = _resolve_select_parameter(device_spec, self._command_name)
        self._labels = self._param.labels if self._param else []
        self._allowed = self._param.allowed if self._param else []
        self._attr_options = list(self._labels) if self._labels else []
        self._local_option: str | None = None

    @property
    def current_option(self) -> str | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            try:
                idx = self._allowed.index(int(mapped))
                return self._labels[idx]
            except (ValueError, IndexError):
                return str(mapped)
        return self._local_option

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        if self._command_name and self._labels and self._allowed:
            try:
                idx = self._labels.index(option)
                value = self._allowed[idx]
            except ValueError:
                return
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                self._command_name,
                {"value": value},
            )
        self._local_option = option
        self.async_write_ha_state()


class LiberatedBreadWifiSelectEntity(LiberatedBreadWifiEntity, SelectEntity):
    """Spec-driven WiFi select entity."""

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        super().__init__(manager, entity_def, device_id)
        spec = manager.spec if hasattr(manager, "spec") else None
        self._command_name = entity_def.commands.get("select_option")
        self._param = _resolve_select_parameter(spec, self._command_name)
        self._labels = self._param.labels if self._param else []
        self._allowed = self._param.allowed if self._param else []
        self._attr_options = list(self._labels) if self._labels else []
        self._local_option: str | None = None

    @property
    def current_option(self) -> str | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            try:
                idx = self._allowed.index(int(mapped))
                return self._labels[idx]
            except (ValueError, IndexError):
                return str(mapped)
        return self._local_option

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        if self._command_name and self._labels and self._allowed:
            try:
                idx = self._labels.index(option)
                value = self._allowed[idx]
            except ValueError:
                return
            await self._manager.execute_command(
                self._entity_def, "select_option", value=value
            )
        self._local_option = option
        self.async_write_ha_state()


def _resolve_select_parameter(spec, command_name):
    if spec is None or command_name is None:
        return None
    _, _, command = spec.find_command(command_name)
    if command is None or command.parameters is None:
        return None
    return command.parameters.params.get("value")
