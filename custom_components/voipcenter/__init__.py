"""The VoipCenter integration."""

import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import VoipCenterClient
from .const import CONF_WS_KEY, CONF_WS_URL, CONF_WS_USERNAME, DEFAULT_WS_URL, DOMAIN
from .coordinator import VoipCenterConfigEntry, VoipCenterCoordinator
from .services import async_setup_services
from .websocket import VoipCenterWebsocket

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the VoipCenter services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: VoipCenterConfigEntry) -> bool:
    """Set up VoipCenter from a config entry."""
    if CONF_USERNAME not in entry.data:
        # Migrated from 1.x: ask for an APIv2 user via the reauth flow.
        raise ConfigEntryAuthFailed("An APIv2 username and password are required")
    client = VoipCenterClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = VoipCenterCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    options = entry.options
    if options.get(CONF_WS_USERNAME) and options.get(CONF_WS_KEY):
        websocket = VoipCenterWebsocket(
            options[CONF_WS_URL],
            options[CONF_WS_USERNAME],
            options[CONF_WS_KEY],
            coordinator.handle_call_event,
            coordinator.handle_websocket_connection,
        )
        entry.async_create_background_task(
            hass, websocket.run(), f"{DOMAIN}_websocket_{entry.entry_id}"
        )
        entry.async_on_unload(websocket.stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: VoipCenterConfigEntry
) -> bool:
    """Migrate a 1.x (v1 API) entry; its credentials don't work with APIv2."""
    if entry.version > 3:
        return False
    if entry.version < 3:
        options = {}
        if ws_username := entry.data.get(CONF_WS_USERNAME):
            # The websocket key used to be fetched via the v1 API; it is
            # suggested again from config/websocket in the options flow.
            options = {CONF_WS_URL: DEFAULT_WS_URL, CONF_WS_USERNAME: ws_username}
        hass.config_entries.async_update_entry(
            entry, data={}, options=options, version=3
        )
        _LOGGER.info(
            "Migrated VoipCenter entry %s from v1 API; re-enter an APIv2 user",
            entry.title,
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoipCenterConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
