# VoipCenter / PBXonline APIv2

This describes the parts of the VoipCenter (PBXonline) cloud APIv2 that the
integration uses, as observed against the live API in October 2026. The
official reference is the *VoipCenterAPIv2 end user* PDF (kept on the `docs`
branch); where the live API differs from it, this document follows the live API
and says so.

Code: [`custom_components/voipcenter/api.py`](../custom_components/voipcenter/api.py)
and [`websocket.py`](../custom_components/voipcenter/websocket.py).

## Base URL

```
https://api.pbxonline.be/v2/<version>
```

`<version>` is a release number of PBXonline, currently `261001`. The PDF and
older clients use `https://pbxonline.be/api/v2/1` (or `/v2/x`); that host now
returns `404` for every path.

The integration keeps the base URL up to date in two ways:

- every token response carries `latestApi` (see [Login](#login)); when it
  differs from the version in use, the integration switches to it;
- when the token request returns `404`, it reads the current base URL from the
  PBXonline web app, `https://pbxonline.be/v7/js/app.js`, which contains
  `axios.defaults.baseURL = "https://api.pbxonline.be/v2/<version>"`, and
  retries once.

## Headers

| Header          | Value                    | When                                   |
| --------------- | ------------------------ | -------------------------------------- |
| `Content-Type`  | `application/json`       | **Every** request, also `GET`. Without it the API answers `415` `{"error_number":"2","error_message":"Content-Type needs to be application/json"}`. |
| `Authorization` | `Bearer <token>`         | Every request except `token` and `refreshtoken`. |
| `X-CUID`        | customer ID              | Only for reseller / developer API users (not used). |
| `X-RUID`        | reseller ID              | Only for reseller / developer API users (not used). |

Responses are JSON, served as `text/json`. Some responses have stray HTML
before the JSON, so the integration parses from the first `{` or `[`.

## Login

### API user

Authentication uses an **API user** created in the PBXonline v7 portal under
*Developer → API* (`config/apiuser`). The credentials of the old v1 API
(`api_id` / `api_key`, e.g. `pi123456vc`) and the normal portal login do not
work.

### `POST token`

The password is **not** sent in plain text: the API expects
`sha256(md5(password))`, both as lowercase hex, which is what the web app
sends too. This is not in the PDF; a plain password is always rejected.

```python
md5 = hashlib.md5(password.encode()).hexdigest()
hashed = hashlib.sha256(md5.encode()).hexdigest()
```

Request:

```json
{"username": "<api user>", "password": "<sha256(md5(password))>"}
```

Response `200`:

```json
{
  "username": "<api user>",
  "latestApi": "261001",
  "isLatestVersion": true,
  "token": "<jwt>",
  "tokenExpires": 1793086114,
  "refreshToken": "<jwt>",
  "refreshTokenExpires": 1793258314
}
```

- `tokenExpires` / `refreshTokenExpires` are Unix timestamps. The token lasts
  10 minutes; the refresh token lasts 48 hours (the PDF says 60 minutes). The
  integration uses the timestamps rather than fixed lifetimes.
- `latestApi` / `isLatestVersion` are not in the PDF; see [Base URL](#base-url).

Wrong credentials, response `401`:

```json
[{"ID": 0, "status": "error",
  "error": {"errorType": "Authentication", "errorSubType": "",
            "error_number": "3", "error_message": "Incorrect credentials"},
  "succes": false}]
```

A body without `password` gives `400` with `errorType` `Missing fields`
(`error_number` `2`).

### `POST refreshtoken`

Request:

```json
{"refreshToken": "<refreshToken from token>"}
```

Response: the same object as `token` (including `latestApi`).

### How the integration uses the tokens

- It reuses the token until 30 seconds before `tokenExpires`.
- Then it calls `refreshtoken`; if that fails or the refresh token has
  expired, it logs in again with `token`.
- A request that gets `401` gets a new token and is retried once.
- `400`, `401` and `403` on `token` mean the credentials are wrong (the config
  flow shows *invalid authentication* and starts reauthentication); any other
  status is an API error.

## Errors

Errors come in two shapes:

```json
[{"ID": 0, "status": "error", "error": {"errorType": "...", "error_number": "3", "error_message": "..."}, "succes": false}]
```

```json
{"error_number": "3", "error_message": "Wrong authorisation: bearer"}
```

The first (a one-item list) is used by `token`; the second by authenticated
endpoints, e.g. a missing or expired token (`401`) or a missing
`Content-Type` (`415`). The integration reads `error_message` from either.

## Lists (`GET`)

All `GET` endpoints return a page of items:

```json
{
  "total": 6,
  "count": 6,
  "next": null,
  "previous": "?offset=0&limit=350",
  "results": [ ... ],
  "error": null
}
```

Pages hold up to 350 items, which is more than a single PBX has of the items
below, so the integration only reads the first page.

Passing `verbose=true` adds detail objects (`...Info` fields); the integration
doesn't use it.

## Endpoints

The integration polls the four `GET` endpoints every 30 seconds, in parallel.
`GET` requests that time out (15 s) or can't connect are retried once.

### `GET pbx/sipaccount` — SIP accounts

One item per SIP account (phone, softphone, ...). Fields used:

| Field          | Type    | Meaning                                         | Entity |
| -------------- | ------- | ----------------------------------------------- | ------ |
| `ID`           | int     | Unique ID; used as `origin` to start a call     | device |
| `logicalName`  | string  | Name                                            | device name |
| `sipUsername`  | string  | SIP username                                    | device serial, attribute |
| `extension`    | int     | Internal number                                 | attribute |
| `currentState` | string  | `idle`, `calling` or `ringing`                  | *Call state* sensor |
| `availability` | bool    | Presence: available or not                      | *Available* binary sensor |
| `isRegistered` | bool    | A SIP client is registered                      | *Registered* binary sensor |
| `userAgent`    | string  | User agent of the registered client             | attribute |
| `ipAddress`    | string  | Public IP of the registered client              | attribute |

The PDF calls the registration flag `regStatus` (plus `regStatusName`); the
live API returns `isRegistered` instead, and also `registerTs` (Unix time of
the last registration). The integration accepts both names.

Other fields returned (not used): `sirname`, `name`, `cidOut`, `isMasked`,
`sipPassword`, `mailAlert`, `countryCode`, `videoEnabled`, `webrtcEnabled`,
`ucEnabled`, `authCalling`, `location`, `encryption`, `transport`,
`contactHeader`, `language`, `mwiMailbox`, `cidrDeny`, `cidrAllow`, `codecs`,
`dtmfMode`, `sendSipOption`, `sipOptionFrequency`, `optionSeconds`,
`mohClassID`, `mohClassInfo`, `screenedNumber`, `canPage`, `recordOut`,
`recordInt`, `sipServer`, `dialgroup`, `dialoutGroup`, `groupMembership`,
`extensionInfo`.

### `GET pbx/functionindicator` — function indicators

Function indicators are green/red switches that change the dialplan (e.g.
"answering machine on").

| Field         | Type   | Meaning                       | Entity |
| ------------- | ------ | ----------------------------- | ------ |
| `ID`          | int    | Unique ID                     | |
| `logicalName` | string | Name                          | switch name |
| `extension`   | int    | Extension (2001–2999)         | attribute |
| `color`       | string | `green` or `red`              | switch: on = `red` |
| `description` | string | Description                   | attribute |

Not used: `useInDialplan`, `disableFi`, `playPrompt`, `stateGreen`, `stateRed`
(the actions run in each state), `webhook`, `hasErrorMessage`.

### `GET pbx/voicemail` — voicemail boxes

| Field         | Type   | Meaning                          | Entity |
| ------------- | ------ | -------------------------------- | ------ |
| `ID`          | int    | Unique ID                        | |
| `logicalName` | string | Name                             | sensor name |
| `extension`   | int    | Mailbox number (1001–1999)       | attribute |
| `messages`    | object | Number of messages per folder    | *Voicemail messages* sensor |

The PDF describes `messages` as a number; the live API returns the count per
folder, e.g. `{"inbox": 3, "logging": 0}`, and also
`"inbox": {"total": 3, "listen": 0}`. The sensor shows `messages.inbox` and
adds the other folders as `<folder>_messages` attributes; a plain number is
still accepted.

Not used: `altMailbox`, `passwordSet`, `password`, `language`, `promptID`,
`promptInfo`, `deleteVM`, `sayTime`, `sayCid`, `altSubject`, `sendMail`,
`mailTo`, `smstoolsID`, `mailAlert`, `webhook`, `altMailboxInfo`.

### `GET action/conversation` — ongoing calls

One item per ongoing conversation; an empty `results` list when nobody is on
the phone. Fields (from the PDF; not yet seen live with a call):

| Field         | Type   | Meaning                                              |
| ------------- | ------ | ---------------------------------------------------- |
| `ID`          | int    | Conversation ID; used to end or transfer the call    |
| `direction`   | string | `in` or `out`                                        |
| `origin`      | string | SIP account ID (out) or caller number (in)           |
| `destination` | string | Number called (out) or DID (in)                      |
| `viaDid`      | string | DID the call goes over                               |
| `timestamp`   | int    | Start of the call (Unix time)                        |
| `inCall`      | bool   | Whether the call has been answered                   |

The integration counts the items (*Ongoing calls* sensor, *In call* binary
sensor) and adds the list as an attribute.

### `GET config/websocket` — websocket users

Used once, by the config flow and options flow, to pre-fill the websocket
credentials (the first item with `isActive` true).

| Field            | Type   | Meaning                                         |
| ---------------- | ------ | ----------------------------------------------- |
| `ID`             | int    | Unique ID                                       |
| `logicalName`    | string | Name                                            |
| `isActive`       | bool   | Whether the user can connect                    |
| `wsUsername`     | string | Username for the websocket `register`           |
| `wsKey`          | string | Key (password) for the websocket `register`     |
| `onStatusChange` | bool   | Also send events on status changes              |
| `applyToSip`     | list   | SIP account IDs that trigger events             |
| `applyToDid`     | list   | DID IDs that trigger events                     |

### `PUT action/functionindicator` — set a function indicator

Request, keyed by the indicator `ID`:

```json
{"2719": {"state": "red"}}
```

`state` is `green`, `red`, or `null` to toggle. The switch sends `red` for on
and `green` for off, then updates its state without waiting for the next poll.

### `POST action/conversation` — start a call (click-to-dial)

Rings SIP account `origin` and, when it is answered, calls `destination`.
The key (`call-1`) is a free label for the new item.

```json
{"call-1": {"origin": 471, "destination": "0470123456"}}
```

The response holds the new conversation; the integration returns its first item
as the response of the `voipcenter.start_call` action.

### `PUT action/conversation` — transfer a call

Keyed by the conversation `ID`; `destination` is an internal extension.

```json
{"9570231": {"destination": "6"}}
```

### `DELETE action/conversation` — end a call

```json
{"ID": 9570231}
```

## Realtime call info (websocket)

Calls are pushed over [Socket.IO](https://socket.io/) (Engine.IO protocol 4;
protocol 3 works as well).

### Server

```
https://wsX.pbxonline.be:4123
```

`X` is the server number: `ws1`, `ws2` and `ws3` all answer. The blog post and
the 1.x integration use `wsX.voipcenter.be`; that name still reaches the same
servers, but their TLS certificate only covers `wsX.pbxonline.be`, so the
connection fails certificate verification. The integration rewrites stored
`voipcenter.be` URLs to `pbxonline.be`.

### Flow

1. Connect. The server emits `serveroutput`:
   `Connection! Please send 'register' with valid credentials.`
2. Emit `register` with the credentials of a websocket user (see
   `config/websocket`); the server disconnects clients that don't:

   ```json
   {"username": "<wsUsername>", "wskey": "<wsKey>"}
   ```

3. The server confirms with another `serveroutput`:

   ```
   {"error":0, "error_message":"", "success_message":"<wsUsername> now registered, "socket":"<id>"}
   ```

   (not valid JSON, so the integration only logs `serveroutput`).
4. For every incoming or outgoing call on the SIP accounts and DIDs selected for
   the websocket user, the server emits `notify` with the call details. The
   fields are not documented; the integration parses the payload as JSON when
   it is a string and fires it unchanged as a `voipcenter` event on the Home
   Assistant event bus (with `config_entry_id` added), and keeps the last one
   in the *Last call event* sensor. It also polls the API right away, so the
   call sensors update immediately.

The integration registers again after every reconnect, and retries a failed
connection with a backoff from 5 seconds up to 5 minutes.

## Quick test with curl

```sh
BASE=https://api.pbxonline.be/v2/261001
HASH=$(printf %s "$(printf %s "$PASSWORD" | md5)" | shasum -a 256 | cut -d' ' -f1)  # macOS; use md5sum on Linux
TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"$API_USER\",\"password\":\"$HASH\"}" $BASE/token | jq -r .token)
curl -s -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
  $BASE/pbx/sipaccount | jq '.results[] | {ID, logicalName, currentState, isRegistered}'
```
