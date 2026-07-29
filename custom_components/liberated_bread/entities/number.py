"""Number entities for Liberated Bread."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..ble.manager import LiberatedBreadManager
from ..spec.models import Command, DeviceSpec, EntityDef
from ..wifi.manager import LiberatedBreadWifiManager
from .base import LiberatedBreadEntity
from .wifi_base import LiberatedBreadWifiEntity


async def async_setup_entry_entities(
    manager: LiberatedBreadManager | LiberatedBreadWifiManager,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create number entities from spec declarations."""
    if isinstance(manager, LiberatedBreadWifiManager):
        async_add_entities(
            LiberatedBreadWifiNumberEntity(manager, entity_def, device_id)
            for device_id, device in manager.devices.items()
            for entity_def in device.entities
            if entity_def.platform == "number"
        )
        return
    async_add_entities(
        LiberatedBreadNumberEntity(
            address, device.name, device.spec, entity_def, manager
        )
        for address, device in manager.devices.items()
        for entity_def in device.spec.entities
        if entity_def.platform == "number"
    )


class LiberatedBreadNumberEntity(LiberatedBreadEntity, NumberEntity):
    """Spec-driven BLE number entity."""

    def __init__(
        self,
        device_address: str,
        device_name: str,
        device_spec: DeviceSpec,
        entity_def: EntityDef,
        manager: LiberatedBreadManager,
    ) -> None:
        super().__init__(device_address, device_name, device_spec, entity_def, manager)
        self._command_name = entity_def.commands.get("set_value")
        self._param = _resolve_number_parameter(device_spec, self._command_name)
        self._local_value: float | None = None

        if self._param and self._param.allowed:
            self._attr_native_min_value = float(min(self._param.allowed))
            self._attr_native_max_value = float(max(self._param.allowed))
            self._attr_native_step = _compute_step(self._param.allowed)
        elif self._param:
            self._attr_native_min_value = float(self._param.min or 0)
            self._attr_native_max_value = float(self._param.max or 100)
            self._attr_native_step = 1.0

    @property
    def native_value(self) -> float | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            try:
                return float(mapped)
            except (TypeError, ValueError):
                pass
        return self._local_value

    async def async_set_native_value(self, value: float) -> None:
        """Set a new value for the number entity."""
        if self._command_name:
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                self._command_name,
                {"value": int(value)},
            )
        self._local_value = value
        self.async_write_ha_state()


class LiberatedBreadWifiNumberEntity(LiberatedBreadWifiEntity, NumberEntity):
    """Spec-driven WiFi number entity."""

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        super().__init__(manager, entity_def, device_id)
        spec = manager.spec if hasattr(manager, "spec") else None
        self._command_name = entity_def.commands.get("set_value")
        self._param = _resolve_number_parameter(spec, self._command_name)
        self._local_value: float | None = None

        if self._param and self._param.allowed:
            self._attr_native_min_value = float(min(self._param.allowed))
            self._attr_native_max_value = float(max(self._param.allowed))
            self._attr_native_step = _compute_step(self._param.allowed)
        elif self._param:
            self._attr_native_min_value = float(self._param.min or 0)
            self._attr_native_max_value = float(self._param.max or 100)
            self._attr_native_step = 1.0

    @property
    def native_value(self) -> float | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            try:
                return float(mapped)
            except (TypeError, ValueError):
                pass
        return self._local_value

    async def async_set_native_value(self, value: float) -> None:
        """Set a new value for the number entity."""
        if self._command_name:
            await self._manager.execute_command(
                self._entity_def, "set_value", value=int(value)
            )
        self._local_value = value
        self.async_write_ha_state()


def _resolve_number_parameter(spec, command_name):
    if spec is None or command_name is None:
        return None
    _, _, command = spec.find_command(command_name)
    if command is None or command.parameters is None:
        return None
    return command.parameters.params.get("value")


def _compute_step(allowed_values):
    if len(allowed_values) < 2:
        return 1.0
    diffs = sorted(set(
        abs(allowed_values[i + 1] - allowed_values[i])
        for i in range(len(allowed_values) - 1)
    ))
    return float(diffs[0]) if diffs else 1.0
