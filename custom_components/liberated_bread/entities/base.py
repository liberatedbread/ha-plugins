"""Base Home Assistant entity for Liberated Bread devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..ble.manager import LiberatedBreadManager
from ..const import DOMAIN
from ..spec.models import DeviceSpec, EntityDef


class LiberatedBreadEntity(CoordinatorEntity[LiberatedBreadManager], Entity):
    """Base entity for OpenGreenIoT devices."""

    _attr_has_entity_name = True

    def __init__(
        self,
        device_address: str,
        device_name: str,
        device_spec: DeviceSpec,
        entity_def: EntityDef,
        manager: LiberatedBreadManager,
    ) -> None:
        super().__init__(manager)
        self._device_address = device_address
        self._device_name = device_name
        self._spec = device_spec
        self._entity_def = entity_def
        slug = entity_def.name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{device_address}_{slug}"
        self._attr_name = entity_def.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_address)},
            name=device_name,
            manufacturer=device_spec.device.manufacturer,
            model=device_spec.device.name,
        )

    @property
    def available(self) -> bool:
        device = self.coordinator.devices.get(self._device_address)
        return device is not None and device.service_info is not None

    def mapped_state(self, key: str = "value") -> object:
        """Return a decoded mapped state value for this entity."""
        return self.coordinator.state_for(self._device_address, self._entity_def.name, key)
