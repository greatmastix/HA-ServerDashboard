"""Config flow tests."""

from __future__ import annotations

import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.playground_dashboard.const import DOMAIN

from .conftest import API, TOKEN, TOKEN2, URL, make_entry


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_success(hass: HomeAssistant, aioclient_mock, ping, state) -> None:
    """Valid key creates an entry; URL is normalized."""
    aioclient_mock.get(f"{API}/ping", json=ping)
    aioclient_mock.get(f"{API}/state", json=state)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"url": f"{URL}/api/v1/", "api_key": TOKEN, "verify_ssl": True},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "myhost"
    assert result["data"]["url"] == URL
    assert result["data"]["scopes"] == ["read", "control"]
    assert result["result"].unique_id == "myhost"
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_user_invalid_auth(hass: HomeAssistant, aioclient_mock) -> None:
    """401 → invalid_auth."""
    aioclient_mock.get(f"{API}/ping", status=401, json={"error": "invalid token"})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": URL, "api_key": TOKEN, "verify_ssl": True}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    """Network error → cannot_connect."""
    aioclient_mock.get(f"{API}/ping", exc=aiohttp.ClientConnectionError())
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": URL, "api_key": TOKEN, "verify_ssl": True}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_bad_token_format(hass: HomeAssistant, aioclient_mock) -> None:
    """Malformed token is rejected without a request."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": URL, "api_key": "nope", "verify_ssl": True}
    )
    assert result["errors"] == {"api_key": "invalid_api_key_format"}
    assert aioclient_mock.call_count == 0


async def test_user_already_configured(hass: HomeAssistant, aioclient_mock, ping) -> None:
    """Same hostname twice → abort."""
    make_entry().add_to_hass(hass)
    aioclient_mock.get(f"{API}/ping", json=ping)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": URL, "api_key": TOKEN, "verify_ssl": True}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, aioclient_mock, ping, state) -> None:
    """Reauth stores the new key and updated scopes."""
    entry = make_entry(scopes=["read"])
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{API}/ping", json=ping)
    aioclient_mock.get(f"{API}/state", json=state)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": TOKEN2})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_key"] == TOKEN2
    assert entry.data["scopes"] == ["read", "control"]


async def test_reauth_invalid_then_wrong_server(hass: HomeAssistant, aioclient_mock, ping) -> None:
    """Reauth shows invalid_auth, and aborts for a key of another server."""
    entry = make_entry()
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{API}/ping", status=401, json={"error": "revoked"})
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": TOKEN2})
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    ping["hostname"] = "otherhost"
    aioclient_mock.get(f"{API}/ping", json=ping)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": TOKEN2})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_server"


async def test_options(hass: HomeAssistant, aioclient_mock, state) -> None:
    """Options flow stores interval and toggles."""
    entry = make_entry()
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{API}/state", json=state)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 60, "containers": False, "sites": True}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": 60, "containers": False, "sites": True}
    assert hass.states.get("binary_sensor.shortener_app_1_running") is None
    assert hass.states.get("binary_sensor.myhost_site_dashboard") is not None
