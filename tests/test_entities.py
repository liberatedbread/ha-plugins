"""Tests for Home Assistant entity classes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.ha

from custom_components.liberated_bread.const import DOMAIN
from custom_components.liberated_bread.entities.climate import (
    LiberatedBreadClimateEntity,
    LiberatedBreadWifiClimateEntity,
)
from custom_components.liberated_bread.entities.light import LiberatedBreadLightEntity
from custom_components.liberated_bread.entities.sensor import LiberatedBreadSensorEntity
from custom_components.liberated_bread.entities.switch import LiberatedBreadSwitchEntity
from custom_components.liberated_bread.entities.wifi_base import LiberatedBreadWifiEntity
from custom_components.liberated_bread.spec.models import EntityDef


def _bind_entity(entity, hass):
    """Bind an entity to the HA instance so async_write_ha_state works."""
    entity.hass = hass
    entity.entity_id = f"test.{entity.name.lower().replace(' ', '_')}"
    if not hasattr(entity, "registry_entry"):
        entity.registry_entry = None


def test_switch_entity_is_on_and_turns_on_off(device_spec, ble_manager) -> None:
    entity_def = EntityDef(platform="switch", name="Power", commands={"turn_on": "on", "turn_off": "off"})
    entity = LiberatedBreadSwitchEntity("AA:BB", "Device", device_spec, entity_def, ble_manager)
    ble_manager.state_for.return_value = 1
    assert entity.is_on is True


@pytest.mark.asyncio
async def test_switch_entity_turn_on_off_dispatches(device_spec, ble_manager, hass) -> None:
    entity_def = EntityDef(platform="switch", name="Power", commands={"turn_on": "on", "turn_off": "off"})
    entity = LiberatedBreadSwitchEntity("AA:BB", "Device", device_spec, entity_def, ble_manager)
    _bind_entity(entity, hass)
    await entity.async_turn_on()
    await entity.async_turn_off()
    assert ble_manager.write_command.await_args_list[0].args[3] == "on"
    assert ble_manager.write_command.await_args_list[1].args[3] == "off"
    assert entity.is_on is False


def test_sensor_entity_native_value(device_spec, ble_manager) -> None:
    entity_def = EntityDef(platform="sensor", name="Temperature", unit="°C")
    entity = LiberatedBreadSensorEntity("AA:BB", "Device", device_spec, entity_def, ble_manager)
    ble_manager.state_for.return_value = 21
    assert entity.native_value == 21


@pytest.mark.asyncio
async def test_light_entity_turn_on_brightness_color_and_off(device_spec, ble_manager, hass) -> None:
    entity_def = EntityDef(
        platform="light",
        name="Lamp",
        features=["brightness", "color"],
        commands={"turn_on": "turn_on", "turn_off": "turn_off", "set_brightness": "set_brightness", "set_color": "set_color"},
    )
    device_spec.find_command = MagicMock(return_value=(None, None, None))
    entity = LiberatedBreadLightEntity("AA:BB", "Device", device_spec, entity_def, ble_manager)
    _bind_entity(entity, hass)
    await entity.async_turn_on(brightness=128, rgb_color=(1, 2, 3))
    await entity.async_turn_off()
    commands = [call.args[3] for call in ble_manager.write_command.await_args_list]
    assert commands == ["set_brightness", "set_color", "turn_on", "turn_off"]
    assert entity.brightness == 128
    assert entity.rgb_color == (1, 2, 3)
    assert entity.is_on is False


@pytest.mark.asyncio
async def test_climate_entity_state_and_commands(device_spec, entity_def, ble_manager, hass) -> None:
    values = {
        ("Thermostat", "hvac_mode"): "heat",
        ("Thermostat", "current_temperature"): 20.5,
        ("Thermostat", "target_temperature"): 22,
    }
    ble_manager.state_for.side_effect = lambda _addr, name, key: values.get((name, key))
    entity = LiberatedBreadClimateEntity("AA:BB", "Device", device_spec, entity_def, ble_manager)
    _bind_entity(entity, hass)
    assert str(entity.hvac_mode) == "heat"
    assert entity.current_temperature == 20.5
    assert entity.target_temperature == 22

    await entity.async_set_hvac_mode("cool")
    await entity.async_set_temperature(temperature=18)

    assert ble_manager.write_command.await_args_list[0].args[3] == "set_mode"
    assert ble_manager.write_command.await_args_list[0].args[4]["mode"] == "cool"
    assert ble_manager.write_command.await_args_list[1].args[3] == "set_target"
    assert ble_manager.write_command.await_args_list[1].args[4]["temperature"] == 18


@pytest.mark.asyncio
async def test_wifi_climate_entity_commands(entity_def, wifi_manager, hass) -> None:
    entity = LiberatedBreadWifiClimateEntity(wifi_manager, entity_def, "wifi-id")
    _bind_entity(entity, hass)
    await entity.async_set_hvac_mode("heat")
    await entity.async_set_temperature(temperature=19.5)
    assert wifi_manager.execute_command.await_args_list[0].args[:2] == (entity_def, "set_hvac_mode")
    assert wifi_manager.execute_command.await_args_list[1].args[:2] == (entity_def, "set_temperature")


@pytest.mark.asyncio
async def test_wifi_entity_base_update_and_unique_id(entity_def, wifi_manager) -> None:
    entity = LiberatedBreadWifiEntity(wifi_manager, entity_def, "wifi-id")
    assert entity._attr_unique_id == f"{DOMAIN}_wifi-id_thermostat"
    entity_def.state_topic = "/state"
    wifi_manager.request_state = AsyncMock(return_value={"value": 1})
    await entity.async_update()
    assert entity.mapped_state("value") == 1
