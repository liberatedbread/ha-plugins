"""WiFi device identity normalization and matching.

Provides canonical key normalization, case-insensitive matching, and
device-key derivation shared by config_flow, __init__, manager, and discovery.
"""

from __future__ import annotations

import hashlib
import re

CANONICAL_IDENTITY_KEYS = ("udn", "serial", "mac")

IDENTITY_READ_ALIASES: dict[str, str] = {
    "serialNumber": "serial",
    "macAddress": "mac",
}


def normalize_identity(raw: dict[str, str]) -> dict[str, str]:
    """Convert raw identity dict to canonical form with key aliasing.

    Flattens known aliases (e.g. ``serialNumber`` → ``serial``) and
    returns only canonical keys from ``CANONICAL_IDENTITY_KEYS``.
    """
    r = dict(raw)
    for alias, target in IDENTITY_READ_ALIASES.items():
        if alias in r and target not in r:
            r[target] = r.pop(alias)
    canon: dict[str, str] = {}
    for key in CANONICAL_IDENTITY_KEYS:
        value = r.get(key)
        if not value:
            continue
        canon[key] = str(value)
    return canon


def identity_value_matches(a: str | None, b: str | None, key: str) -> bool:
    """Compare two identity values for the same key, normalising by type.

    MAC addresses are compared after stripping delimiters; UDNs and
    serials are compared after stripping non-alphanumeric/-/_ characters.
    """
    if not a or not b:
        return False
    if key == "mac":
        return _normalize_mac(a) == _normalize_mac(b)
    return _normalize_udn_serial(a) == _normalize_udn_serial(b)


def identity_matches(stored: dict[str, str], discovered: dict[str, str]) -> bool:
    """Return True if *discovered* device identity matches *stored* criteria.

    Both sides are normalised via :func:`normalize_identity` and compared
    key-by-key.  A single matching canonical key is sufficient.
    """
    canon_stored = normalize_identity(stored)
    canon_disc = normalize_identity(discovered)
    for key in CANONICAL_IDENTITY_KEYS:
        if identity_value_matches(
            canon_stored.get(key), canon_disc.get(key), key
        ):
            return True
    return False


def derive_device_key(
    identity: dict[str, str], host: str = "", port: int = 0
) -> str:
    """Derive a canonical device key from identity + host:port fallback.

    Prefers a normalised MAC, then UDN, then serial.  Falls back to a
    SHA1-based key from ``host:port`` when no canonical identity field
    produces a usable value.
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


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _normalize_mac(value: str) -> str:
    """Strip colons, dashes, and whitespace; lowercase hex."""
    return re.sub(r"[^0-9a-f]", "", value.lower())


def _normalize_udn_serial(value: str) -> str:
    """Strip all non-alphanumeric, non-dash, non-underscore characters."""
    return re.sub(r"[^0-9a-z_-]", "", value.lower())
