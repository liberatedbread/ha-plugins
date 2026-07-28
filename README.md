# Liberated Bread — Home Assistant Plugins

> **⚠️ WIP / UNTESTED — DO NOT USE IN PRODUCTION**
>
> This integration is under active development. Device specs, discovery, and
> control paths have not been validated against real hardware. Expect
> breakage, missing features, and incomplete protocol handling. **DO NOT**
> deploy this to a production Home Assistant instance.

Custom integration, add-ons, and device specifications for the Liberated Bread
Home Assistant platform. Ships in the [Liberated Bread monorepo][lb].

[lb]: https://github.com/liberatedbread/liberatedbread-web-static

## Device Setup Guide

### WiFi Devices

WiFi devices **must** be connected to your local network before the integration
can discover and control them:

1. **Use the OEM app** (Wemo app, Vector app, etc.) to connect the device to
   your WiFi network.
2. Once the device is on WiFi, the Liberated Bread integration uses **SSDP**
   (Simple Service Discovery Protocol) or **mDNS** to find it automatically on
   your local network. No static IP configuration is needed.
3. For Wemo devices specifically, the integration stores stable identity keys
   (UDN, serial, MAC address) so it can **re-resolve** the device even if its
   IP address or HTTP port changes after a power cycle.

### BLE Devices

Bluetooth Low Energy (BLE) devices require:

1. **Bluetooth enabled** on your Home Assistant host, with a supported Bluetooth
   adapter.
2. The device must be **powered on and advertising**. Discovery is automatic —
   the integration scans for BLE advertisements that match the device spec
   (local name prefix, service UUIDs, or manufacturer data).
3. Some BLE devices may require an **AES-ECB encryption key** (e.g., Shining
   mask or glasses). The config flow will prompt you for the key when needed.

## Bundled Device Specs

### WiFi Devices

- **Belkin Wemo Smart Devices** — switches, dimmers, Insight plugs, motion
  sensors, bridge, coffee maker, crock pot, air purifier, heater, humidifier.
  Discovered via SSDP. Dynamic identity: UDN/serial/MAC so the device is
  re-resolved when its IP or port changes.

- **Vector Robot** — Anki/Digital Dream Labs companion robot. Discovered via
  mDNS (`_ankivector._tcp.local`). gRPC + protobuf 3 over TLS on port 443.

- **Frigidaire WiFi Portable AC** — WiFi-connected portable air conditioner.

- **Frigidaire WiFi Window AC** — WiFi-connected window air conditioner.

### BLE Devices

- Admore light bar
- Autobaba LED backpack
- Bluetooth LED name badge
- Chef IQ Sense
- Ember mug
- iDotMatrix
- LEDs2RAVE4 lunchbox LED
- Magic Display
- Motool Slacker
- Nyan BT image controller
- PAX vape
- Shining glasses
- Shining mask

## Known Limitations

### Wemo SOAP Control

Wemo devices are now fully supported via the SOAP transport layer
(`wifi/soap_client.py`). Discovery works via SSDP, and per-variant entities
are scoped to each device model so a Wemo Mini only gets a switch entity
(not Insight sensors). Insight plugs expose power/energy sensors in addition
to the switch, and dimmers use the light platform with brightness control.

### WiFi Device Control (General)

Vector robot and Frigidaire AC specs also lack entity blocks and rely on
protocol-specific clients (gRPC + protobuf, custom TCP/UDP). These backends
are not yet wired into the entity platform loop.

## Wemo Dynamic Identity

Wemo devices change their HTTP port after a power cycle or reconnect (commonly
in the 49152–49159 range). To handle this, the integration stores stable
identity keys — **UDN** (primary), **serial**, and **MAC** — at config entry
time. When a request to the device fails, the manager attempts a single SSDP
re-resolution using the stored identity to find the new host:port before
marking the device unavailable.

---

## HACS Installation

1. In HACS, choose **... > Custom repositories**.
2. Add the repository URL for the Liberated Bread monorepo
   (`https://github.com/liberatedbread/liberatedbread-web-static`).
3. Select category **Integration**.
4. Install **Liberated Bread** and restart Home Assistant.

## Moonshine Speech-to-Text Add-On

`moonshine/` contains a Home Assistant add-on for speech-to-text with
[Moonshine](https://github.com/moonshine-ai/moonshine). It is an unofficial
drop-in add-on intended for the Wyoming Protocol flow.

After installing the add-on, add Moonshine through **Settings > Devices &
services > Wyoming Protocol**. If it is not discovered automatically, add it
manually using the add-on host and port `10300`. Then select it as the
speech-to-text engine for your voice assistant.

## Repository Layout

This directory serves as both a Home Assistant add-on repository (via
`repository.yaml`) and a HACS custom integration repository (via `hacs.json`
and `custom_components/liberated_bread/`).

The integration was created from reverse-engineering and open-source lineage
(pywemo, Home Assistant core, ouimeaux, anki_vector SDK). Device specs live in
`custom_components/liberated_bread/device_specs/` organized by transport
(`wifi/` and `ble/`).

## License

Repository license text is in `LICENSE`. Moonshine and its dependencies may
have separate license terms; review upstream projects before redistribution.
