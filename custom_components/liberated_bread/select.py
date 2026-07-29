"""Home Assistant select platform for Liberated Bread."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_MANAGER, DOMAIN
from .entities.select import async_setup_entry_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Liberated Bread select entities."""
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not data:
        return
    manager = data[DATA_MANAGER]
    await async_setup_entry_entities(manager, async_add_entities)
