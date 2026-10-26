"""Tests for the VoipCenter config flow."""

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voipcenter.api import VoipCenterAuthError
from custom_components.voipcenter.const import (
    CONF_WS_KEY,
    CONF_WS_URL,
    CONF_WS_USERNAME,
    DEFAULT_WS_URL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

CREDENTIALS = {CONF_USERNAME: "apiuser", CONF_PASSWORD: "secret"}


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_with_websocket(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """The websocket step is pre-filled from config/websocket."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "websocket"
    schema = {str(key): key for key in result["data_schema"].schema}
    assert schema[CONF_WS_USERNAME].description == {"suggested_value": "wsuser"}

    ws = {CONF_WS_URL: DEFAULT_WS_URL, CONF_WS_USERNAME: "wsuser", CONF_WS_KEY: "wskey"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], ws)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CREDENTIALS
    assert result["options"] == ws
    assert result["result"].unique_id == "apiuser"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_invalid_auth(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Rejected credentials show an error and can be retried."""
    mock_client.authenticate.side_effect = VoipCenterAuthError("nope")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.authenticate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["step_id"] == "websocket"


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The same API user can only be added once."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reauthentication stores the new password."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-secret"
