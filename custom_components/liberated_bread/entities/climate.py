"""Climate entities for Liberated Bread."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..ble.manager import LiberatedBreadManager
from ..spec.models import DeviceSpec, EntityDef
from ..wifi.manager import LiberatedBreadWifiManager
from .base import LiberatedBreadEntity
from .wifi_base import LiberatedBreadWifiEntity

_DEFAULT_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.COOL,
    HVACMode.FAN_ONLY,
]

_ALL_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.HEAT_COOL,
    HVACMode.AUTO,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
]
_HVAC_MODE_VALUES = {str(mode.value): mode for mode in _ALL_HVAC_MODES}


async def async_setup_entry_entities(
    manager: LiberatedBreadManager | LiberatedBreadWifiManager,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create climate entities from spec declarations."""
    if isinstance(manager, LiberatedBreadWifiManager):
        async_add_entities(
            LiberatedBreadWifiClimateEntity(manager, entity_def, device_id)
            for device_id, device in manager.devices.items()
            for entity_def in device.entities
            if entity_def.platform == "climate"
        )
        return
    async_add_entities(
        LiberatedBreadClimateEntity(
            address, device.name, device.spec, entity_def, manager
        )
        for address, device in manager.devices.items()
        for entity_def in device.spec.entities
        if entity_def.platform == "climate"
    )


class LiberatedBreadClimateEntity(LiberatedBreadEntity, ClimateEntity):
    """Spec-driven BLE climate entity."""

    def __init__(
        self,
        device_address: str,
        device_name: str,
        device_spec: DeviceSpec,
        entity_def: EntityDef,
        manager: LiberatedBreadManager,
    ) -> None:
        super().__init__(device_address, device_name, device_spec, entity_def, manager)
        self._attr_hvac_modes = _resolve_hvac_modes(entity_def)
        self._attr_supported_features = _supported_features(entity_def)
        self._attr_fan_modes = _resolve_fan_modes(entity_def)
        self._local_hvac_mode: HVACMode | str | None = None
        self._local_target_temperature: float | None = None
        self._local_fan_mode: str | None = None

    @property
    def hvac_mode(self) -> HVACMode | str | None:
        mapped = self.mapped_state("hvac_mode")
        if mapped is not None:
            return _normalize_hvac_mode(mapped)
        return self._local_hvac_mode

    @property
    def current_temperature(self) -> float | None:
        return _coerce_float(self.mapped_state("current_temperature"))

    @property
    def target_temperature(self) -> float | None:
        mapped = _coerce_float(self.mapped_state("target_temperature"))
        if mapped is not None:
            return mapped
        return self._local_target_temperature

    @property
    def fan_mode(self) -> str | None:
        mapped = self.mapped_state("fan_mode")
        if mapped is not None:
            return str(mapped)
        return self._local_fan_mode

    @property
    def min_temp(self) -> float:
        return _coerce_float(self._entity_def.extensions.get("min_temp")) or 7.0

    @property
    def max_temp(self) -> float:
        return _coerce_float(self._entity_def.extensions.get("max_temp")) or 35.0

    @property
    def target_temperature_step(self) -> float:
        return (
            _coerce_float(self._entity_def.extensions.get("target_temperature_step"))
            or 0.5
        )

    @property
    def temperature_unit(self) -> str:
        return _normalize_temperature_unit(self._entity_def.unit)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode | str) -> None:
        """Set the active HVAC mode."""
        normalized = _normalize_hvac_mode(hvac_mode)
        command = self._entity_def.commands.get("set_hvac_mode")
        if command:
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                command,
                {"mode": str(normalized)},
            )
        elif normalized == HVACMode.OFF and self._entity_def.commands.get("turn_off"):
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                self._entity_def.commands["turn_off"],
                {},
            )
        elif normalized != HVACMode.OFF and self._entity_def.commands.get("turn_on"):
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                self._entity_def.commands["turn_on"],
                {},
            )
        self._local_hvac_mode = normalized
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return
        temperature = float(kwargs[ATTR_TEMPERATURE])
        command = self._entity_def.commands.get("set_temperature")
        if command:
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                command,
                {"temperature": temperature},
            )
        self._local_target_temperature = temperature
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        command = self._entity_def.commands.get("set_fan_mode")
        if command:
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                command,
                {"fan_mode": fan_mode},
            )
        self._local_fan_mode = fan_mode
        self.async_write_ha_state()


class LiberatedBreadWifiClimateEntity(LiberatedBreadWifiEntity, ClimateEntity):
    """Spec-driven WiFi climate entity."""

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        super().__init__(manager, entity_def, device_id)
        self._attr_hvac_modes = _resolve_hvac_modes(entity_def)
        self._attr_supported_features = _supported_features(entity_def)
        self._attr_fan_modes = _resolve_fan_modes(entity_def)
        self._local_hvac_mode: HVACMode | str | None = None
        self._local_target_temperature: float | None = None
        self._local_fan_mode: str | None = None

    @property
    def hvac_mode(self) -> HVACMode | str | None:
        mapped = self.mapped_state("hvac_mode")
        if mapped is not None:
            return _normalize_hvac_mode(mapped)
        return self._local_hvac_mode

    @property
    def current_temperature(self) -> float | None:
        return _coerce_float(self.mapped_state("current_temperature"))

    @property
    def target_temperature(self) -> float | None:
        mapped = _coerce_float(self.mapped_state("target_temperature"))
        if mapped is not None:
            return mapped
        return self._local_target_temperature

    @property
    def fan_mode(self) -> str | None:
        mapped = self.mapped_state("fan_mode")
        if mapped is not None:
            return str(mapped)
        return self._local_fan_mode

    @property
    def min_temp(self) -> float:
        return _coerce_float(self._entity_def.extensions.get("min_temp")) or 7.0

    @property
    def max_temp(self) -> float:
        return _coerce_float(self._entity_def.extensions.get("max_temp")) or 35.0

    @property
    def target_temperature_step(self) -> float:
        return (
            _coerce_float(self._entity_def.extensions.get("target_temperature_step"))
            or 0.5
        )

    @property
    def temperature_unit(self) -> str:
        return _normalize_temperature_unit(self._entity_def.unit)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode | str) -> None:
        """Set the active HVAC mode."""
        normalized = _normalize_hvac_mode(hvac_mode)
        if self._entity_def.commands.get("set_hvac_mode"):
            await self._manager.execute_command(
                self._entity_def, "set_hvac_mode", mode=str(normalized)
            )
        elif normalized == HVACMode.OFF and self._entity_def.commands.get("turn_off"):
            await self._manager.execute_command(self._entity_def, "turn_off")
        elif normalized != HVACMode.OFF and self._entity_def.commands.get("turn_on"):
            await self._manager.execute_command(self._entity_def, "turn_on")
        self._local_hvac_mode = normalized
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return
        temperature = float(kwargs[ATTR_TEMPERATURE])
        if self._entity_def.commands.get("set_temperature"):
            await self._manager.execute_command(
                self._entity_def, "set_temperature", temperature=temperature
            )
        self._local_target_temperature = temperature
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        if self._entity_def.commands.get("set_fan_mode"):
            await self._manager.execute_command(
                self._entity_def, "set_fan_mode", fan_mode=fan_mode
            )
        self._local_fan_mode = fan_mode
        self.async_write_ha_state()


def _resolve_hvac_modes(entity_def: EntityDef) -> list[HVACMode | str]:
    configured = entity_def.extensions.get("hvac_modes")
    raw_modes = configured if isinstance(configured, list) else entity_def.features
    modes = [_normalize_hvac_mode(mode) for mode in raw_modes if _is_hvac_mode(mode)]
    if modes:
        return modes
    return list(_DEFAULT_HVAC_MODES)


def _resolve_fan_modes(entity_def: EntityDef) -> list[str] | None:
    configured = entity_def.extensions.get("fan_modes")
    if isinstance(configured, list):
        return [str(m) for m in configured]
    return None


def _is_hvac_mode(value: object) -> bool:
    return str(value) in _HVAC_MODE_VALUES


def _normalize_hvac_mode(value: object) -> HVACMode | str:
    return _HVAC_MODE_VALUES.get(str(value), str(value))


def _supported_features(entity_def: EntityDef) -> ClimateEntityFeature:
    supported = ClimateEntityFeature(0)
    if (
        "target_temperature" in entity_def.features
        or "set_temperature" in entity_def.commands
        or "target_temperature" in entity_def.state_mapping
    ):
        supported |= ClimateEntityFeature.TARGET_TEMPERATURE
    if (
        "fan_mode" in entity_def.features
        or "set_fan_mode" in entity_def.commands
        or "fan_mode" in entity_def.state_mapping
    ):
        supported |= ClimateEntityFeature.FAN_MODE
    if "turn_on" in entity_def.commands and "turn_off" in entity_def.commands:
        supported |= ClimateEntityFeature.TURN_ON
        supported |= ClimateEntityFeature.TURN_OFF
    return supported


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_temperature_unit(unit: str | None) -> str:
    if unit in {"F", "°F"}:
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS
