"""Binary sensor entities for Liberated Bread."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Create binary sensor entities from spec declarations."""
    if isinstance(manager, LiberatedBreadWifiManager):
        async_add_entities(
            LiberatedBreadWifiBinarySensorEntity(manager, entity_def, device_id)
            for device_id, device in manager.devices.items()
            for entity_def in device.entities
            if entity_def.platform == "binary_sensor"
        )
        return
    async_add_entities(
        LiberatedBreadBinarySensorEntity(
            address, device.name, device.spec, entity_def, manager
        )
        for address, device in manager.devices.items()
        for entity_def in device.spec.entities
        if entity_def.platform == "binary_sensor"
    )


class LiberatedBreadBinarySensorEntity(LiberatedBreadEntity, BinarySensorEntity):
    """Spec-driven BLE binary sensor entity."""

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
                self._attr_device_class = BinarySensorDeviceClass(entity_def.device_class)
            except ValueError:
                self._attr_device_class = entity_def.device_class

    @property
    def is_on(self) -> bool | None:
        value = self.mapped_state("value")
        return None if value is None else bool(value)


class LiberatedBreadWifiBinarySensorEntity(
    LiberatedBreadWifiEntity, BinarySensorEntity
):
    """Spec-driven WiFi binary sensor entity."""

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        super().__init__(manager, entity_def, device_id)
        if entity_def.device_class:
            try:
                self._attr_device_class = BinarySensorDeviceClass(entity_def.device_class)
            except ValueError:
                self._attr_device_class = entity_def.device_class

    @property
    def is_on(self) -> bool | None:
        value = self.mapped_state("value")
        return None if value is None else bool(value)
