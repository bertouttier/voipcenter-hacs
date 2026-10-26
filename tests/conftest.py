"""Fixtures for the VoipCenter tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voipcenter.const import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

SIP_ACCOUNTS = [
    {
        "ID": 471,
        "logicalName": "Office phone",
        "sipUsername": "abc123",
        "extension": 1,
        "currentState": "idle",
        "availability": True,
        "regStatus": True,
    }
]
FUNCTION_INDICATORS = [
    {"ID": 2719, "logicalName": "Night mode", "extension": 2001, "color": "green"}
]
VOICEMAILBOXES = [{"ID": 12, "logicalName": "Main", "extension": 1001, "messages": 3}]
CONVERSATIONS = [
    {"ID": 9570231, "direction": "in", "origin": "32470123456", "inCall": True}
]
WEBSOCKET_USERS = [
    {
        "ID": 21,
        "logicalName": "HA",
        "wsUsername": "wsuser",
        "wsKey": "wskey",
        "isActive": True,
    }
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations."""
    return


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Mock the VoipCenter API client in both the integration and the flow."""
    with (
        patch(
            "custom_components.voipcenter.VoipCenterClient", autospec=True
        ) as client_cls,
        patch(
            "custom_components.voipcenter.config_flow.VoipCenterClient", new=client_cls
        ),
    ):
        client = client_cls.return_value
        client.get_sip_accounts.return_value = SIP_ACCOUNTS
        client.get_function_indicators.return_value = FUNCTION_INDICATORS
        client.get_voicemailboxes.return_value = VOICEMAILBOXES
        client.get_conversations.return_value = CONVERSATIONS
        client.get_websocket_users.return_value = WEBSOCKET_USERS
        client.start_call.return_value = {"ID": 1234}
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Don't set up the entry created by the config flow."""
    with patch(
        "custom_components.voipcenter.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry without websocket."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="VoipCenter apiuser",
        version=3,
        unique_id="apiuser",
        data={CONF_USERNAME: "apiuser", CONF_PASSWORD: "secret"},
        options={},
    )
