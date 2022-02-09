import logging
from typing import Any

from homeassistant.helpers.entity import ToggleEntity, generate_entity_id
from homeassistant.components.switch import ENTITY_ID_FORMAT
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class VoipcenterSwitch(ToggleEntity):
    """Representation of a switch to toggle on/off Voipcenter function indicators."""

    def __init__(self, hass, klantnummer, api, name, id):
        """Initialize the switch."""
        self._hass = hass
        self._api = api
        self._attr_name = name
        self._id = id
        self._attr_unique_id = f"fi_{klantnummer}_{self._id}"
        self._state = STATE_UNKNOWN
        self.entity_id = generate_entity_id(ENTITY_ID_FORMAT, f"fi_{klantnummer}_{self._id}", hass=hass)

    @property
    def should_poll(self):
        """Poll for status regularly."""
        return True

    @property
    def state(self):
        """Return the state of the function indicator if any."""
        return self._state

    @property
    def is_on(self):
        """Return true if function indicator is on."""
        return self._state == STATE_ON

    @property
    def device_info(self):
        return self._api.get_device_info()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the function indicator on."""
        _LOGGER.info('Turning on FI %s (%s)', self._attr_name, self._id)
        if (await self._api.activate_fi(self._id, True)) == False:
            _LOGGER.error('Could not turn on FI %s (%s)', self._attr_name, self._id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the function indicator off."""
        _LOGGER.info('Turning off FI %s (%s)', self._attr_name, self._id)
        if (await self._api.activate_fi(self._id, False)) == False:
            _LOGGER.error('Could not turn off FI %s (%s)', self._attr_name, self._id)

    async def async_update(self):
        """Update function indicator state."""
        _LOGGER.debug('Getting state for function indicator %s (%s)', self._attr_name, self._id)
        r = await self._api.get_fi(self._id)
        if r == None:
            _LOGGER.debug('No response received')
            self._state = STATE_UNKNOWN
        elif "actief" in r:
            actief = r['actief']
            _LOGGER.debug('Actief = %s', actief)
            self._state = STATE_ON if actief == '1' else STATE_OFF
        else:
            _LOGGER.error('Unexpected response')
            _LOGGER.debug(r)
            self._state = STATE_UNKNOWN
