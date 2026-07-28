"""Variant matching for WiFi device specs.

Matches a discovered deviceType / UDN / friendly_name against the spec's
variants list to determine which per-variant entities to use.
"""

from __future__ import annotations

from typing import Any


def match_variant(
    spec: object,
    device_type: str | None,
    udn: str | None,
    friendly_name: str | None,
) -> dict[str, Any] | None:
    """Match a discovered device against the spec's variant list.

    Match order (first wins at each level):
      1. Exact *device_type* match on ``identification.device_type``.
         When **multiple** variants share the same deviceType (e.g. Dimmer
         v1 and v2 both use ``dimmer:1``), UDN prefix is used as a
         tiebreaker — the variant with the LONGEST matching UDN prefix wins.
      2. *device_type* matches an entry in ``identification.alternate_device_types``
      3. UDN prefix match — LONGEST matching prefix wins
      4. *friendly_name* contains the variant's ``identification.friendly_name_pattern``
         (case-insensitive substring)

    Returns the matched variant dict (with its ``entities`` block) or None.
    """
    device = getattr(spec, "device", None)
    if device is None:
        return None
    variants: list[dict[str, Any]] = getattr(device, "variants", None) or []
    if not variants:
        return None

    dt = (device_type or "").strip()
    u = (udn or "").strip()
    fn = (friendly_name or "").strip().lower()

    # --- Level 1: exact deviceType match (with UDN tiebreaker for ties) ---
    dt_matches = _variants_by_device_type(variants, dt)
    if len(dt_matches) == 1:
        return dt_matches[0]
    if len(dt_matches) > 1:
        best = _best_by_udn_prefix(dt_matches, u)
        if best is not None:
            return best

    # --- Level 2: alternate_device_types ---
    for variant in variants:
        ident = variant.get("identification") or {}
        alternates: list[str] = ident.get("alternate_device_types") or []
        for alt in alternates:
            if dt and alt.strip().lower() == dt.lower():
                return variant

    # --- Level 3: UDN prefix match (longest first) ---
    best = _best_by_udn_prefix(variants, u)
    if best is not None:
        return best

    # --- Level 4: friendly_name substring ---
    for variant in variants:
        ident = variant.get("identification") or {}
        pattern = (ident.get("friendly_name_pattern") or "").strip().lower()
        if fn and pattern and pattern in fn:
            return variant

    return None


def _variants_by_device_type(
    variants: list[dict[str, Any]], device_type: str
) -> list[dict[str, Any]]:
    """Return all variants whose deviceType matches exactly (case-insensitive)."""
    if not device_type:
        return []
    dt_lower = device_type.lower()
    result: list[dict[str, Any]] = []
    for variant in variants:
        ident = variant.get("identification") or {}
        variant_dt = (ident.get("device_type") or "").strip().lower()
        if variant_dt and variant_dt == dt_lower:
            result.append(variant)
    return result


def _best_by_udn_prefix(
    variants: list[dict[str, Any]], udn: str
) -> dict[str, Any] | None:
    """Find the variant with the longest matching UDN prefix.

    Returns None when *udn* is empty or no prefix matches.
    """
    if not udn:
        return None
    u_lower = udn.lower()
    best_len = 0
    best_variant: dict[str, Any] | None = None
    for variant in variants:
        ident = variant.get("identification") or {}
        prefixes: list[str] = ident.get("udn_prefixes") or []
        for prefix in prefixes:
            pf = prefix.strip().lower()
            if pf and u_lower.startswith(pf) and len(pf) > best_len:
                best_len = len(pf)
                best_variant = variant
    return best_variant
