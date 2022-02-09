## Voipcenter

This custom component allows you to add [Voipcenter](https://www.voipcenter.be/) Function indicators and events to Home Assistant.

## Requirements

- Voipcenter API addon enabled
- Voipcenter API ID, API Key, klantnummer and password
- Optional: Websocket addon enabled. Websocket username.

## Supported Features

Function indicators show up as switches in Home Assistant.
Call events from the websocket interface can be used as event triggers for automations

## Configuration

After installing the integration using HACS, use the [integration setup in your Home Assistant instance](https://my.home-assistant.io/redirect/config_flow_start/?domain=voipcenter) to configure. The integration will then automatically discover all function indicators.