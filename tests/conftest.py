"""Fixtures for the VoipCenter tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from aiovoipcenter.types import (
    CallEvent,
    CallRecord,
    Conversation,
    Dialplan,
    FunctionIndicator,
    SipAccount,
    Voicemail,
    WebsocketUser,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.voipcenter.const import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.util import dt as dt_util

SIP_ACCOUNTS = [
    {
        "ID": 471,
        "logicalName": "Office phone",
        "sipUsername": "abc123",
        "extension": 1,
        "currentState": "idle",
        "availability": True,
        "isRegistered": True,
    }
]
FUNCTION_INDICATORS = [
    {"ID": 2719, "logicalName": "Night mode", "extension": 2001, "color": "green"}
]
VOICEMAILBOXES = [
    {
        "ID": 12,
        "logicalName": "Main",
        "extension": 1001,
        "messages": {"inbox": 3, "logging": 0},
    }
]
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

DIALPLANS = [
    {
        "ID": 3609,
        "logicalName": "papa_gsm",
        "steps": [{"step": 1, "action": "externalNumber"}],
    },
    {"ID": 3612, "logicalName": "menu", "steps": [{"step": 1, "action": "ivr"}]},
]
OFFICE = {"ID": 471, "logicalName": "Office phone", "sipUsername": "abc123"}
TRUNK = {"ID": 1728, "did": "3220000000", "logicalName": "main"}


def _call(call_id: int, direction: str, talk: int, **extra: object) -> dict:
    """Return a raw CDR that started an hour after the start of its month."""
    return {
        "ID": call_id,
        "callDirection": direction,
        "status": "answered" if talk else "unanswered",
        "isAnswered": bool(talk),
        "answerTs": 3610 if talk else 0,
        "endTs": 3610 + talk,
        "handledbyInfo": TRUNK,
        **extra,
    }


# This month: 120 s outgoing (plus an unanswered try) from the office phone,
# an incoming call answered by it, one forwarded by papa_gsm (90 s), one
# answered by voicemail, an old one whose route PBXonline no longer has and a
# call that just ended whose route is not there yet.
CURRENT_CALLS = [
    _call(1, "outgoing", 120, originInfo=OFFICE),
    _call(2, "outgoing", 0, originInfo=OFFICE),
    _call(3, "incoming", 300, answeredbyInfo=OFFICE),
    _call(100, "incoming", 90, answeredBy=""),
    _call(101, "incoming", 30, answeredBy=""),
    _call(102, "incoming", 40, answeredBy=""),
    _call(103, "incoming", 20, answeredBy=""),
]
# Previous month: one 60 s outgoing call from the office phone.
PREVIOUS_CALLS = [_call(50, "outgoing", 60, originInfo=OFFICE)]


def _route_event(event: str, name: str, value: str) -> dict:
    return {
        "eventType": {"event": event},
        "eventData": {"datafield1": name, "data1": value},
    }


ROUTES = {
    100: [
        _route_event("loadDialplan", "dialplanID", "3612"),
        _route_event("loadDialplan", "dialplanID", "3609"),
        {
            "eventType": {"event": "forwardToNumber"},
            "eventData": {
                "datafield1": "forwardAction",
                "data1": "dialExternalNumber",
                "datafield2": "dialedNumber",
                "data2": "32495000000",
            },
        },
    ],
    101: [_route_event("loadDialplan", "dialplanID", "3612")],
}


async def _get_cdr_between(start: int, end: int, **filters: object) -> list:
    """Return this month's calls, or the previous month's for an older window."""
    month_start = dt_util.start_of_local_day(dt_util.now().replace(day=1))
    if start < month_start.timestamp():
        return [CallRecord.from_api(call) for call in PREVIOUS_CALLS]
    now = int(dt_util.utcnow().timestamp())
    return [
        # Call 103 ended a minute ago.
        CallRecord.from_api(
            {**call, "answerTs": now - 80, "endTs": now - 60}
            if call["ID"] == 103
            else call
        )
        for call in CURRENT_CALLS
    ]


async def _get_call_route(call_id: int) -> list:
    return [CallEvent.from_api(event) for event in ROUTES.get(call_id, [])]


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
        # Parse the raw API payloads the way the real client does.
        client.get_sip_accounts.return_value = [
            SipAccount.from_api(item) for item in SIP_ACCOUNTS
        ]
        client.get_function_indicators.return_value = [
            FunctionIndicator.from_api(item) for item in FUNCTION_INDICATORS
        ]
        client.get_voicemailboxes.return_value = [
            Voicemail.from_api(item) for item in VOICEMAILBOXES
        ]
        client.get_conversations.return_value = [
            Conversation.from_api(item) for item in CONVERSATIONS
        ]
        client.get_websocket_users.return_value = [
            WebsocketUser.from_api(item) for item in WEBSOCKET_USERS
        ]
        client.start_call.return_value = Conversation(ID=1234)
        client.get_dialplans.return_value = [
            Dialplan.from_api(item) for item in DIALPLANS
        ]
        client.get_cdr_between.side_effect = _get_cdr_between
        client.get_call_route.side_effect = _get_call_route
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
