"""Async client for the VoipCenter (PBXonline) APIv2."""

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Renew tokens this many seconds before they expire.
TOKEN_EXPIRY_MARGIN = 30


class VoipCenterError(Exception):
    """Generic VoipCenter API error."""


class VoipCenterConnectionError(VoipCenterError):
    """The API could not be reached."""


class VoipCenterAuthError(VoipCenterError):
    """The API username / password were rejected."""


def _parse_body(text: str) -> Any:
    """Parse a response body.

    The API answers with ``text/json`` and sometimes prefixes the JSON with
    stray HTML, so parse from the first ``{`` or ``[`` onwards.
    """
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return text
    try:
        return json.loads(text[min(starts) :])
    except ValueError:
        return text


def _error_message(body: Any) -> str:
    """Extract an error message from an error response."""
    if isinstance(body, dict):
        if "error_message" in body:
            return str(body["error_message"])
        error = body.get("error")
        if isinstance(error, dict) and "errorMessage" in error:
            return str(error["errorMessage"])
    return str(body)[:200]


def _results(body: Any) -> list[dict[str, Any]]:
    """Return the list of items of a GET response."""
    if isinstance(body, dict):
        body = body.get("results", [])
    if isinstance(body, dict):
        body = list(body.values())
    return (
        [item for item in body if isinstance(item, dict)]
        if isinstance(body, list)
        else []
    )


class VoipCenterClient:
    """Client for the VoipCenter APIv2, authenticating with an API user."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_expires = 0.0
        self._refresh_token: str | None = None
        self._refresh_token_expires = 0.0
        self._auth_lock = asyncio.Lock()

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        json_data: Any = None,
        params: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._session.request(
                method,
                f"{API_BASE_URL}/{path}",
                json=json_data,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                return resp.status, _parse_body(await resp.text())
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VoipCenterConnectionError(
                f"Error communicating with VoipCenter: {err}"
            ) from err

    def _store_tokens(self, status: int, body: Any) -> bool:
        if status != 200 or not isinstance(body, dict) or not body.get("token"):
            return False
        now = time.time()
        self._token = body["token"]
        # Token is valid for 10 minutes, the refresh token for 60 minutes.
        self._token_expires = float(body.get("tokenExpires") or now + 600)
        self._refresh_token = body.get("refreshToken")
        self._refresh_token_expires = float(
            body.get("refreshTokenExpires") or now + 3600
        )
        return True

    async def authenticate(self) -> None:
        """Get a fresh token pair using the API username and password."""
        status, body = await self._raw_request(
            "POST",
            "token",
            json_data={"username": self._username, "password": self._password},
        )
        if not self._store_tokens(status, body):
            if status >= 500:
                raise VoipCenterError(
                    f"Token request failed ({status}): {_error_message(body)}"
                )
            raise VoipCenterAuthError(_error_message(body))

    async def _ensure_token(self, failed_token: str | None = None) -> str:
        """Return a valid token, refreshing or re-authenticating as needed."""
        async with self._auth_lock:
            now = time.time()
            if (
                self._token
                and self._token != failed_token
                and self._token_expires - TOKEN_EXPIRY_MARGIN > now
            ):
                return self._token
            if (
                self._refresh_token
                and self._refresh_token_expires - TOKEN_EXPIRY_MARGIN > now
            ):
                status, body = await self._raw_request(
                    "POST",
                    "refreshtoken",
                    json_data={"refreshToken": self._refresh_token},
                )
                if self._store_tokens(status, body):
                    return self._token  # type: ignore[return-value]
                _LOGGER.debug("Refresh token rejected, re-authenticating")
            await self.authenticate()
            return self._token  # type: ignore[return-value]

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_data: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Do an authenticated request, renewing the token once on a 401."""
        token = await self._ensure_token()
        status, body = await self._raw_request(
            method, path, json_data=json_data, params=params, token=token
        )
        if status == 401:
            token = await self._ensure_token(failed_token=token)
            status, body = await self._raw_request(
                method, path, json_data=json_data, params=params, token=token
            )
            if status == 401:
                raise VoipCenterAuthError(_error_message(body))
        if not 200 <= status < 300:
            raise VoipCenterError(
                f"{method} {path} failed ({status}): {_error_message(body)}"
            )
        return body

    async def get_sip_accounts(self) -> list[dict[str, Any]]:
        """Return the SIP accounts, including state and registration status."""
        return _results(await self.request("GET", "pbx/sipaccount"))

    async def get_function_indicators(self) -> list[dict[str, Any]]:
        """Return the function indicators and their color (green / red)."""
        return _results(await self.request("GET", "pbx/functionindicator"))

    async def get_voicemailboxes(self) -> list[dict[str, Any]]:
        """Return the voicemail boxes, including their number of messages."""
        return _results(await self.request("GET", "pbx/voicemail"))

    async def get_conversations(self) -> list[dict[str, Any]]:
        """Return the ongoing conversations."""
        return _results(await self.request("GET", "action/conversation"))

    async def get_websocket_users(self) -> list[dict[str, Any]]:
        """Return the websocket users (``wsUsername`` / ``wsKey``)."""
        return _results(await self.request("GET", "config/websocket"))

    async def set_function_indicator(self, indicator_id: int, state: str | None) -> Any:
        """Set a function indicator to ``green`` or ``red``, or toggle it (None)."""
        return await self.request(
            "PUT",
            "action/functionindicator",
            json_data={str(indicator_id): {"state": state}},
        )

    async def start_call(self, sip_account_id: int, destination: str) -> Any:
        """Ring a SIP account and connect it to a destination (click-to-dial)."""
        body = await self.request(
            "POST",
            "action/conversation",
            json_data={
                "call-1": {"origin": sip_account_id, "destination": destination}
            },
        )
        if isinstance(body, list) and body:
            return body[0]
        return body

    async def end_call(self, conversation_id: int) -> Any:
        """Hang up an ongoing conversation."""
        return await self.request(
            "DELETE", "action/conversation", json_data={"ID": conversation_id}
        )

    async def transfer_call(self, conversation_id: int, destination: str) -> Any:
        """Transfer an ongoing conversation to another extension."""
        return await self.request(
            "PUT",
            "action/conversation",
            json_data={str(conversation_id): {"destination": destination}},
        )
