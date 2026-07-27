"""Advertisement matching helpers."""

from __future__ import annotations

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from ..spec.models import DeviceSpec


def service_info_matches_spec(
    service_info: BluetoothServiceInfoBleak, spec: DeviceSpec
) -> bool:
    """Return true when a Bluetooth advertisement matches a spec."""
    identification = spec.device.identification
    if identification is None:
        return False
    local_name = service_info.name or ""
    prefix = identification.local_name_prefix
    if prefix is not None and prefix != "" and local_name.startswith(prefix):
        return True
    advertised = {uuid.lower() for uuid in service_info.service_uuids}
    expected = {uuid.lower() for uuid in identification.service_uuids or []}
    return bool(advertised & expected)

