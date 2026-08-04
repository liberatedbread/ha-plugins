"""Tests for integration setup lifecycle helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.ha

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.liberated_bread.const import (
    CONF_SPEC_NAME,
    CONF_WIFI_DEVICES,
    DATA_MANAGER,
    DATA_SPECS,
    DOMAIN,
)
from custom_components.liberated_bread.spec.models import (
    DeviceInfo,
    DeviceSpec,
    ManufacturerStatus,
    Protocol,
)


def _spec(protocol=Protocol.BLE) -> DeviceSpec:
    return DeviceSpec(
        device=DeviceInfo(
            name="Device",
            manufacturer="Maker",
            manufacturer_status=ManufacturerStatus.ACTIVE,
            protocol=protocol,
        )
    )


@pytest.mark.asyncio
async def test_async_setup_entry_unknown_spec_returns_false(hass, config_entry, monkeypatch) -> None:
    from custom_components.liberated_bread import async_setup_entry

    monkeypatch.setattr("custom_components.liberated_bread.spec.loader.load_specs", lambda: {})
    assert await async_setup_entry(hass, config_entry) is False


@pytest.mark.asyncio
async def test_async_setup_entry_basic_setup(hass, monkeypatch) -> None:
    from custom_components.liberated_bread import async_setup_entry

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_SPEC_NAME: "Device"}, entry_id="entry-1")
    monkeypatch.setattr("custom_components.liberated_bread.spec.loader.load_specs", lambda: {"Device": _spec()})

    # Mock the BLE manager to avoid BluetoothManager init in tests.
    mock_mgr = MagicMock()
    mock_mgr.async_start = AsyncMock()
    monkeypatch.setattr(
        "custom_components.liberated_bread.ble.manager.LiberatedBreadManager",
        lambda *a, **kw: mock_mgr,
    )
    # Mock forward_entry_setups — HA loader can't find integration in test env.
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

    assert await async_setup_entry(hass, entry) is True
    assert DOMAIN in hass.data
    mock_mgr.async_start.assert_awaited_once()
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert isinstance(entry_data[DATA_SPECS], dict) and entry_data[DATA_SPECS]
    assert entry_data[DATA_MANAGER] is mock_mgr
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_unload_entry(hass, config_entry) -> None:
    from custom_components.liberated_bread import async_unload_entry
    from custom_components.liberated_bread.const import DATA_MANAGER

    manager = MagicMock()
    manager.async_stop = AsyncMock()
    hass.data[DOMAIN] = {config_entry.entry_id: {DATA_MANAGER: manager}}
    assert await async_unload_entry(hass, config_entry) is True
    manager.async_stop.assert_awaited_once()
    assert DOMAIN not in hass.data


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2(hass) -> None:
    from custom_components.liberated_bread import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SPEC_NAME: "Device",
            "wifi_devices": [{"device_id": "old", "identity": {"mac": "AA:BB:CC:DD:EE:FF"}, "host": "1.2.3.4", "port": 80}],
        },
        version=1,
    )
    # Register the entry so async_update_entry can find it.
    hass.config_entries._entries[entry.entry_id] = entry
    assert await async_migrate_entry(hass, entry) is True
    # After migration: version bumped to 2, device_id prefixed, unique_id set.
    assert entry.version == 2
    assert entry.unique_id is not None
    assert entry.data[CONF_WIFI_DEVICES][0]["device_id"] != "old"


@pytest.mark.asyncio
async def test_async_setup_entry_wifi(hass, monkeypatch) -> None:
    """Test WiFi protocol path for async_setup_entry."""
    from custom_components.liberated_bread import async_setup_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SPEC_NAME: "WiFiDevice",
            CONF_WIFI_DEVICES: [{"host": "1.2.3.4", "port": 80, "device_id": "wifi-1"}],
        },
        entry_id="wifi-entry",
    )
    spec = _spec(Protocol.WIFI)
    monkeypatch.setattr(
        "custom_components.liberated_bread.spec.loader.load_specs",
        lambda: {"WiFiDevice": spec},
    )

    mock_mgr = MagicMock()
    mock_mgr.async_start = AsyncMock()
    monkeypatch.setattr(
        "custom_components.liberated_bread.wifi.manager.LiberatedBreadWifiManager",
        lambda *a, **kw: mock_mgr,
    )
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

    assert await async_setup_entry(hass, entry) is True
    mock_mgr.async_start.assert_awaited_once()
    entry_data = hass.data[DOMAIN][entry.entry_id]
    assert entry_data[DATA_MANAGER] is mock_mgr
    assert isinstance(entry_data[DATA_SPECS], dict)
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_entry_wifi_matches_manager_signature(hass, monkeypatch) -> None:
    """Setup must call the WiFi manager with kwargs its __init__ accepts.

    Regression guard: async_setup_entry passed identity=/variant_key=/entry=
    to a manager whose __init__ accepted none of them, so every WiFi config
    entry raised TypeError at setup.  test_async_setup_entry_wifi above mocks
    the manager with ``lambda *a, **kw``, which swallows any signature
    mismatch — so bind the call against the real signature here instead.
    """
    import inspect

    from custom_components.liberated_bread import async_setup_entry
    from custom_components.liberated_bread.wifi.manager import LiberatedBreadWifiManager

    real_signature = inspect.signature(LiberatedBreadWifiManager)
    captured: dict = {}

    def _signature_checked(*args, **kwargs):
        # Raises TypeError if setup passes anything __init__ cannot accept.
        real_signature.bind(*args, **kwargs)
        captured.update(kwargs)
        manager = MagicMock()
        manager.async_start = AsyncMock()
        return manager

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SPEC_NAME: "WiFiDevice",
            CONF_WIFI_DEVICES: [{"host": "1.2.3.4", "port": 80, "device_id": "wifi-1"}],
        },
        entry_id="wifi-sig-entry",
    )
    monkeypatch.setattr(
        "custom_components.liberated_bread.spec.loader.load_specs",
        lambda: {"WiFiDevice": _spec(Protocol.WIFI)},
    )
    monkeypatch.setattr(
        "custom_components.liberated_bread.wifi.manager.LiberatedBreadWifiManager",
        _signature_checked,
    )
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

    assert await async_setup_entry(hass, entry) is True
    # The kwargs that were missing from __init__ and broke WiFi setup.
    assert set(captured) >= {"identity", "variant_key", "entry"}


def test_match_device_by_identity() -> None:
    from custom_components.liberated_bread import _match_device_by_identity

    device = type("Device", (), {"identity": {"mac": "AA:BB:CC:DD:EE:FF"}})()
    assert _match_device_by_identity([device], {"mac": "aabbccddeeff"}) is device
    assert _match_device_by_identity([], {"mac": "aabbccddeeff"}) is None


@pytest.mark.asyncio
async def test_async_migrate_entry_noop(hass) -> None:
    """Test that migration with current version returns False."""
    from custom_components.liberated_bread import async_migrate_entry

    entry = MockConfigEntry(domain=DOMAIN, data={}, version=2)
    assert await async_migrate_entry(hass, entry) is False


def test_service_registration(hass) -> None:
    from custom_components.liberated_bread import _async_register_services

    _async_register_services(hass)
    assert hass.services.has_service(DOMAIN, "send_command") is True
