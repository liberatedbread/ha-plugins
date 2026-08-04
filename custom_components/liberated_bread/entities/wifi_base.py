"""Base WiFi Home Assistant entity for Liberated Bread devices."""

from __future__ import annotations

import logging

from homeassistant.helpers.entity import Entity

from ..const import DOMAIN
from ..spec.models import EntityDef
from ..wifi.manager import LiberatedBreadWifiManager

_LOGGER = logging.getLogger(__name__)


class LiberatedBreadWifiEntity(Entity):
    """Base entity for WiFi devices - no DataUpdateCoordinator."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        self._manager = manager
        self._entity_def = entity_def
        self._device_id = device_id
        slug = entity_def.name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{slug}"
        self._attr_name = entity_def.name
        self._attr_device_info = manager.device_info
        self._state: dict[str, object] = {}
        self._available = manager.ready

    @property
    def available(self) -> bool:
        return self._available and self._manager.ready

    async def async_update(self) -> None:
        """Poll state from WiFi device."""
        # Poll when there is a state_topic (HTTP) OR SOAP extensions (SOAP).
        has_soap = bool(self._entity_def.extensions.get("soap_action"))
        if (self._entity_def.state_topic and not self._entity_def.state_characteristic) or has_soap:
            try:
                state = await self._manager.request_state(
                    self._device_id, self._entity_def
                )
            except Exception as err:  # noqa: BLE001 - HA update should not crash.
                self._available = False
                self._manager.mark_unavailable(err)
                _LOGGER.debug(
                    "Failed to update WiFi entity %s: %s",
                    self._attr_unique_id,
                    err,
                )
                return
            self._available = True
            self._state = state if isinstance(state, dict) else {"value": state}

    def mapped_state(self, key: str = "value") -> object:
        """Return the last mapped state value for this entity."""
        if key in self._state:
            return self._state[key]
        return self._manager.state_for(self._entity_def.name, key)
