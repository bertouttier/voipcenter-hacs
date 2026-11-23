"""Tests for the monthly call minutes sensors."""

from unittest.mock import AsyncMock

from aiovoipcenter import VoipCenterError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voipcenter.const import DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util


def _state(hass: HomeAssistant, unique_id: str):
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return hass.states.get(entity_id)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_minutes_sensors(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Outgoing minutes per SIP account and forwarded minutes per dialplan."""
    await _setup(hass, mock_config_entry)

    state = _state(hass, "apiuser_outgoing_minutes_471")
    assert state.state == "2.0"
    assert state.name == "Office phone Outgoing call minutes"
    assert state.attributes["unit_of_measurement"] == "min"
    assert state.attributes["state_class"] == "total"
    month_start = dt_util.start_of_local_day(dt_util.now().replace(day=1))
    assert state.attributes["last_reset"] == month_start.isoformat()
    assert state.attributes["calls"] == 2
    assert state.attributes["answered_calls"] == 1
    assert state.attributes["previous_month_minutes"] == 1.0
    assert state.attributes["previous_month_calls"] == 1

    state = _state(hass, "apiuser_forwarded_minutes_3609")
    assert state.state == "1.5"
    assert state.name == "VoipCenter apiuser papa_gsm forwarded call minutes"
    assert state.attributes["calls"] == 1
    assert state.attributes["numbers"] == ["32495000000"]
    assert state.attributes["previous_month_minutes"] == 0.0

    # The menu dialplan does not forward externally, so it has no sensor.
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "apiuser_forwarded_minutes_3612")
        is None
    )


async def test_routes_are_fetched_once(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Only calls answered without a SIP account get their route fetched, once."""
    await _setup(hass, mock_config_entry)
    fetched = sorted(
        call.args[0] for call in mock_client.get_call_route.await_args_list
    )
    assert fetched == [100, 101]

    await mock_config_entry.runtime_data.call_stats.async_refresh()
    await hass.async_block_till_done()

    assert mock_client.get_call_route.await_count == 2
    assert _state(hass, "apiuser_forwarded_minutes_3609").state == "1.5"


async def test_minutes_unavailable_on_error(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A failed call record poll makes only the minutes sensors unavailable."""
    mock_client.get_cdr_between.side_effect = VoipCenterError("down")
    await _setup(hass, mock_config_entry)

    assert _state(hass, "apiuser_outgoing_minutes_471").state == STATE_UNAVAILABLE
    assert _state(hass, "apiuser_call_state_471").state == "idle"
