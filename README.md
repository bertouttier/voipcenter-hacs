# VoipCenter (PBXonline) for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration for the
[VoipCenter (PBXonline)](https://www.voipcenter.be) cloud telephone exchange,
using the VoipCenter **APIv2** and the realtime call **websocket**.

> **Upgrading from 1.x:** 2.0.0 is a rewrite on the VoipCenter APIv2. The
> v1 credentials (API ID/key, customer number, password) no longer work: after
> updating, Home Assistant asks to re-authenticate the existing entry with an
> **APIv2 username and password**. Open *Configure* afterwards to enter the
> websocket key. The websocket event keeps its `voipcenter` event type, but the
> old function indicator switches are replaced by new entities.

## Features

| Entity | Description |
| --- | --- |
| Switch per **function indicator** | On = red, off = green. Turning it on/off sets the indicator. |
| **Call state** sensor per SIP account | `idle`, `calling` or `ringing` (`currentState`). |
| **Registered** binary sensor per SIP account | Whether a SIP client is registered. |
| **Available** binary sensor per SIP account | Presence of the account. |
| **Voicemail messages** sensor per mailbox | Number of messages in the voicemail box. |
| **Ongoing calls** sensor | Number of ongoing conversations; details in the `conversations` attribute. |
| **In call** binary sensor | On while any conversation is ongoing. |
| **Last call event** sensor *(websocket)* | Time of the last realtime notification; its data in the attributes. |
| **Websocket** binary sensor *(websocket)* | Connection state of the realtime websocket. |

State is polled every 30 seconds. With the websocket enabled, every call
notification also triggers an immediate refresh.

### Services

| Service | Fields | API |
| --- | --- | --- |
| `voipcenter.start_call` | `sip_account_id`, `destination` | Click-to-dial: rings the SIP account, then calls the destination. Returns the conversation. |
| `voipcenter.end_call` | `conversation_id` | Hangs up an ongoing conversation. |
| `voipcenter.transfer_call` | `conversation_id`, `destination` | Transfers a conversation to an extension. |

The SIP account ID is in the `id` attribute of the account's *Call state*
sensor; conversation IDs are in the `conversations` attribute of *Ongoing calls*.

### Events

Every websocket `notify` message is fired as a `voipcenter` event, with the
call details as event data (plus `config_entry_id`). For example, to pause media
on an incoming call:

```yaml
triggers:
  - trigger: event
    event_type: voipcenter
actions:
  - action: media_player.media_pause
    target:
      entity_id: media_player.living_room
```

Use *Developer tools → Events* and listen to `voipcenter` to see the fields
your PBX sends.

## Installation

1. In HACS, add `https://github.com/bertouttier/voipcenter-hacs` as a
   [custom repository](https://hacs.xyz/docs/faq/custom_repositories) of type
   *Integration*.
2. Install **VoipCenter** and restart Home Assistant.
3. Go to *Settings → Devices & services → Add integration → VoipCenter*.

Requires Home Assistant 2026.10.4 or newer.

## Configuration

1. **API user** – the username and password of an API user of your VoipCenter
   account (used to obtain the APIv2 JWT token).
2. **Realtime call info** *(optional)* – the websocket server URL
   (`https://wsX.voipcenter.be:4123`, default `ws1`), the websocket username and
   the websocket key. They are pre-filled from the first websocket user found
   in *Config → Websockets*; leave the username empty to skip. You can change
   this later via *Configure* on the integration.

## Development

Against a Home Assistant core checkout next to this repository (`../core`, set
up with its `script/setup`, plus `uv pip install "python-socketio[asyncio_client]"`):

```bash
script/test_core.sh        # pytest, ruff and hassfest using core's tooling
```

Or standalone, with Python 3.14:

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

## References

- [VoipCenter APIv2: start, end or transfer a call](https://www.voipcenter.be/2021/12/31/een-gesprek-starten-via-de-voipcenter-apiv2/)
- [VoipCenter realtime call info via websocket](https://www.voipcenter.be/2022/02/04/realtime-call-info-via-websocket/)
