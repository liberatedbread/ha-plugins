"""Sensor entities for Liberated Bread."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
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
    """Create sensor entities from spec declarations."""
    if isinstance(manager, LiberatedBreadWifiManager):
        async_add_entities(
            LiberatedBreadWifiSensorEntity(manager, entity_def, device_id)
            for device_id, device in manager.devices.items()
            for entity_def in device.spec.entities
            if entity_def.platform == "sensor"
        )
        return
    async_add_entities(
        LiberatedBreadSensorEntity(address, device.name, device.spec, entity_def, manager)
        for address, device in manager.devices.items()
        for entity_def in device.spec.entities
        if entity_def.platform == "sensor"
    )


class LiberatedBreadSensorEntity(LiberatedBreadEntity, SensorEntity):
    """Spec-driven BLE sensor entity."""

    def __init__(
        self,
        device_address: str,
        device_name: str,
        device_spec: DeviceSpec,
        entity_def: EntityDef,
        manager: LiberatedBreadManager,
    ) -> None:
        super().__init__(device_address, device_name, device_spec, entity_def, manager)
        if entity_def.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(entity_def.device_class)
            except ValueError:
                self._attr_device_class = entity_def.device_class
        self._attr_native_unit_of_measurement = _normalize_unit(entity_def.unit)

    @property
    def native_value(self) -> object:
        return self.mapped_state("value")


class LiberatedBreadWifiSensorEntity(LiberatedBreadWifiEntity, SensorEntity):
    """Spec-driven WiFi sensor entity."""

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        super().__init__(manager, entity_def, device_id)
        if entity_def.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(entity_def.device_class)
            except ValueError:
                self._attr_device_class = entity_def.device_class
        self._attr_native_unit_of_measurement = _normalize_unit(entity_def.unit)

    @property
    def native_value(self) -> object:
        return self.mapped_state("value")


def _normalize_unit(unit: str | None) -> str | None:
    if unit in {"C", "°C"}:
        return UnitOfTemperature.CELSIUS
    if unit in {"F", "°F"}:
        return UnitOfTemperature.FAHRENHEIT
    return unit
