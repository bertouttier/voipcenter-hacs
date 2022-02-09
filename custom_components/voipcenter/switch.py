import logging
from datetime import timedelta

from .const import (
    DOMAIN,
    CONF_KLANTNUMMER
)

from .entity import VoipcenterSwitch

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

async def async_setup_entry(hass, config_entry, async_add_entities):
    klantnummer = config_entry.data[CONF_KLANTNUMMER]
    api = hass.data[DOMAIN].get(klantnummer)

    entities = []

    if api:
        all_fi = await api.get_fi('0')
        entities = [VoipcenterSwitch(hass, klantnummer, api, value, key.split('_')[1]) for key, value in all_fi.items()]

    async_add_entities(entities)