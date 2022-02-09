import voluptuous as vol
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

class VoipcenterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a KaaS config flow."""

    VERSION = 2

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_KLANTNUMMER],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(
                {
                    vol.Required(CONF_APIID): str,
                    vol.Required(CONF_APIKEY): str,
                    vol.Required(CONF_KLANTNUMMER): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_WS_USERNAME): str,
                }
            )
        )
