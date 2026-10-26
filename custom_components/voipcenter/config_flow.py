"""Config flow for the VoipCenter integration."""

from collections.abc import Mapping
import logging
from typing import Any

import probatio

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    VoipCenterAuthError,
    VoipCenterClient,
    VoipCenterConnectionError,
    VoipCenterError,
)
from .const import CONF_WS_KEY, CONF_WS_URL, CONF_WS_USERNAME, DEFAULT_WS_URL, DOMAIN
from .coordinator import VoipCenterConfigEntry

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

CREDENTIALS_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_USERNAME): str,
        probatio.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)


def _websocket_schema(defaults: Mapping[str, Any]) -> probatio.Schema:
    return probatio.Schema(
        {
            probatio.Required(
                CONF_WS_URL, default=defaults.get(CONF_WS_URL) or DEFAULT_WS_URL
            ): str,
            probatio.Optional(
                CONF_WS_USERNAME,
                description={"suggested_value": defaults.get(CONF_WS_USERNAME)},
            ): str,
            probatio.Optional(
                CONF_WS_KEY,
                description={"suggested_value": defaults.get(CONF_WS_KEY)},
            ): PASSWORD_SELECTOR,
        }
    )


async def _async_discover_websocket(client: VoipCenterClient) -> dict[str, str]:
    """Suggest the first (active) websocket user from config/websocket."""
    try:
        users = await client.get_websocket_users()
    except VoipCenterError as err:
        _LOGGER.debug("Could not read websocket users: %s", err)
        return {}
    users = [user for user in users if user.get("wsUsername")]
    users.sort(key=lambda user: not user.get("isActive", True))
    if not users:
        return {}
    return {
        CONF_WS_USERNAME: str(users[0]["wsUsername"]),
        CONF_WS_KEY: str(users[0].get("wsKey") or ""),
    }


class VoipCenterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VoipCenter."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, str] = {}
        self._websocket_defaults: dict[str, str] = {}

    async def _async_validate(
        self, user_input: Mapping[str, Any]
    ) -> tuple[VoipCenterClient | None, dict[str, str]]:
        client = VoipCenterClient(
            async_get_clientsession(self.hass),
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
        )
        try:
            await client.authenticate()
            await client.get_sip_accounts()
        except VoipCenterAuthError:
            return None, {"base": "invalid_auth"}
        except VoipCenterConnectionError:
            return None, {"base": "cannot_connect"}
        except VoipCenterError:
            _LOGGER.exception("Unexpected VoipCenter response")
            return None, {"base": "unknown"}
        return client, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API username and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()
            client, errors = await self._async_validate(user_input)
            if client is not None:
                self._data = user_input
                self._websocket_defaults = await _async_discover_websocket(client)
                return await self.async_step_websocket()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_websocket(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optionally configure the realtime websocket."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"VoipCenter {self._data[CONF_USERNAME]}",
                data=self._data,
                options=user_input,
            )
        return self.async_show_form(
            step_id="websocket",
            data_schema=_websocket_schema(self._websocket_defaults),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle rejected (or, after migrating from 1.x, missing) credentials."""
        if CONF_USERNAME not in entry_data:
            return await self.async_step_reauth_api_user()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            client, errors = await self._async_validate(data)
            if client is not None:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_PASSWORD): PASSWORD_SELECTOR}
            ),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    async def async_step_reauth_api_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for an APIv2 user for an entry migrated from 1.x."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()
            client, errors = await self._async_validate(user_input)
            if client is not None:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=user_input[CONF_USERNAME],
                    title=f"VoipCenter {user_input[CONF_USERNAME]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="reauth_api_user",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, user_input
            ),
            description_placeholders={"title": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: VoipCenterConfigEntry,
    ) -> VoipCenterOptionsFlow:
        """Return the options flow."""
        return VoipCenterOptionsFlow()


class VoipCenterOptionsFlow(OptionsFlowWithReload):
    """Change the websocket settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the websocket settings."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        defaults: Mapping[str, Any] = self.config_entry.options
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if not defaults.get(CONF_WS_KEY) and coordinator is not None:
            defaults = await _async_discover_websocket(coordinator.client)
        return self.async_show_form(
            step_id="init", data_schema=_websocket_schema(defaults)
        )
