"""HTTP client for WiFi Liberated Bread devices."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import aiohttp

try:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
except ModuleNotFoundError:  # pragma: no cover - standalone import outside HA.
    def async_get_clientsession(_: object) -> aiohttp.ClientSession:
        return aiohttp.ClientSession()

from ..spec.models import EntityDef, HttpEndpoint

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class LiberatedBreadHttpClient:
    """HTTP client for WiFi device REST APIs."""

    def __init__(
        self,
        host: str,
        port: int,
        hass: HomeAssistant,
        session: aiohttp.ClientSession | None = None,
        use_ssl: bool | None = None,
    ) -> None:
        self.host, host_scheme = _split_host_scheme(host)
        self.port = port
        self.hass = hass
        self.session = session or async_get_clientsession(hass)
        self.use_ssl = use_ssl if use_ssl is not None else _default_use_ssl(port, host_scheme)

    async def request(self, endpoint: HttpEndpoint, **path_params: Any) -> Any:
        """Execute an HTTP endpoint from the spec."""
        path = endpoint.path.format(**path_params)
        url = path if path.startswith(("http://", "https://")) else self._url(path)
        kwargs: dict[str, Any] = {}
        body = endpoint.request_body or {}
        if body:
            kwargs["json"] = _json_body_from_params(path_params)
        kwargs.setdefault("timeout", aiohttp.ClientTimeout(total=10))
        try:
            async with self.session.request(endpoint.method, url, **kwargs) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, ValueError):
                        _LOGGER.debug("Invalid JSON response from %s", url)
                return await response.text()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RuntimeError(
                f"HTTP {endpoint.method} {url} failed for endpoint {endpoint.name}: {err}"
            ) from err

    async def get_state(self, entity: EntityDef) -> Any:
        """Read entity state from its state_topic endpoint."""
        if not entity.state_topic:
            return None
        endpoint = HttpEndpoint(
            method="GET",
            path=entity.state_topic,
            name=entity.name,
        )
        return await self.request(endpoint)

    async def send_command(
        self, entity: EntityDef, command: str, **params: Any
    ) -> Any:
        """Execute a command defined in entity.commands."""
        endpoint = HttpEndpoint(
            method="POST",
            path=command,
            name=command,
            request_body={"content_type": "application/json"},
        )
        return await self.request(endpoint, payload=params)

    def _url(self, path: str) -> str:
        prefix = "" if path.startswith("/") else "/"
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.host}:{self.port}{prefix}{path}"


def _split_host_scheme(host: str) -> tuple[str, str | None]:
    if host.startswith("https://"):
        return host.removeprefix("https://").rstrip("/"), "https"
    if host.startswith("http://"):
        return host.removeprefix("http://").rstrip("/"), "http"
    return host, None


def _default_use_ssl(port: int, host_scheme: str | None) -> bool:
    if host_scheme == "https":
        return True
    if host_scheme == "http":
        return False
    return int(port) == 443


def _json_body_from_params(path_params: dict[str, Any]) -> dict[str, Any]:
    if "json" in path_params:
        return path_params["json"]
    if "payload" in path_params:
        return path_params["payload"]
    return {
        key: value
        for key, value in path_params.items()
        if key not in {"device_id", "applianceId"}
    }
