"""Data coordinator for the VoipCenter integration."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import VoipCenterAuthError, VoipCenterClient, VoipCenterError
from .const import DOMAIN, EVENT_CALL, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type VoipCenterConfigEntry = ConfigEntry[VoipCenterCoordinator]


def _by_id(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Index API items by their integer ``ID``."""
    indexed: dict[int, dict[str, Any]] = {}
    for item in items:
        try:
            indexed[int(item["ID"])] = item
        except KeyError, TypeError, ValueError:
            continue
    return indexed


@dataclass
class VoipCenterData:
    """Data fetched from VoipCenter."""

    sip_accounts: dict[int, dict[str, Any]] = field(default_factory=dict)
    function_indicators: dict[int, dict[str, Any]] = field(default_factory=dict)
    voicemailboxes: dict[int, dict[str, Any]] = field(default_factory=dict)
    conversations: list[dict[str, Any]] = field(default_factory=list)
    last_call_event: dict[str, Any] | None = None
    last_call_event_time: datetime | None = None
    websocket_connected: bool = False


class VoipCenterCoordinator(DataUpdateCoordinator[VoipCenterData]):
    """Polls the PBX state and merges in realtime websocket events."""

    config_entry: VoipCenterConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VoipCenterConfigEntry,
        client: VoipCenterClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._state = VoipCenterData()

    async def _async_update_data(self) -> VoipCenterData:
        try:
            (
                sip_accounts,
                function_indicators,
                voicemailboxes,
                conversations,
            ) = await asyncio.gather(
                self.client.get_sip_accounts(),
                self.client.get_function_indicators(),
                self.client.get_voicemailboxes(),
                self.client.get_conversations(),
            )
        except VoipCenterAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VoipCenterError as err:
            raise UpdateFailed(str(err)) from err
        self._state.sip_accounts = _by_id(sip_accounts)
        self._state.function_indicators = _by_id(function_indicators)
        self._state.voicemailboxes = _by_id(voicemailboxes)
        self._state.conversations = conversations
        return self._state

    async def async_set_function_indicator(
        self, indicator_id: int, state: str | None
    ) -> None:
        """Set a function indicator and refresh."""
        await self.client.set_function_indicator(indicator_id, state)
        if state and indicator_id in self._state.function_indicators:
            # Optimistic update; the next poll confirms it.
            self._state.function_indicators[indicator_id]["color"] = state
            self.async_set_updated_data(self._state)
        await self.async_request_refresh()

    @callback
    def handle_call_event(self, calldetails: dict[str, Any]) -> None:
        """Handle a realtime call notification from the websocket."""
        self._state.last_call_event = calldetails
        self._state.last_call_event_time = dt_util.utcnow()
        self.hass.bus.async_fire(
            EVENT_CALL, {"config_entry_id": self.config_entry.entry_id, **calldetails}
        )
        self.async_set_updated_data(self._state)
        # Call state changed, so poll SIP account states and conversations now.
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def handle_websocket_connection(self, connected: bool) -> None:
        """Track the websocket connection state."""
        self._state.websocket_connected = connected
        self.async_set_updated_data(self._state)
