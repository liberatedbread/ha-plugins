# Contributing to OpenGreenIoT Protocol Docs

First off -- thanks for wanting to help keep IoT devices alive!

## Documenting a New Device

The most valuable contribution. If you have an abandoned IoT device:

1. Copy `docs/devices/_template.md` to `docs/devices/your-device-name.md`
2. Fill in as much as you can -- partial documentation is still valuable
3. Open a PR with your findings

## Style Guide

- Use the device documentation template for consistency
- Include hex dumps and protocol byte layouts where possible
- Reference specific BLE UUIDs, HTTP endpoints, or MQTT topics
- Credit any existing research you're building on

## Code Contributions

1. Fork the repo
2. Create a feature branch
3. Make sure docs build: `mkdocs build --strict`
4. Submit a PR
