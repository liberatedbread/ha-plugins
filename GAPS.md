# GAPS.md — Known Gaps in Liberated Bread Protocol Specs

Last updated: 2026-07-28

## 1. Targets Without Device-Spec YAMLs (27)

These targets have research stub files under `targets/` but no corresponding
`device-specs/devices/<name>.yaml`. They are in early research phase.

| Target | Probable Protocol |
|--------|-------------------|
| ble-pulse-oximeter | BLE |
| bmw-motorcycle-motoscan | BLE / OBD-II |
| cat-printer | BLE |
| divoom-pixoo | BLE |
| elk-bledom-led-strip | BLE |
| etekcity-smart-scale | BLE |
| fichero-d11-printer | BLE |
| frigidaire-ac | WiFi (split into portable-ac + window-ac specs) |
| gerbing-thermogauge | BLE |
| govee-h5075-thermo | BLE |
| govee-h5080-plug | BLE |
| govee-h6001-bulb | BLE |
| hotwired-heated-gear | BLE |
| ibbq-meat-thermo | BLE |
| ifreqtech-speaker-mic | BLE |
| iledcolor-led-panel | BLE |
| itag-ble-tracker | BLE |
| led-space | BLE |
| m6-fitness-band | BLE |
| motorcycle-ground-effect-lighting | BLE |
| niimbot-d110 | BLE |
| roku-local-remote | WiFi |
| spider-farmer-ggs | BLE |
| switchbot-ble | BLE |
| xiaomi-lywsd03mmc | BLE |
| xiaomi-miflora | BLE |
| xiaomi-mi-scale | BLE |

## 2. Specs That Need Deeper Docs (4)

These have `device-specs/devices/*.yaml` files but only stub documentation pages:

- **frigidaire-portable-ac** — has stub; needs full documentation
- **frigidaire-window-ac** — has stub; needs full documentation
- **proglow-motorcycle-led** — has stub; needs full documentation
- **seeblue-motorcycle-led** — has stub; needs full documentation

## 3. Frigidaire Split

`targets/frigidaire-ac.md` covers both portable and window ACs, but the
device-specs are split into two files. The combined docs page
(`docs/devices/frigidaire-ac.md`) serves as an overview. Consider whether these
should be merged into a single spec or kept separate long-term.

## 4. Targets Without Docs Pages (26)

All 27 targets from section 1 (minus frigidaire-ac which has a combined doc
page) also lack `docs/devices/<name>.md` pages. These need research completion
before docs can be written.

## 5. Docs With No Spec (1)

`docs/devices/frigidaire-ac.md` has no single device-spec — it's been split
into `frigidaire-portable-ac.yaml` and `frigidaire-window-ac.yaml`. The doc
serves as an overview for both.

## 6. Known WiFi Devices Without Target Files

These devices have docs pages and device-specs but no target stub; they were
likely documented before the target-file convention was established:

- Anki Vector Robot (`vector-robot`)
- Roku ECP (`roku-ecp`)
- Philips Hue Bridge (`hue-bridge`)
- Enphase Envoy (`enphase-envoy`)
- Dyson Air Purifier (`dyson-air-purifier`)
- LIFX Z (`lifx-z`)
- Lutron Caseta Smart Bridge 2 (`lutron-caseta-smart-bridge`)
- Rachio Controller (`rachio-controller`)
- SmartThings Hub v2 (`smartthings-hub-v2`)
- Belkin Wemo (`wemo-devices`)

## Summary

| Metric | Count |
|--------|-------|
| Total targets | 50 |
| Targets with specs | 24 |
| Targets without specs | 27 |
| Specs with stub docs | 4 |
| Docs without specs | 1 |

## 7. Pre-existing: Broken `#working-a-repair-cafe` Anchor (3 docs)

`docs/protocols/obd2-common.md` uses `{#working-a-repair-cafe}` syntax which
requires the `attr_list` extension. That extension is not in `mkdocs.yml`.
Affected files:

- `docs/protocols/obd2-common.md`
- `docs/devices/bmw-motorcycle-diagnostics.md`
- `docs/devices/triumph-tiger-900.md`

Fix: either add `attr_list` to `markdown_extensions` in `mkdocs.yml`, or
replace the `{#anchor}` syntax with a standard HTML `<a id="..."></a>` tag.
