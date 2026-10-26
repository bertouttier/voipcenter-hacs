"""Services for the VoipCenter integration."""

from typing import Any

import probatio

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import VoipCenterError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONVERSATION_ID,
    ATTR_DESTINATION,
    ATTR_SIP_ACCOUNT_ID,
    DOMAIN,
    SERVICE_END_CALL,
    SERVICE_START_CALL,
    SERVICE_TRANSFER_CALL,
)
from .coordinator import VoipCenterCoordinator

_BASE_SCHEMA = {probatio.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}

START_CALL_SCHEMA = probatio.Schema(
    {
        **_BASE_SCHEMA,
        probatio.Required(ATTR_SIP_ACCOUNT_ID): probatio.Coerce(int),
        probatio.Required(ATTR_DESTINATION): cv.string,
    }
)
END_CALL_SCHEMA = probatio.Schema(
    {**_BASE_SCHEMA, probatio.Required(ATTR_CONVERSATION_ID): probatio.Coerce(int)}
)
TRANSFER_CALL_SCHEMA = probatio.Schema(
    {
        **_BASE_SCHEMA,
        probatio.Required(ATTR_CONVERSATION_ID): probatio.Coerce(int),
        probatio.Required(ATTR_DESTINATION): cv.string,
    }
)


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> VoipCenterCoordinator:
    """Return the coordinator of the targeted (or only loaded) config entry."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_config_entry"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="multiple_config_entries"
        )
    return entries[0].runtime_data


def _as_response(result: Any) -> ServiceResponse:
    if isinstance(result, dict):
        return result
    return {"result": result}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the VoipCenter services."""

    async def start_call(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call)
        try:
            result = await coordinator.client.start_call(
                call.data[ATTR_SIP_ACCOUNT_ID], call.data[ATTR_DESTINATION]
            )
        except VoipCenterError as err:
            raise HomeAssistantError(f"Could not start call: {err}") from err
        await coordinator.async_request_refresh()
        return _as_response(result)

    async def end_call(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call)
        try:
            result = await coordinator.client.end_call(call.data[ATTR_CONVERSATION_ID])
        except VoipCenterError as err:
            raise HomeAssistantError(f"Could not end call: {err}") from err
        await coordinator.async_request_refresh()
        return _as_response(result)

    async def transfer_call(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call)
        try:
            result = await coordinator.client.transfer_call(
                call.data[ATTR_CONVERSATION_ID], call.data[ATTR_DESTINATION]
            )
        except VoipCenterError as err:
            raise HomeAssistantError(f"Could not transfer call: {err}") from err
        await coordinator.async_request_refresh()
        return _as_response(result)

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_CALL,
        start_call,
        schema=START_CALL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_END_CALL,
        end_call,
        schema=END_CALL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRANSFER_CALL,
        transfer_call,
        schema=TRANSFER_CALL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
