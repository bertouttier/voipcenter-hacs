"""Tests for the VoipCenter API client."""

import time

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.voipcenter.api import (
    VoipCenterAuthError,
    VoipCenterClient,
    _parse_body,
)
from custom_components.voipcenter.const import API_BASE_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


def _tokens(token: str = "tok", expires_in: int = 600) -> dict:  # noqa: S107
    now = int(time.time())
    return {
        "username": "apiuser",
        "token": token,
        "tokenExpires": now + expires_in,
        "refreshToken": f"refresh-{token}",
        "refreshTokenExpires": now + 3600,
    }


def test_parse_body_strips_html_prefix() -> None:
    """Stray HTML before the JSON is ignored."""
    assert _parse_body('<br/>notice\n{"results": [1]}') == {"results": [1]}
    assert _parse_body("[1, 2]") == [1, 2]
    assert _parse_body("plain") == "plain"


async def test_authenticate_and_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The token is fetched once and sent as bearer token."""
    aioclient_mock.post(f"{API_BASE_URL}/token", json=_tokens())
    aioclient_mock.get(f"{API_BASE_URL}/pbx/sipaccount", json={"results": [{"ID": 1}]})
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "secret")

    assert await client.get_sip_accounts() == [{"ID": 1}]
    assert await client.get_sip_accounts() == [{"ID": 1}]

    token_calls = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/token")]
    assert len(token_calls) == 1
    assert token_calls[0][2] == {"username": "apiuser", "password": "secret"}
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == "Bearer tok"


async def test_expired_token_uses_refresh_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An expiring token is renewed with the refresh token."""
    aioclient_mock.post(f"{API_BASE_URL}/token", json=_tokens("old", expires_in=5))
    aioclient_mock.post(f"{API_BASE_URL}/refreshtoken", json=_tokens("new"))
    aioclient_mock.get(f"{API_BASE_URL}/action/conversation", json={"results": []})
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "secret")

    await client.authenticate()
    await client.get_conversations()

    refresh_calls = [
        c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/refreshtoken")
    ]
    assert refresh_calls[0][2] == {"refreshToken": "refresh-old"}
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == "Bearer new"


async def test_invalid_credentials(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A rejected token request raises an auth error."""
    aioclient_mock.post(
        f"{API_BASE_URL}/token", status=401, json={"error_message": "Wrong password"}
    )
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "bad")

    with pytest.raises(VoipCenterAuthError, match="Wrong password"):
        await client.authenticate()


async def test_action_payloads(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Actions send the payloads from the API documentation."""
    aioclient_mock.post(f"{API_BASE_URL}/token", json=_tokens())
    aioclient_mock.post(f"{API_BASE_URL}/action/conversation", json=[{"ID": 5}])
    aioclient_mock.put(f"{API_BASE_URL}/action/conversation", json={})
    aioclient_mock.delete(f"{API_BASE_URL}/action/conversation", json={})
    aioclient_mock.put(f"{API_BASE_URL}/action/functionindicator", json={})
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "secret")

    assert await client.start_call(471, "0470123456") == {"ID": 5}
    await client.transfer_call(2719, "6")
    await client.end_call(2719)
    await client.set_function_indicator(2719, "red")

    payloads = [c[2] for c in aioclient_mock.mock_calls[1:]]
    assert payloads == [
        {"call-1": {"origin": 471, "destination": "0470123456"}},
        {"2719": {"destination": "6"}},
        {"ID": 2719},
        {"2719": {"state": "red"}},
    ]
