# ha-plugins

Home Assistant plugins for [Liberated Bread](https://liberatedbread.com).

This repository serves two Home Assistant distribution paths from one repo:

- `repository.yaml` at the repository root makes this a Home Assistant add-on repository.
- `hacs.json` and `custom_components/liberated_bread/` make this a HACS custom integration repository.

## Moonshine Add-On

`moonshine/` contains a Home Assistant add-on for speech-to-text with [Moonshine](https://github.com/moonshine-ai/moonshine). It is an unofficial drop-in add-on intended for the Wyoming Protocol flow that Home Assistant voice assistants use.

### Install Moonshine

1. In Home Assistant, go to **Settings > Add-ons > Add-on Store**.
2. Open the menu and choose **Repositories**.
3. Add this repository URL:

   ```text
   https://github.com/liberatedbread/ha-plugins
   ```

4. Install the **Moonshine** add-on.
5. After it starts, add Moonshine through **Settings > Devices & services > Wyoming Protocol**. If it is not discovered automatically, add it manually using the add-on host and port `10300`.
6. Select it as the speech-to-text engine for your voice assistant.

## Liberated Bread Integration

`custom_components/liberated_bread/` contains the Liberated Bread custom integration for Home Assistant. It discovers and manages supported Bluetooth and Wi-Fi devices using bundled device specifications.

### Install With HACS

1. In HACS, open **Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add this repository URL:

   ```text
   https://github.com/liberatedbread/ha-plugins
   ```

4. Select category **Integration**.
5. Install **Liberated Bread** and restart Home Assistant.

### Bundled Device Specs

The integration ships device specs for:

- Admore light bar
- Autobaba LED backpack
- Bluetooth LED name badge
- Chef IQ Sense
- Ember mug
- Frigidaire portable AC
- Frigidaire window AC
- iDotMatrix
- LEDs2RAVE4 lunchbox LED
- Magic Display
- Motool Slacker
- Nyan BT image controller
- PAX vape
- Shining glasses
- Shining mask
- Vector robot
- Wemo devices

## Attribution

This combined repository was merged from:

- `PigsCanFlyLabs/moonshine4homeassistant`, preserving its Git commit history.
- `PigsCanFlyLabs/liberatedbread-homeassistant`, importing the live working-tree integration because its Git history only contained an initial `.gitignore` commit while the Home Assistant integration files were untracked.

## License

Repository license text is in `LICENSE`. Moonshine and its dependencies may have separate license terms; review upstream projects before redistribution.
