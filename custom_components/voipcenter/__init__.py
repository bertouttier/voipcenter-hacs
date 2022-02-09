import logging

from homeassistant import config_entries

from homeassistant.const import (
    CONF_PASSWORD
)

from .const import (
    DOMAIN,
    CONF_APIID,
    CONF_APIKEY,
    CONF_KLANTNUMMER,
    CONF_WS_USERNAME
)
from .voipcenter import VoipcenterApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    """Set up a backend from a config entry."""
    hass.data[DOMAIN][entry.entry_id] = entry.data

    klantnummer = entry.data[CONF_KLANTNUMMER]
    api = hass.data[DOMAIN].get(klantnummer)

    # Connect to each backend in the config and
    if not api:
        _LOGGER.debug("API {} does not exist yet".format(klantnummer))
        api = VoipcenterApi(
            hass,
            entry.data[CONF_APIID],
            entry.data[CONF_APIKEY],
            klantnummer,
            entry.data[CONF_PASSWORD],
            entry.data.get(CONF_WS_USERNAME)
        )
        hass.data[DOMAIN][klantnummer] = api
        _LOGGER.info("API {} has been set up".format(klantnummer))
        await api.connect_ws()
    else:
        _LOGGER.debug("API {} already exists".format(klantnummer))

    # create the function indicators
    hass.config_entries.async_setup_platforms(entry, ["switch"])

    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    klantnummer = entry.data[CONF_KLANTNUMMER]
    api = hass.data[DOMAIN].pop(klantnummer)
    await api.disconnect_ws()
    _LOGGER.debug("Unload API {}".format(klantnummer))
    return True

async def async_setup(hass, config):
    """Set up Key as a Service."""
    _LOGGER.info("Starting up Voipcenter component")
    hass.data.setdefault(DOMAIN, {})
    return True
