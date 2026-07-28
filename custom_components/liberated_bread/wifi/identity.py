"""WiFi device identity normalization and matching.

Provides canonical key normalization, case-insensitive matching, and
device-key derivation shared by config_flow, __init__, manager, and discovery.
"""

from __future__ import annotations

import hashlib
import re

# Canonical identity keys in priority order (matches spec discovery.identity.stable_keys).
CANONICAL_IDENTITY_KEYS = ("udn", "serial", "mac")

# Aliases that map non-canonical names to canonical ones on read.
IDENTITY_READ_ALIASES: dict[str, str] = {
    "serialNumber": "serial",
    "macAddress": "mac",
}


def normalize_identity(raw: dict[str, str]) -> dict[str, str]:
    """Resolve aliases and return a canonical identity dict.

    Only canonical keys (udn, serial, mac) are included.
    Non-canonical / passthrough keys (variant, host, etc.) are DROPPED
    so they cannot cause false-positive matches.
    """
    r = dict(raw)
    for alias, target in IDENTITY_READ_ALIASES.items():
        if alias in r and target not in r:
            r[target] = r.pop(alias)
    canon: dict[str, str] = {}
    for key in CANONICAL_IDENTITY_KEYS:
        value = r.get(key)
        if value:
            canon[key] = str(value)
    return canon


def identity_value_matches(a: str | None, b: str | None, key: str) -> bool:
    """Compare two identity values after normalization.

    *MAC* values are hex-stripped and lowercased (aa:bb:cc == aabbcc).
    *UDN/serial* values are stripped and case-folded (UUID:xxx == uuid:xxx).
    """
    if not a or not b:
        return False
    if key == "mac":
        return _normalize_mac(a) == _normalize_mac(b)
    return _normalize_udn_serial(a) == _normalize_udn_serial(b)


def identity_matches(stored: dict[str, str], discovered: dict[str, str]) -> bool:
    """Return True when *stored* identity matches a *discovered* device.

    Compared on canonical keys (udn, serial, mac) after normalisation.
    """
    canon_stored = normalize_identity(stored)
    canon_disc = normalize_identity(discovered)
    for key in CANONICAL_IDENTITY_KEYS:
        if identity_value_matches(canon_stored.get(key), canon_disc.get(key), key):
            return True
    return False


def derive_device_key(identity: dict[str, str], host: str = "", port: int = 0) -> str:
    """Derive a stable device key from identity in priority order.

    Uses spec stable_keys order: udn → serial → mac → sha1(host:port).

    MAC values are hex-stripped. UDN/serial values keep alphanumeric + ``_-``.
    """
    canon = normalize_identity(identity)
    for key in CANONICAL_IDENTITY_KEYS:
        value = canon.get(key)
        if not value:
            continue
        if key == "mac":
            normalised = _normalize_mac(value)
        else:
            normalised = _normalize_udn_serial(value)
        if normalised:
            return normalised
    digest = hashlib.sha1(f"{host}:{port}".encode()).hexdigest()[:12]
    return f"wifi_{digest}"


def _normalize_mac(value: str) -> str:
    """Strip to lowercase hex digits only."""
    return re.sub(r"[^0-9a-f]", "", value.lower())


def _normalize_udn_serial(value: str) -> str:
    """Keep alphanumeric + common separators, lowercase."""
    return re.sub(r"[^0-9a-z_-]", "", value.lower())
