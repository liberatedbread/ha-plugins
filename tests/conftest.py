"""Test fixtures for Liberated Bread."""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.liberated_bread.const import DOMAIN
from custom_components.liberated_bread.spec.models import (
    DeviceInfo,
    DeviceSpec,
    EntityDef,
    ManufacturerStatus,
    Protocol,
)


@pytest.fixture
def config_entry():
    return MockConfigEntry(domain=DOMAIN, data={"spec_name": "Test Device"}, entry_id="entry-1")


@pytest.fixture
def bluetooth_service_info():
    return types.SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Test Device")


@pytest.fixture
def entity_def():
    return EntityDef(
        platform="climate",
        name="Thermostat",
        features=["off", "heat", "cool", "target_temperature"],
        commands={
            "set_hvac_mode": "set_mode",
            "set_temperature": "set_target",
        },
        state_mapping={
            "hvac_mode": "mode",
            "current_temperature": "room",
            "target_temperature": "target",
        },
        unit="°C",
    )


@pytest.fixture
def device_spec(entity_def):
    return DeviceSpec(
        device=DeviceInfo(
            name="Test Device",
            manufacturer="Test Maker",
            manufacturer_status=ManufacturerStatus.ACTIVE,
            protocol=Protocol.BLE,
        ),
        entities=[entity_def],
    )


@pytest.fixture
def ble_manager(device_spec):
    manager = MagicMock()
    manager.devices = {
        "AA:BB": types.SimpleNamespace(
            name="Test Device", spec=device_spec, service_info=object()
        )
    }
    manager.state_for = MagicMock(return_value=None)
    manager.write_command = AsyncMock()
    return manager


@pytest.fixture
def wifi_manager(device_spec):
    manager = MagicMock()
    manager.ready = True
    manager.device_info = {}
    manager.devices = {
        "wifi-id": types.SimpleNamespace(
            device_id="wifi-id",
            name="Test Device",
            spec=device_spec,
            entities=device_spec.entities,
            state={},
        )
    }
    manager.state_for = MagicMock(return_value=None)
    manager.execute_command = AsyncMock(return_value=True)
    manager.request_state = AsyncMock(return_value={})
    return manager
