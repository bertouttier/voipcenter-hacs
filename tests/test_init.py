"""Tests for setting up VoipCenter and its entities and services."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.voipcenter.const import (
    CONF_WS_KEY,
    CONF_WS_URL,
    CONF_WS_USERNAME,
    DEFAULT_WS_URL,
    DOMAIN,
    EVENT_CALL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


async def test_setup_creates_entities(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Entities reflect the polled PBX state."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    state = hass.states.get(_entity_id(hass, "sensor", "apiuser_ongoing_calls"))
    assert state.state == "1"
    state = hass.states.get(_entity_id(hass, "sensor", "apiuser_call_state_471"))
    assert state.state == "idle"
    assert state.attributes["id"] == 471
    state = hass.states.get(_entity_id(hass, "binary_sensor", "apiuser_registered_471"))
    assert state.state == STATE_ON
    state = hass.states.get(_entity_id(hass, "sensor", "apiuser_voicemail_messages_12"))
    assert state.state == "3"
    assert state.name == "VoipCenter apiuser Main voicemail messages"

    switch_id = _entity_id(hass, "switch", "apiuser_function_indicator_2719")
    state = hass.states.get(switch_id)
    assert state.state == STATE_OFF
    assert state.name == "VoipCenter apiuser Night mode"

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_function_indicator_switch(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Turning the switch on sets the indicator to red."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    switch_id = _entity_id(hass, "switch", "apiuser_function_indicator_2719")

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: switch_id}, blocking=True
    )
    mock_client.set_function_indicator.assert_awaited_once_with(2719, "red")


async def test_services(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The call services reach the API client."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "start_call",
        {"sip_account_id": 471, "destination": "0470123456"},
        blocking=True,
        return_response=True,
    )
    assert response == {"ID": 1234}
    mock_client.start_call.assert_awaited_once_with(471, "0470123456")

    await hass.services.async_call(
        DOMAIN,
        "transfer_call",
        {"conversation_id": 9570231, "destination": "6"},
        blocking=True,
    )
    mock_client.transfer_call.assert_awaited_once_with(9570231, "6")

    await hass.services.async_call(
        DOMAIN, "end_call", {"conversation_id": 9570231}, blocking=True
    )
    mock_client.end_call.assert_awaited_once_with(9570231)


async def test_websocket_events(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Websocket notifications fire events and update the last call sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        unique_id="apiuser",
        data={"username": "apiuser", "password": "secret"},
        options={
            CONF_WS_URL: DEFAULT_WS_URL,
            CONF_WS_USERNAME: "wsuser",
            CONF_WS_KEY: "wskey",
        },
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.voipcenter.VoipCenterWebsocket", autospec=True
    ) as ws_cls:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    url, username, key, on_notify, on_connection = ws_cls.call_args.args
    assert (url, username, key) == (DEFAULT_WS_URL, "wsuser", "wskey")

    events = async_capture_events(hass, EVENT_CALL)
    on_connection(True)
    on_notify({"callid": "abc", "status": "ringing"})
    await hass.async_block_till_done()

    assert events[0].data == {
        "config_entry_id": entry.entry_id,
        "callid": "abc",
        "status": "ringing",
    }
    state = hass.states.get(_entity_id(hass, "sensor", "apiuser_last_call_event"))
    assert state.attributes["status"] == "ringing"
    state = hass.states.get(_entity_id(hass, "binary_sensor", "apiuser_websocket"))
    assert state.state == STATE_ON


async def test_migrate_v1_entry(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """A 1.x entry is migrated and asks for an APIv2 user via reauth."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="170703",
        data={
            "api_id": "170703api",
            "api_key": "old-key",
            "klantnummer": "170703",
            "password": "old-password",
            "ws_username": "wsuser",
        },
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 3
    assert entry.data == {}
    assert entry.options == {CONF_WS_URL: DEFAULT_WS_URL, CONF_WS_USERNAME: "wsuser"}
    assert entry.state is ConfigEntryState.SETUP_ERROR

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_api_user"

    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {"username": "apiuser", "password": "secret"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == "apiuser"
    assert entry.data == {"username": "apiuser", "password": "secret"}
    assert entry.state is ConfigEntryState.LOADED
