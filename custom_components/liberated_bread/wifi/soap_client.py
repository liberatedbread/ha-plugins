"""SOAP client for Wemo and other UPnP Wi-Fi devices.

Builds SOAP XML envelopes, sets SOAPACTION headers, parses responses.
Handles Wemo-specific quirks like pipe-delimited BinaryState values.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

import aiohttp

try:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
except ModuleNotFoundError:  # pragma: no cover - standalone import outside HA.
    def async_get_clientsession(_: object) -> aiohttp.ClientSession:
        return aiohttp.ClientSession()

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_BASICEVENT_SERVICE = "urn:Belkin:service:basicevent:1"
_INSIGHT_SERVICE = "urn:Belkin:service:insight:1"
_DEVICEEVENT_SERVICE = "urn:Belkin:service:deviceevent:1"


class SoapClient:
    """SOAP-over-HTTP client for Wemo and compatible UPnP devices."""

    def __init__(
        self,
        host: str,
        port: int,
        hass: HomeAssistant,
        control_urls: dict[str, str],
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.hass = hass
        self.control_urls = control_urls
        self.session = session or async_get_clientsession(hass)

    # -- SOAP action primitives -------------------------------------------------

    async def call_action(
        self,
        service_type: str,
        action_name: str,
        args: dict[str, Any] | None = None,
    ) -> str:
        """Send a SOAP action and return the raw XML response text."""
        url = self.control_urls.get(service_type)
        if url is None:
            raise ValueError(
                f"No control URL for service {service_type}; "
                f"available: {list(self.control_urls)}"
            )
        envelope = _build_soap_envelope(service_type, action_name, args or {})
        headers = {
            "SOAPACTION": f'"{service_type}#{action_name}"',
            "Content-Type": 'text/xml; charset="utf-8"',
        }
        try:
            async with self.session.post(
                url,
                data=envelope,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                return await response.text()
        except (aiohttp.ClientError, TimeoutError) as err:  # noqa: B904
            raise RuntimeError(
                f"SOAP {service_type}#{action_name} failed: {err}"
            ) from err

    async def call_action_parsed(
        self,
        service_type: str,
        action_name: str,
        args: dict[str, Any] | None = None,
    ) -> ElementTree.Element:
        """Send a SOAP action and return the parsed XML response body."""
        raw = await self.call_action(service_type, action_name, args)
        root = ElementTree.fromstring(raw)
        body = _find_child(root, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
        if body is None:
            raise RuntimeError(f"No SOAP Body in response for {action_name}")
        # Most Wemo responses have a single child: <u:ActionNameResponse>
        response_elem = _first_child(body)
        if response_elem is None:
            raise RuntimeError(f"Empty SOAP Body in response for {action_name}")
        return response_elem

    # -- Wemo convenience methods -----------------------------------------------

    async def get_binary_state(self) -> dict[str, Any]:
        """Call GetBinaryState and return parsed state dict."""
        elem = await self.call_action_parsed(_BASICEVENT_SERVICE, "GetBinaryState")
        raw = _child_text(elem, "BinaryState") or "0"
        return _parse_binary_state(raw)

    async def set_binary_state(
        self, value: int, brightness: int | None = None
    ) -> bool:
        """Call SetBinaryState(1/0) with optional brightness.

        Returns True on success. Raises on error.
        """
        args = {"BinaryState": value}
        if brightness is not None:
            args["brightness"] = brightness
        await self.call_action(_BASICEVENT_SERVICE, "SetBinaryState", args)
        return True

    async def get_insight_params(self) -> dict[str, Any]:
        """Call GetInsightParams and return parsed fields."""
        elem = await self.call_action_parsed(_INSIGHT_SERVICE, "GetInsightParams")
        raw = _child_text(elem, "InsightParams") or ""
        return _parse_insight_params(raw)

    async def get_attributes(self) -> str:
        """Call GetAttributes on deviceevent and return the raw attribute list."""
        try:
            elem = await self.call_action_parsed(
                _DEVICEEVENT_SERVICE, "GetAttributes"
            )
            return _child_text(elem, "attributeList") or ""
        except Exception:  # noqa: BLE001 - optional probe; absence is not an error.
            _LOGGER.debug("GetAttributes failed for %s:%s", self.host, self.port)
            return ""


# -- XML helpers ----------------------------------------------------------------

def _build_soap_envelope(
    service_type: str, action_name: str, args: dict[str, Any]
) -> str:
    """Build a SOAP XML envelope body for a single action call.

    Example output::

        <?xml version="1.0" encoding="utf-8"?>
        <s:Envelope ...>
          <s:Body>
            <u:SetBinaryState xmlns:u="urn:Belkin:service:basicevent:1">
              <BinaryState>1</BinaryState>
            </u:SetBinaryState>
          </s:Body>
        </s:Envelope>
    """
    ns = service_type
    body = ElementTree.Element("s:Body")
    action_elem = ElementTree.SubElement(body, f"u:{action_name}")
    action_elem.set("xmlns:u", ns)
    for key, value in args.items():
        child = ElementTree.SubElement(action_elem, key)
        child.text = str(value)
    # Manually wrap in envelope instead of using ElementTree encoding quirks.
    body_xml = ElementTree.tostring(body, encoding="unicode")
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f"{body_xml}</s:Envelope>"
    )


def _parse_binary_state(raw: str) -> dict[str, Any]:
    """Parse GetBinaryState response value.

    Usually just "0" or "1", but some devices return pipe-delimited extras
    like ``"1|1678492800|120"`` (state|timestamp|something).
    """
    parts = raw.split("|")
    try:
        value = int(parts[0]) if parts[0] else 0
    except ValueError:
        # Wemo occasionally returns "error" here while the relay is busy.
        _LOGGER.debug("Unparseable BinaryState %r; treating as off", raw)
        value = 0
    return {
        "value": value,
        "raw": raw,
        "extra": parts[1:] if len(parts) > 1 else [],
    }


def _parse_insight_params(raw: str) -> dict[str, Any]:
    """Parse pipe-delimited InsightParams into a labelled dict.

    Format: ``state|lastchange|onfor|ontoday|ontotal|timeperiod|wifipower|
    currentpower_mw|todaymw|totalmw|powerthreshold``
    """
    parts = raw.split("|")
    labels = [
        "state", "lastchange", "onfor", "ontoday", "ontotal",
        "timeperiod", "wifipower", "currentpower_mw",
        "todaymw", "totalmw", "powerthreshold",
    ]
    result: dict[str, Any] = {"raw": raw}
    for idx, label in enumerate(labels):
        if idx < len(parts) and parts[idx]:
            result[label] = _try_int(parts[idx])
        else:
            result[label] = None
    return result


def _try_int(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


# -- ElementTree helpers --------------------------------------------------------

def _find_child(parent: ElementTree.Element, tag: str) -> ElementTree.Element | None:
    for child in parent:
        if child.tag == tag:
            return child
    return None


def _first_child(parent: ElementTree.Element) -> ElementTree.Element | None:
    for child in parent:
        return child
    return None


def _child_text(parent: ElementTree.Element, tag: str) -> str | None:
    for child in parent:
        if child.tag == tag or child.tag.endswith(f"}}{tag}"):
            return (child.text or "").strip() or None
    return None
