"""Tests for the VoipCenter API client."""

import time

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.voipcenter import api
from custom_components.voipcenter.api import (
    VoipCenterAuthError,
    VoipCenterClient,
    VoipCenterError,
    _hash_password,
    _parse_body,
)
from custom_components.voipcenter.const import API_BASE_URL, WEB_APP_SCRIPT_URL
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


@pytest.fixture(autouse=True)
def reset_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo base URL rediscovery between tests."""
    monkeypatch.setattr(api, "_base_url", API_BASE_URL)


def test_parse_body_strips_html_prefix() -> None:
    """Stray HTML before the JSON is ignored."""
    assert _parse_body('<br/>notice\n{"results": [1]}') == {"results": [1]}
    assert _parse_body("[1, 2]") == [1, 2]
    assert _parse_body("plain") == "plain"


def test_hash_password() -> None:
    """Passwords are sent as sha256(md5(password)), like the web app does."""
    assert _hash_password("secret") == (
        "9f9dd1d2e3f189e7929a73ef1f5b54873622f64cc15210133c5085b5175325df"
    )


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
    assert token_calls[0][2] == {
        "username": "apiuser",
        "password": _hash_password("secret"),
    }
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
    """A rejected token request raises an auth error with the API message."""
    aioclient_mock.post(
        f"{API_BASE_URL}/token",
        status=401,
        json=[
            {
                "ID": 0,
                "status": "error",
                "error": {
                    "errorType": "Authentication",
                    "error_number": "3",
                    "error_message": "Incorrect credentials",
                },
                "succes": False,
            }
        ],
    )
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "bad")

    with pytest.raises(VoipCenterAuthError, match="^Incorrect credentials$"):
        await client.authenticate()


async def test_moved_api_is_rediscovered(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 404 on the token endpoint looks up the current base URL in the web app."""
    new_base = "https://api.pbxonline.be/v2/270101"
    aioclient_mock.post(f"{API_BASE_URL}/token", status=404, text="<HTML>404</HTML>")
    aioclient_mock.get(
        WEB_APP_SCRIPT_URL,
        text=f'axios.defaults.baseURL = \\"{new_base}\\";',
    )
    aioclient_mock.post(f"{new_base}/token", json=_tokens())
    aioclient_mock.get(f"{new_base}/pbx/sipaccount", json={"results": []})
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "secret")

    await client.authenticate()
    assert await client.get_sip_accounts() == []


async def test_missing_api_is_not_an_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 404 that can't be rediscovered is reported as an API error."""
    aioclient_mock.post(f"{API_BASE_URL}/token", status=404, text="<HTML>404</HTML>")
    aioclient_mock.get(WEB_APP_SCRIPT_URL, text="no base url here")
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "secret")

    with pytest.raises(VoipCenterError, match="failed \\(404\\)") as exc:
        await client.authenticate()
    assert not isinstance(exc.value, VoipCenterAuthError)


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


async def test_latest_api_from_token_response(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The base URL follows the ``latestApi`` of the token response."""
    new_base = "https://api.pbxonline.be/v2/270101"
    aioclient_mock.post(
        f"{API_BASE_URL}/token", json=_tokens() | {"latestApi": "270101"}
    )
    aioclient_mock.get(f"{new_base}/pbx/sipaccount", json={"results": [{"ID": 1}]})
    client = VoipCenterClient(async_get_clientsession(hass), "apiuser", "secret")

    assert await client.get_sip_accounts() == [{"ID": 1}]
