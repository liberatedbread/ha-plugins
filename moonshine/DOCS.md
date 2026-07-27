# moonshine4homeassistant

An unofficial attempt at making a drop in add-on for Home Assistant Nabu to replace Whisper with [Moonshine](https://github.com/moonshine-ai/moonshine).

This is a rough fork of https://github.com/home-assistant/addons/blob/master/whisper.

And depends on another fork of https://github.com/rhasspy/wyoming-faster-whisper at https://github.com/holdenk/wyoming-moonshine-ext/.

Both from https://github.com/OHF-Voice/wyoming.

## Why?

Whisper is slow, lots of people use RPIs for HA, and Moonshine is better speech to text for RPIs, among other places.

## Who?

Right now Holden.

## Does it work?

Sort of.

## Installation

You can install this into Home Assistant by adding https://github.com/liberatedbread/ha-plugins as an add-on repository. Then install the Moonshine add-on.

Once installed, go to **Settings > Devices and Services > Wyoming Protocol**. You should see **Moonshine** with an **Add** button.

If Moonshine is not listed under the Wyoming Protocol integration, manually add it with the hostname and port of the Moonshine container from the running add-on page.

Once added to the Wyoming Protocol list, configure it for your voice assistant under **Settings > Voice Assistants > your voice assistant > Speech-to-text**.

## License

This code is Apache-2.0 licensed. There are separate Moonshine and bundled dependency licenses. Most users can probably depend on the automatic non-commercial Moonshine license, but please consult a license expert before distributing this add-on or its image.

## Third-Party Terms

The add-on image installs and bundles third-party software at build time. Review the upstream license terms for each project before redistribution:

- moonshine-voice: https://github.com/usefulsensors/moonshine
- torch: https://github.com/pytorch/pytorch
- transformers: https://github.com/huggingface/transformers
- onnx-asr: https://github.com/istupakov/onnx-asr
- holdenk/wyoming-moonshine-ext: https://github.com/holdenk/wyoming-moonshine-ext
- wyoming: https://github.com/OHF-Voice/wyoming
