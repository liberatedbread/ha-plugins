"""Light entities for Liberated Bread."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
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
    """Create light entities from spec declarations."""
    if isinstance(manager, LiberatedBreadWifiManager):
        async_add_entities(
            LiberatedBreadWifiLightEntity(manager, entity_def, device_id)
            for device_id, device in manager.devices.items()
            for entity_def in device.spec.entities
            if entity_def.platform == "light"
        )
        return
    entities: list[LiberatedBreadLightEntity] = []
    for address, device in manager.devices.items():
        entities.extend(
            LiberatedBreadLightEntity(address, device.name, device.spec, entity_def, manager)
            for entity_def in device.spec.entities
            if entity_def.platform == "light"
        )
    async_add_entities(entities)


class LiberatedBreadLightEntity(LiberatedBreadEntity, LightEntity):
    """Spec-driven BLE light entity."""

    def __init__(
        self,
        device_address: str,
        device_name: str,
        device_spec: DeviceSpec,
        entity_def: EntityDef,
        manager: LiberatedBreadManager,
    ) -> None:
        super().__init__(device_address, device_name, device_spec, entity_def, manager)
        features = set(entity_def.features)
        if "color" in features:
            self._attr_supported_color_modes = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB
        elif "brightness" in features:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF
        self._local_is_on: bool | None = None
        self._brightness: int | None = None
        self._rgb_color: tuple[int, int, int] | None = None

    @property
    def is_on(self) -> bool | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            return bool(mapped)
        return self._local_is_on

    @property
    def brightness(self) -> int | None:
        return self._brightness

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self._rgb_color

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on or update the light."""
        commands = self._entity_def.commands
        set_brightness = self._resolve_command("set_brightness")
        if ATTR_BRIGHTNESS in kwargs and set_brightness:
            brightness = int(kwargs[ATTR_BRIGHTNESS])
            scaled_brightness = self._scale_brightness(brightness, set_brightness)
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                set_brightness,
                {"brightness": scaled_brightness},
            )
            self._brightness = brightness

        set_color = self._resolve_command("set_color")
        set_foreground_color = self._resolve_command("set_foreground_color")
        if "rgb_color" in kwargs and set_color:
            red, green, blue = kwargs["rgb_color"]
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                set_color,
                {"red": red, "green": green, "blue": blue},
            )
            self._rgb_color = (red, green, blue)
        elif "rgb_color" in kwargs and set_foreground_color:
            red, green, blue = kwargs["rgb_color"]
            await self.coordinator.write_command(
                self._device_address,
                None,
                None,
                set_foreground_color,
                {"red": red, "green": green, "blue": blue, "flag": 1},
            )
            self._rgb_color = (red, green, blue)

        turn_on = self._resolve_command("turn_on")
        set_mode = self._resolve_command("set_mode")
        if turn_on:
            await self.coordinator.write_command(
                self._device_address, None, None, turn_on, {}
            )
        elif set_mode:
            await self.coordinator.write_command(
                self._device_address, None, None, set_mode, {"mode": 1}
            )
        self._local_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light when the spec exposes a suitable command."""
        turn_off = self._resolve_command("turn_off")
        set_mode = self._resolve_command("set_mode")
        if turn_off:
            await self.coordinator.write_command(
                self._device_address, None, None, turn_off, {}
            )
        elif set_mode:
            await self.coordinator.write_command(
                self._device_address, None, None, set_mode, {"mode": 0}
            )
        self._local_is_on = False
        self.async_write_ha_state()

    def _resolve_command(self, key: str) -> str | None:
        mapped = self._entity_def.commands.get(key)
        if mapped:
            return mapped
        _, _, command = self._spec.find_command(key)
        return key if command is not None else None

    def _scale_brightness(self, brightness: int, command_name: str) -> int:
        _, _, command = self._spec.find_command(command_name)
        parameter = _brightness_parameter(command)
        if parameter is None or parameter.min is None or parameter.max is None:
            return brightness
        minimum = int(parameter.min)
        maximum = int(parameter.max)
        return round(minimum + (brightness / 255) * (maximum - minimum))


def _brightness_parameter(command: Command | None):
    if command is None or command.parameters is None:
        return None
    return command.parameters.params.get("brightness")


class LiberatedBreadWifiLightEntity(LiberatedBreadWifiEntity, LightEntity):
    """Spec-driven WiFi light entity."""

    def __init__(
        self,
        manager: LiberatedBreadWifiManager,
        entity_def: EntityDef,
        device_id: str,
    ) -> None:
        super().__init__(manager, entity_def, device_id)
        features = set(entity_def.features)
        if "color" in features:
            self._attr_supported_color_modes = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB
        elif "brightness" in features:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF
        self._local_is_on: bool | None = None
        self._brightness: int | None = None
        self._rgb_color: tuple[int, int, int] | None = None

    @property
    def is_on(self) -> bool | None:
        mapped = self.mapped_state("value")
        if mapped is not None:
            return bool(mapped)
        return self._local_is_on

    @property
    def brightness(self) -> int | None:
        return self._brightness

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self._rgb_color

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on or update the light."""
        if ATTR_BRIGHTNESS in kwargs:
            brightness = int(kwargs[ATTR_BRIGHTNESS])
            await self._manager.execute_command(
                self._entity_def, "set_brightness", brightness=brightness
            )
            self._brightness = brightness
        if "rgb_color" in kwargs:
            red, green, blue = kwargs["rgb_color"]
            await self._manager.execute_command(
                self._entity_def,
                "set_color",
                red=red,
                green=green,
                blue=blue,
            )
            self._rgb_color = (red, green, blue)
        await self._manager.execute_command(self._entity_def, "turn_on")
        self._local_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self._manager.execute_command(self._entity_def, "turn_off")
        self._local_is_on = False
        self.async_write_ha_state()
