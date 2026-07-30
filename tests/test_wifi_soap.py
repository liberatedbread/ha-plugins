"""Tests for the Wemo/UPnP SOAP transport.

Covers envelope construction, Wemo's pipe-delimited response quirks, the
manager's SOAP routing/caching, and the rediscover-and-retry wrapper.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.liberated_bread.spec.models import (
    DeviceInfo,
    DeviceSpec,
    EntityDef,
    ManufacturerStatus,
    Protocol,
)
from custom_components.liberated_bread.wifi.discovery import _variant_matches_targets
from custom_components.liberated_bread.wifi.manager import (
    LiberatedBreadWifiManager,
    _resolve_variant_entities,
    _spec_uses_soap,
)
from custom_components.liberated_bread.wifi.soap_client import (
    SoapClient,
    _build_soap_envelope,
    _parse_binary_state,
    _parse_insight_params,
)

BASICEVENT = "urn:Belkin:service:basicevent:1"
INSIGHT = "urn:Belkin:service:insight:1"


def _wemo_spec(*, transport: str = "upnp", variants=None) -> DeviceSpec:
    return DeviceSpec(
        device=DeviceInfo(
            name="Belkin Wemo Smart Devices",
            manufacturer="Belkin",
            manufacturer_status=ManufacturerStatus.ACTIVE,
            protocol=Protocol.WIFI,
            transport=transport,
            variants=variants,
        ),
        entities=[EntityDef(platform="switch", name="Relay")],
    )


# --- Envelope construction ---------------------------------------------------


def test_build_soap_envelope_declares_namespace_and_args() -> None:
    xml = _build_soap_envelope(BASICEVENT, "SetBinaryState", {"BinaryState": 1})
    assert xml.startswith('<?xml version="1.0" encoding="utf-8"?>')
    assert 'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"' in xml
    assert f'<u:SetBinaryState xmlns:u="{BASICEVENT}">' in xml
    assert "<BinaryState>1</BinaryState>" in xml
    assert xml.rstrip().endswith("</s:Envelope>")


def test_build_soap_envelope_with_no_args_is_self_contained() -> None:
    xml = _build_soap_envelope(BASICEVENT, "GetBinaryState", {})
    assert "GetBinaryState" in xml
    assert "<s:Body>" in xml


# --- Wemo response parsing ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", 1), ("0", 0), ("", 0)],
)
def test_parse_binary_state_plain(raw: str, expected: int) -> None:
    assert _parse_binary_state(raw)["value"] == expected


def test_parse_binary_state_pipe_delimited_keeps_extras() -> None:
    parsed = _parse_binary_state("1|1678492800|120")
    assert parsed["value"] == 1
    assert parsed["extra"] == ["1678492800", "120"]
    assert parsed["raw"] == "1|1678492800|120"


def test_parse_binary_state_tolerates_garbage() -> None:
    # Wemo can return "error" while the relay is mid-transition; treat as off
    # rather than raising into the HA update loop.
    assert _parse_binary_state("error")["value"] == 0


def test_parse_insight_params_labels_fields() -> None:
    parsed = _parse_insight_params("1|1678|60|120|999|1200|-45|18500|100|200|8000")
    assert parsed["state"] == 1
    assert parsed["currentpower_mw"] == 18500
    assert parsed["wifipower"] == -45


def test_parse_insight_params_short_response_pads_with_none() -> None:
    parsed = _parse_insight_params("1|1678")
    assert parsed["state"] == 1
    assert parsed["currentpower_mw"] is None


# --- SoapClient over a mocked session ---------------------------------------


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    async def text(self) -> str:
        return self._text


def _client_returning(body: str) -> tuple[SoapClient, MagicMock]:
    session = MagicMock()
    session.post = MagicMock(return_value=_FakeResponse(body))
    client = SoapClient(
        "192.0.2.10",
        49153,
        hass=MagicMock(),
        control_urls={BASICEVENT: "http://192.0.2.10:49153/upnp/control/basicevent1"},
        session=session,
    )
    return client, session


def _envelope(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<s:Body>{inner}</s:Body></s:Envelope>"
    )


@pytest.mark.asyncio
async def test_get_binary_state_parses_response() -> None:
    client, session = _client_returning(
        _envelope(
            f'<u:GetBinaryStateResponse xmlns:u="{BASICEVENT}">'
            "<BinaryState>1</BinaryState></u:GetBinaryStateResponse>"
        )
    )
    assert (await client.get_binary_state())["value"] == 1
    # SOAPACTION header is required by Wemo firmware.
    headers = session.post.call_args.kwargs["headers"]
    assert headers["SOAPACTION"] == f'"{BASICEVENT}#GetBinaryState"'


@pytest.mark.asyncio
async def test_set_binary_state_sends_value_and_brightness() -> None:
    client, session = _client_returning(_envelope("<u:SetBinaryStateResponse/>"))
    assert await client.set_binary_state(1, brightness=60) is True
    body = session.post.call_args.kwargs["data"]
    assert "<BinaryState>1</BinaryState>" in body
    assert "<brightness>60</brightness>" in body


@pytest.mark.asyncio
async def test_call_action_rejects_unknown_service() -> None:
    client, _ = _client_returning(_envelope(""))
    with pytest.raises(ValueError, match="No control URL"):
        await client.call_action("urn:Belkin:service:insight:1", "GetInsightParams")


# --- Transport selection -----------------------------------------------------


def test_spec_uses_soap_via_transport() -> None:
    assert _spec_uses_soap(_wemo_spec(), {}) is True


def test_spec_uses_soap_via_control_url_urns() -> None:
    spec = _wemo_spec(transport="")
    assert _spec_uses_soap(spec, {BASICEVENT: "http://x/y"}) is True


def test_spec_does_not_use_soap_for_plain_http() -> None:
    spec = _wemo_spec(transport="")
    assert _spec_uses_soap(spec, {"status": "http://x/status"}) is False


# --- Variant entity resolution ----------------------------------------------


def _variants() -> list[dict]:
    return [
        {
            "identification": {"device_type": "urn:Belkin:device:controllee:1"},
            "entities": [{"platform": "switch", "name": "Relay"}],
        },
        {
            "identification": {"device_type": "urn:Belkin:device:insight:1"},
            "entities": [
                {"platform": "switch", "name": "Relay"},
                {"platform": "sensor", "name": "Current Power"},
            ],
        },
    ]


def test_resolve_variant_entities_picks_matching_variant() -> None:
    spec = _wemo_spec(variants=_variants())
    entities = _resolve_variant_entities(spec, "urn:Belkin:device:insight:1")
    assert [e.name for e in entities] == ["Relay", "Current Power"]


def test_resolve_variant_entities_falls_back_when_unmatched() -> None:
    spec = _wemo_spec(variants=_variants())
    entities = _resolve_variant_entities(spec, "urn:Belkin:device:unknown:9")
    assert [e.name for e in entities] == ["Relay"]


def test_resolve_variant_entities_without_variant_key() -> None:
    spec = _wemo_spec(variants=_variants())
    assert [e.name for e in _resolve_variant_entities(spec, None)] == ["Relay"]


# --- SSDP target filtering ---------------------------------------------------


def test_variant_matches_targets_exact_and_prefix() -> None:
    targets = ["urn:Belkin:device:controllee:1"]
    assert _variant_matches_targets("urn:Belkin:device:controllee:1", targets) is True
    assert _variant_matches_targets("URN:BELKIN:DEVICE:CONTROLLEE:1", targets) is True


def test_variant_matches_targets_rejects_foreign_device() -> None:
    targets = ["urn:Belkin:device:controllee:1"]
    assert _variant_matches_targets("urn:schemas-upnp-org:device:Basic:1", targets) is False


def test_variant_matches_targets_empty_inputs() -> None:
    assert _variant_matches_targets("", ["urn:x"]) is False
    assert _variant_matches_targets("urn:x", []) is False


# --- Manager SOAP routing / caching / retry ---------------------------------


def _manager(spec: DeviceSpec) -> LiberatedBreadWifiManager:
    """Build a manager without touching HA's real aiohttp session factory."""
    with (
        patch(
            "custom_components.liberated_bread.wifi.soap_client.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.liberated_bread.wifi.http_client.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        return LiberatedBreadWifiManager(
            hass=MagicMock(),
            spec=spec,
            device_id="wemo-1",
            host="192.0.2.10",
            port=49153,
            control_urls={
                BASICEVENT: "http://192.0.2.10:49153/upnp/control/basicevent1"
            },
        )


@pytest.mark.asyncio
async def test_manager_routes_state_to_soap_and_caches() -> None:
    manager = _manager(_wemo_spec())
    manager.soap = MagicMock()
    manager.soap.get_binary_state = AsyncMock(return_value={"value": 1})
    entity = EntityDef(
        platform="switch",
        name="Relay",
        state_topic="GetBinaryState",
        extensions={"soap_service": BASICEVENT, "soap_action": "GetBinaryState"},
    )

    assert (await manager._request_soap_state(entity))["value"] == 1
    # Second read within the TTL is served from cache, not a second SOAP call.
    await manager._request_soap_state(entity)
    assert manager.soap.get_binary_state.await_count == 1


@pytest.mark.asyncio
async def test_manager_command_invalidates_soap_cache() -> None:
    manager = _manager(_wemo_spec())
    manager.soap = MagicMock()
    manager.soap.get_binary_state = AsyncMock(return_value={"value": 0})
    manager.soap.set_binary_state = AsyncMock(return_value=True)
    entity = EntityDef(
        platform="switch",
        name="Relay",
        state_topic="GetBinaryState",
        extensions={"soap_service": BASICEVENT, "soap_action": "GetBinaryState"},
    )

    await manager._request_soap_state(entity)
    await manager._execute_soap_command(entity, "SetBinaryState", {"value": 1})
    # The cache was cleared, so the next poll hits the device again.
    await manager._request_soap_state(entity)
    assert manager.soap.get_binary_state.await_count == 2


@pytest.mark.asyncio
async def test_manager_defaults_to_basicevent_service() -> None:
    manager = _manager(_wemo_spec())
    manager.soap = MagicMock()
    manager.soap.call_action = AsyncMock(return_value="<xml/>")
    entity = EntityDef(
        platform="switch", name="Relay", extensions={"soap_action": "GetHomeInfo"}
    )

    await manager._request_soap_state(entity)
    assert manager.soap.call_action.await_args.args[0] == BASICEVENT


@pytest.mark.asyncio
async def test_with_rediscovery_retries_after_successful_reresolution() -> None:
    manager = _manager(_wemo_spec())
    manager.rediscover = AsyncMock(return_value=True)
    action = AsyncMock(side_effect=[OSError("host moved"), "ok"])

    assert await manager._with_rediscovery(action, "Request") == "ok"
    assert action.await_count == 2


@pytest.mark.asyncio
async def test_with_rediscovery_raises_when_reresolution_fails() -> None:
    manager = _manager(_wemo_spec())
    manager.rediscover = AsyncMock(return_value=False)
    action = AsyncMock(side_effect=OSError("host moved"))

    with pytest.raises(OSError):
        await manager._with_rediscovery(action, "Request")
    # No retry when the device could not be re-resolved.
    assert action.await_count == 1
    assert manager._available is False
    assert manager._last_error


@pytest.mark.asyncio
async def test_with_rediscovery_respects_cooldown() -> None:
    manager = _manager(_wemo_spec())
    manager.rediscover = AsyncMock(return_value=True)
    # Simulate a rediscovery that just happened.
    import time

    manager._last_rediscovery = time.monotonic()
    action = AsyncMock(side_effect=OSError("still down"))

    with pytest.raises(OSError):
        await manager._with_rediscovery(action, "Request")
    manager.rediscover.assert_not_awaited()


def test_wifi_device_entities_prefers_variant_entities() -> None:
    dev = _manager(_wemo_spec()).devices["wemo-1"]
    # No variant match yet, so the flat spec entity list is used.
    assert [e.name for e in dev.entities] == ["Relay"]

    dev.variant_entities = [EntityDef(platform="sensor", name="Current Power")]
    assert [e.name for e in dev.entities] == ["Current Power"]
