"""WiFi discovery helpers for Liberated Bread device specs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urljoin, urlparse

import aiohttp

try:
    from defusedxml import ElementTree
except ImportError:  # pragma: no cover - dependency is declared in manifest.
    from xml.etree import ElementTree  # type: ignore[no-redef]

from ..spec.models import Discovery, DiscoveryMethod

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """A discovered device ready for config entry."""

    identity: dict[str, str]
    display_name: str
    host: str
    port: int
    control_urls: dict[str, str]
    raw_info: dict[str, Any] = field(default_factory=dict)


class WifiDiscovery:
    """Drives discovery from a spec's device.discovery.methods list."""

    def __init__(self, discovery: Discovery, hass: HomeAssistant | None = None) -> None:
        self.discovery = discovery
        self.hass = hass

    async def discover(self, timeout: int = 10) -> list[DiscoveredDevice]:
        """Run configured discovery methods concurrently and return deduped results."""
        return await DiscoveryRouter(self.hass).discover_all(self.discovery, timeout)

    async def _discover_ssdp(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Send M-SEARCH, parse responses, fetch LOCATION XML, extract identity."""
        return await SSDPScanner(self.discovery).discover(method, timeout)

    async def _discover_mdns(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Browse DNS-SD service type, collect host:port + TXT records."""
        return await MDNSScanner(self.discovery, self.hass).discover(method, timeout)

    async def _discover_cloud(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Stub - cloud discovery needs user auth. Returns empty list."""
        return await CloudDiscoveryBackend(self.discovery).discover(method, timeout)


class DiscoveryBackend(Protocol):
    """Backend interface for one discovery method type."""

    async def discover(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Discover devices for one configured method."""


class DiscoveryRouter:
    """Route discovery methods to pluggable backends and run them concurrently."""

    def __init__(self, hass: HomeAssistant | None = None) -> None:
        self.hass = hass

    async def discover_all(
        self, discovery: Discovery, timeout: int
    ) -> list[DiscoveredDevice]:
        """Run all configured discovery methods concurrently."""
        tasks = []
        for method in discovery.methods:
            backend = self._backend_for(discovery, method)
            if backend is None:
                continue
            tasks.append(backend.discover(method, timeout))
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        devices: list[DiscoveredDevice] = []
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.debug("WiFi discovery backend failed: %s", result)
                continue
            devices.extend(result)
        return _dedupe_devices(devices, discovery)

    def _backend_for(
        self, discovery: Discovery, method: DiscoveryMethod
    ) -> DiscoveryBackend | None:
        if method.type == "ssdp":
            return SSDPScanner(discovery)
        if method.type == "mdns":
            return MDNSScanner(discovery, self.hass)
        if method.type == "cloud":
            return CloudDiscoveryBackend(discovery)
        if method.type == "ble_scan":
            return None
        _LOGGER.warning("Unsupported WiFi discovery method type: %s", method.type)
        return None


class SSDPScanner:
    """SSDP M-SEARCH discovery backend."""

    def __init__(self, discovery: Discovery) -> None:
        self.discovery = discovery

    async def _discover_ssdp(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Send M-SEARCH, parse responses, fetch LOCATION XML, extract identity."""
        group = method.multicast_group or "239.255.255.250"
        port = int(method.multicast_port or 1900)
        targets = method.search_targets or ["ssdp:all"]
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        mreq = socket.inet_aton(group) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        found: dict[str, DiscoveredDevice] = {}
        seen_usns: set[str] = set()
        try:
            for target in targets:
                request = "\r\n".join(
                    [
                        "M-SEARCH * HTTP/1.1",
                        f"HOST: {group}:{port}",
                        'MAN: "ssdp:discover"',
                        "MX: 1",
                        f"ST: {target}",
                        "",
                        "",
                    ]
                ).encode()
                await loop.sock_sendto(sock, request, (group, port))

            deadline = loop.time() + timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 65535), timeout=remaining
                    )
                except TimeoutError:
                    break
                headers = _parse_ssdp_headers(data)
                location = headers.get("location")
                usn = headers.get("usn")
                if usn and usn in seen_usns:
                    continue
                if usn:
                    seen_usns.add(usn)
                if not location or location in found:
                    continue
                device = await _device_from_location(
                    location, method, addr[0], self.discovery
                )
                if device is not None:
                    found[location] = device
        finally:
            sock.close()
        return list(found.values())

    async def discover(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Discover SSDP devices."""
        return await self._discover_ssdp(method, timeout)


class MDNSScanner:
    """mDNS/DNS-SD discovery backend."""

    def __init__(self, discovery: Discovery, hass: HomeAssistant | None = None) -> None:
        self.discovery = discovery
        self.hass = hass

    async def _discover_mdns(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Browse DNS-SD service type, collect host:port + TXT records."""
        try:
            from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
        except ImportError:
            _LOGGER.warning("zeroconf is not installed; mDNS discovery unavailable")
            return []

        devices: list[DiscoveredDevice] = []
        seen_names: set[str] = set()
        seen_identities: set[str] = set()
        service_type = _normalize_mdns_service_type(method.service_type)
        if not service_type:
            return []
        discovery = self.discovery

        class Listener(ServiceListener):
            def add_service(self, zeroconf: Zeroconf, type_: str, name: str) -> None:
                info = zeroconf.get_service_info(type_, name)
                if info is None or name in seen_names:
                    return
                seen_names.add(name)
                addresses = info.parsed_addresses()
                if not addresses:
                    return
                txt = {
                    _decode_txt_key(key): _decode_txt_value(value)
                    for key, value in info.properties.items()
                }
                identity = _identity_from_mdns(name, info.server, txt, method)
                stable_key = _device_dedupe_key(identity, discovery)
                if stable_key in seen_identities:
                    return
                seen_identities.add(stable_key)
                display = identity.get(discovery.identity.display) or name
                devices.append(
                    DiscoveredDevice(
                        identity=identity,
                        display_name=display,
                        host=addresses[0],
                        port=int(method.port or info.port or 80),
                        control_urls={},
                        raw_info={
                            "name": name,
                            "hostname": info.server,
                            "txt": txt,
                            "addresses": addresses,
                        },
                    )
                )

        zeroconf = None
        owned_zeroconf = False
        try:
            zeroconf = await _async_get_zeroconf(self.hass)
            if zeroconf is None:
                zeroconf = Zeroconf()
                owned_zeroconf = True
            ServiceBrowser(zeroconf, service_type, Listener())
            await asyncio.sleep(timeout)
        finally:
            if owned_zeroconf and zeroconf is not None:
                zeroconf.close()
        return devices

    async def discover(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Discover mDNS devices."""
        return await self._discover_mdns(method, timeout)


class CloudDiscoveryBackend:
    """Cloud discovery backend placeholder."""

    def __init__(self, discovery: Discovery) -> None:
        self.discovery = discovery

    async def _discover_cloud(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Stub - cloud discovery needs user auth. Returns empty list."""
        return []

    async def discover(
        self, method: DiscoveryMethod, timeout: int
    ) -> list[DiscoveredDevice]:
        """Discover cloud devices when auth is available."""
        return await self._discover_cloud(method, timeout)


async def _device_from_location(
    location: str,
    method: DiscoveryMethod,
    fallback_host: str,
    discovery: Discovery,
) -> DiscoveredDevice | None:
    response = await _fetch_location_xml(location)
    resolved_location = location
    if response is None:
        fallback_response = await _fetch_port_fallback_xml(location, method)
        if fallback_response is None:
            return None
        resolved_location, response = fallback_response

    try:
        root = ElementTree.fromstring(response)
    except ElementTree.ParseError as err:
        _LOGGER.debug("Failed to parse SSDP LOCATION XML %s: %s", resolved_location, err)
        return None

    parsed = urlparse(resolved_location)
    host = parsed.hostname or fallback_host
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    identity, display = _extract_xml_identity(root, method)
    control_urls = _extract_control_urls(root, resolved_location, method)
    raw_info = {
        "location": resolved_location,
        "identity": identity,
        "control_urls": control_urls,
    }
    stable_identity = {
        key: str(identity[key])
        for key in discovery.identity.stable_keys
        if identity.get(key) is not None
    }
    if not stable_identity:
        stable_identity = {key: str(value) for key, value in identity.items() if value}
    return DiscoveredDevice(
        identity=stable_identity,
        display_name=display or identity.get("friendlyName") or host,
        host=host,
        port=port,
        control_urls=control_urls,
        raw_info=raw_info,
    )


async def _fetch_location_xml(location: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(location, timeout=5) as response:
                response.raise_for_status()
                return await response.text()
    except Exception as err:  # noqa: BLE001 - discovery should keep scanning.
        _LOGGER.debug("Failed to fetch SSDP LOCATION %s: %s", location, err)
        return None


async def _fetch_port_fallback_xml(
    location: str, method: DiscoveryMethod
) -> tuple[str, str] | None:
    if not method.port_fallback:
        return None
    parsed = urlparse(location)
    if not parsed.hostname:
        return None
    path = parsed.path or "/setup.xml"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    scheme = parsed.scheme or "http"
    for port in method.port_fallback:
        fallback = f"{scheme}://{parsed.hostname}:{int(port)}{path}"
        if fallback == location:
            continue
        response = await _fetch_location_xml(fallback)
        if response is not None:
            return fallback, response
    return None


def _parse_ssdp_headers(data: bytes) -> dict[str, str]:
    text = data.decode(errors="replace")
    headers: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _extract_xml_identity(
    root: ElementTree.Element, method: DiscoveryMethod
) -> tuple[dict[str, Any], str | None]:
    parse = _response_parse(method)
    mapping = parse.get("device_identity", {}) if isinstance(parse, dict) else {}
    identity: dict[str, Any] = {}
    for item in mapping.get("stable_keys") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        source = item.get("source")
        if key and source:
            identity[str(key)] = _xml_value(root, str(source))
    variant = mapping.get("variant")
    if isinstance(variant, dict) and variant.get("source"):
        identity["variant"] = _xml_value(root, str(variant["source"]))
    display_source = mapping.get("display", {})
    display = None
    if isinstance(display_source, dict) and display_source.get("source"):
        display = _xml_value(root, str(display_source["source"]))
    return identity, display


def _extract_control_urls(
    root: ElementTree.Element, location: str, method: DiscoveryMethod
) -> dict[str, str]:
    parse = _response_parse(method)
    mapping = parse.get("control_endpoints", {}) if isinstance(parse, dict) else {}
    source = mapping.get("source", "xml://device/serviceList/service")
    fields = mapping.get("fields") or {}
    service_type_field = fields.get("service_type", "serviceType")
    control_url_field = fields.get("control_url", "controlURL")
    control_urls: dict[str, str] = {}
    for service in _xml_findall(root, str(source)):
        service_type = _child_text(service, str(service_type_field))
        control_url = _child_text(service, str(control_url_field))
        if service_type and control_url:
            control_urls[service_type] = urljoin(location, control_url)
    return control_urls


def _response_parse(method: DiscoveryMethod) -> dict[str, Any]:
    response_mapping = method.response_mapping or {}
    location = response_mapping.get("location", {})
    parse = location.get("parse", {}) if isinstance(location, dict) else {}
    return parse if isinstance(parse, dict) else {}


def _identity_from_mdns(
    name: str, hostname: str | None, txt: dict[str, str], method: DiscoveryMethod
) -> dict[str, str]:
    identity = {"name": name}
    if hostname:
        identity["hostname"] = hostname
    for key in method.txt_record_keys:
        if key in txt:
            identity[key] = txt[key]
    return identity


async def _async_get_zeroconf(hass: HomeAssistant | None) -> Any:
    if hass is None:
        return None
    try:
        from homeassistant.components.zeroconf import async_get_instance
    except (ImportError, ModuleNotFoundError):
        return None
    instance = await async_get_instance(hass)
    return getattr(instance, "zeroconf", instance)


def _normalize_mdns_service_type(service_type: str | None) -> str | None:
    if not service_type:
        return None
    normalized = service_type.strip()
    normalized = normalized.removesuffix(".")
    if not normalized.endswith(".local"):
        normalized = f"{normalized}.local"
    return f"{normalized}."


def _decode_txt_key(key: Any) -> str:
    if isinstance(key, bytes):
        return key.decode(errors="replace")
    return str(key)


def _decode_txt_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _dedupe_devices(
    devices: list[DiscoveredDevice], discovery: Discovery
) -> list[DiscoveredDevice]:
    deduped: list[DiscoveredDevice] = []
    seen: set[str] = set()
    for device in devices:
        key = _device_dedupe_key(device.identity, discovery)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(device)
    return deduped


def _device_dedupe_key(identity: dict[str, Any], discovery: Discovery) -> str:
    values = [
        str(identity[key])
        for key in discovery.identity.stable_keys
        if identity.get(key) is not None
    ]
    if values:
        return "|".join(values)
    if identity:
        return "|".join(f"{key}={identity[key]}" for key in sorted(identity))
    return ""


def _xml_value(root: ElementTree.Element, source: str) -> str | None:
    items = _xml_findall(root, source)
    if not items:
        return None
    return (items[0].text or "").strip() or None


def _xml_findall(root: ElementTree.Element, source: str) -> list[ElementTree.Element]:
    path = source.removeprefix("xml://").strip("/")
    parts = [part for part in path.split("/") if part]
    current = [root]
    if parts and _local_name(root.tag) == parts[0]:
        parts = parts[1:]
    for part in parts:
        next_items: list[ElementTree.Element] = []
        for node in current:
            next_items.extend(
                child for child in list(node) if _local_name(child.tag) == part
            )
        current = next_items
    return current


def _child_text(node: ElementTree.Element, name: str) -> str | None:
    with contextlib.suppress(IndexError):
        value = _xml_findall(node, name)[0].text
        return (value or "").strip() or None
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
