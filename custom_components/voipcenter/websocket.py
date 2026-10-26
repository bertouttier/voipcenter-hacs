"""Realtime call notifications via the VoipCenter Socket.IO websocket."""

import asyncio
from collections.abc import Callable
import contextlib
import json
import logging
from typing import Any

import socketio

_LOGGER = logging.getLogger(__name__)


class VoipCenterWebsocket:
    """Socket.IO client that registers and forwards ``notify`` events."""

    def __init__(
        self,
        url: str,
        username: str,
        key: str,
        on_notify: Callable[[dict[str, Any]], None],
        on_connection_change: Callable[[bool], None],
    ) -> None:
        """Initialize the websocket client."""
        self._url = url
        self._username = username
        self._key = key
        self._on_notify = on_notify
        self._on_connection_change = on_connection_change
        self._sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_delay=5,
            reconnection_delay_max=300,
        )
        self._sio.on("connect", self._handle_connect)
        self._sio.on("disconnect", self._handle_disconnect)
        self._sio.on("notify", self._handle_notify)
        self._sio.on("serveroutput", self._handle_serveroutput)

    @property
    def connected(self) -> bool:
        """Return whether the socket is connected."""
        return self._sio.connected

    async def run(self) -> None:
        """Keep trying to connect; the client reconnects on its own afterwards."""
        delay = 5
        while True:
            try:
                await self._sio.connect(self._url, transports=["websocket", "polling"])
            except socketio.exceptions.ConnectionError as err:
                _LOGGER.warning(
                    "Could not connect to %s: %s, retrying in %ss",
                    self._url,
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)
            else:
                return

    async def stop(self) -> None:
        """Disconnect."""
        await self._sio.disconnect()

    async def _register(self) -> None:
        # The server drops the connection when the credentials are wrong.
        await self._sio.emit(
            "register", {"username": self._username, "wskey": self._key}
        )

    async def _handle_connect(self) -> None:
        _LOGGER.debug("Connected to %s, registering as %s", self._url, self._username)
        await self._register()
        self._on_connection_change(True)

    async def _handle_serveroutput(self, data: Any) -> None:
        _LOGGER.debug("Server output: %s", data)

    async def _handle_disconnect(self, *args: Any) -> None:
        _LOGGER.debug("Disconnected from %s", self._url)
        self._on_connection_change(False)

    async def _handle_notify(self, calldetails: Any) -> None:
        if isinstance(calldetails, str):
            with contextlib.suppress(ValueError):
                calldetails = json.loads(calldetails)
        if not isinstance(calldetails, dict):
            calldetails = {"data": calldetails}
        _LOGGER.debug("Call notification: %s", calldetails)
        self._on_notify(calldetails)
