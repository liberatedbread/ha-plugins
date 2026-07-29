"""Tests for config flow helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.ha

from custom_components.liberated_bread.const import (
    CONF_AES_ECB_KEY,
    CONF_DEVICE_ADDRESSES,
    CONF_HOST,
    CONF_WIFI_DEVICES,
)
from custom_components.liberated_bread.config_flow import (
    LiberatedBreadConfigFlow,
    _default_wifi_port,
    _is_mac_address,
    _spec_needs_aes_ecb_key,
)
from custom_components.liberated_bread.spec.models import (
    Characteristic,
    CharacteristicProperty,
    DeviceInfo,
    DeviceSpec,
    Discovery,
    DiscoveryMethod,
    ManufacturerStatus,
    Protocol,
    Service,
)


def _spec(protocol=Protocol.BLE, discovery=None, encryption=None) -> DeviceSpec:
    return DeviceSpec(
        device=DeviceInfo(
            name="Device",
            manufacturer="Maker",
            manufacturer_status=ManufacturerStatus.ACTIVE,
            protocol=protocol,
            discovery=discovery,
        ),
        services=[
            Service(
                uuid="svc",
                name="svc",
                characteristics=[
                    Characteristic(
                        uuid="char",
                        name="char",
                        properties=[CharacteristicProperty.WRITE],
                        encryption=encryption,
                    )
                ],
            )
        ],
    )


async def _executor_result(result):
    return result


@pytest.mark.asyncio
async def test_user_step_with_empty_specs_aborts(hass, monkeypatch) -> None:
    flow = LiberatedBreadConfigFlow()
    flow.hass = hass
    flow.context = {}
    monkeypatch.setattr("custom_components.liberated_bread.config_flow.load_specs", lambda: {})
    result = await flow.async_step_user()
    assert result["type"] == "abort"
    assert result["reason"] == "no_specs"


@pytest.mark.asyncio
async def test_user_step_with_valid_specs_shows_form(hass, monkeypatch) -> None:
    flow = LiberatedBreadConfigFlow()
    flow.hass = hass
    flow.context = {}
    monkeypatch.setattr("custom_components.liberated_bread.config_flow.load_specs", lambda: {"Device": _spec()})
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_scan_step_with_no_matches(hass, monkeypatch) -> None:
    flow = LiberatedBreadConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._spec_name = "Device"
    flow._specs = {"Device": _spec()}
    monkeypatch.setattr(
        "custom_components.liberated_bread.config_flow._scan_for_matches",
        AsyncMock(return_value={}),
    )
    result = await flow.async_step_scan()
    assert result["type"] == "form"
    assert result["step_id"] == "scan"
    assert result["errors"] == {"base": "no_devices_found"}


@pytest.mark.asyncio
async def test_scan_step_with_matched_devices_and_selection(hass, monkeypatch) -> None:
    flow = LiberatedBreadConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._spec_name = "Device"
    flow._specs = {"Device": _spec()}
    monkeypatch.setattr(
        "custom_components.liberated_bread.config_flow._scan_for_matches",
        AsyncMock(return_value={"AA:BB": type("Info", (), {"name": "Device"})()}),
    )
    form = await flow.async_step_scan()
    assert form["type"] == "form"
    entry = await flow.async_step_scan({CONF_DEVICE_ADDRESSES: ["AA:BB"]})
    assert entry["type"] == "create_entry"
    assert entry["data"][CONF_DEVICE_ADDRESSES] == ["AA:BB"]


@pytest.mark.asyncio
async def test_wifi_discovery_manual_host_entry(hass) -> None:
    flow = LiberatedBreadConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._spec_name = "Device"
    flow._specs = {"Device": _spec(protocol=Protocol.WIFI)}
    result = await flow.async_step_wifi_discovery({CONF_HOST: "192.0.2.10"})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_WIFI_DEVICES][0]["host"] == "192.0.2.10"


@pytest.mark.asyncio
async def test_wifi_discovery_mac_manual_entry_sets_resolution(hass) -> None:
    flow = LiberatedBreadConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._spec_name = "Device"
    flow._specs = {"Device": _spec(protocol=Protocol.WIFI)}
    result = await flow.async_step_wifi_discovery({CONF_HOST: "AA:BB:CC:DD:EE:FF"})
    device = result["data"][CONF_WIFI_DEVICES][0]
    assert device["host"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_encryption_step_collects_key_and_continues_to_scan(hass, monkeypatch) -> None:
    flow = LiberatedBreadConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._spec_name = "Device"
    monkeypatch.setattr(flow, "async_step_scan", AsyncMock(return_value={"type": "form", "step_id": "scan"}))
    result = await flow.async_step_encryption({CONF_AES_ECB_KEY: "00112233445566778899aabbccddeeff"})
    assert result["step_id"] == "scan"
    assert flow._aes_keys["aes-128-ecb"] == "00112233445566778899aabbccddeeff"


def test_wifi_helpers() -> None:
    discovery = Discovery(methods=[DiscoveryMethod(type="ssdp", port_fallback=[49153])])
    assert _default_wifi_port(_spec(protocol=Protocol.WIFI, discovery=discovery)) == 49153
    assert _is_mac_address("aa:bb:cc:dd:ee:ff") is True
    assert _is_mac_address("not-a-mac") is False


def test_spec_needs_aes_ecb_key_helper() -> None:
    assert _spec_needs_aes_ecb_key(_spec(encryption={"algorithm": "aes-128-ecb"})) is True
    assert _spec_needs_aes_ecb_key(_spec(encryption={"algorithm": "aes-128-ecb", "static_key": "x"})) is False
    assert _spec_needs_aes_ecb_key(_spec()) is False
