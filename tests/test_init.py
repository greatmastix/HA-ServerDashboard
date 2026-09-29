"""Setup, coordinator and entity tests."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.playground_dashboard.const import DOMAIN

from .conftest import API, make_entry


async def _setup(hass, entry=None):
    entry = entry or make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _tick(hass, seconds=31):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_setup_entities(hass: HomeAssistant, aioclient_mock, state) -> None:
    """Entities are created from /state."""
    aioclient_mock.get(f"{API}/state", json=state)
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.myhost_cpu").state == "1.5"
    assert hass.states.get("sensor.myhost_pending_updates").state == "2"
    assert hass.states.get("sensor.myhost_last_boot").state == "2026-09-28T14:30:44+00:00"
    assert hass.states.get("sensor.myhost_last_host_job").state == "done"
    # no swap → no swap sensor
    assert hass.states.get("sensor.myhost_swap_used") is None
    assert hass.states.get("binary_sensor.myhost_reboot_required").state == STATE_OFF
    assert hass.states.get("binary_sensor.myhost_service_caddy").state == STATE_ON

    assert hass.states.get("binary_sensor.shortener_app_1_running").state == STATE_ON
    assert hass.states.get("binary_sensor.worker_app_1_running").state == STATE_OFF
    assert hass.states.get("binary_sensor.shortener_app_1_health").state == STATE_OFF
    # no healthcheck → no health entity
    assert hass.states.get("binary_sensor.worker_app_1_health") is None

    site = hass.states.get("binary_sensor.myhost_site_shortener")
    assert site.state == STATE_OFF
    assert site.attributes["failing_host"] == "s.example.org"
    assert hass.states.get("binary_sensor.myhost_site_dashboard").state == STATE_ON

    update = hass.states.get("update.myhost_system_packages")
    assert update.state == STATE_ON
    assert update.attributes["installed_version"] == "7.0.0-34-generic"

    assert hass.states.get("button.myhost_reboot") is not None


async def test_buttons_hidden_without_control(hass: HomeAssistant, aioclient_mock, state) -> None:
    """No buttons (and no install feature) with a read-only key."""
    aioclient_mock.get(f"{API}/state", json=state)
    await _setup(hass, make_entry(scopes=["read"]))
    assert hass.states.async_entity_ids("button") == []
    update = hass.states.get("update.myhost_system_packages")
    assert update.attributes["supported_features"] & 1 == 0  # INSTALL


@pytest.mark.parametrize(
    ("status", "exc"), [(503, None), (500, None), (None, aiohttp.ClientError())]
)
async def test_unavailable_on_errors(hass, aioclient_mock, state, status, exc) -> None:
    """503 / 5xx / network errors make entities unavailable, then recover."""
    aioclient_mock.get(f"{API}/state", json=state)
    await _setup(hass)
    assert hass.states.get("sensor.myhost_cpu").state == "1.5"

    aioclient_mock.clear_requests()
    if exc:
        aioclient_mock.get(f"{API}/state", exc=exc)
    else:
        aioclient_mock.get(f"{API}/state", status=status, json={"error": "x"})
    await _tick(hass)
    assert hass.states.get("sensor.myhost_cpu").state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/state", json=state)
    await _tick(hass, 62)
    assert hass.states.get("sensor.myhost_cpu").state == "1.5"


async def test_401_starts_reauth(hass: HomeAssistant, aioclient_mock, state) -> None:
    """401 during polling triggers the reauth flow."""
    aioclient_mock.get(f"{API}/state", json=state)
    entry = await _setup(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/state", status=401, json={"error": "revoked"})
    await _tick(hass)
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == entry.entry_id


async def test_setup_401_starts_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    """401 at setup → setup error + reauth."""
    aioclient_mock.get(f"{API}/state", status=401, json={"error": "revoked"})
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        f["context"]["source"] == SOURCE_REAUTH for f in hass.config_entries.flow.async_progress()
    )


async def test_setup_503_retries(hass: HomeAssistant, aioclient_mock) -> None:
    """503 at setup → retry."""
    aioclient_mock.get(f"{API}/state", status=503, json={"error": "warming up"})
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_dynamic_containers(hass: HomeAssistant, aioclient_mock, state) -> None:
    """New containers get entities at runtime; removed ones are deleted, and come back."""
    aioclient_mock.get(f"{API}/state", json=state)
    entry = await _setup(hass)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    assert hass.states.get("binary_sensor.new_app_1_running") is None
    assert _container_devices(dev_reg, entry) == {
        "myhost_container_shortener_app_1",
        "myhost_container_worker_app_1",
    }

    worker = state["containers"][1]
    new = dict(state["containers"][0], key="new_app_1", name="new-app-1", health=None)
    state["containers"] = [state["containers"][0], new]  # worker removed, new added
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/state", json=state)
    await _tick(hass)

    assert hass.states.get("binary_sensor.new_app_1_running").state == STATE_ON
    assert hass.states.get("binary_sensor.shortener_app_1_running").state == STATE_ON
    # removed container: entities and device are gone from HA
    assert hass.states.get("binary_sensor.worker_app_1_running") is None
    assert ent_reg.async_get("binary_sensor.worker_app_1_running") is None
    assert _container_devices(dev_reg, entry) == {
        "myhost_container_shortener_app_1",
        "myhost_container_new_app_1",
    }

    # health appears later → health entity gets added
    state["containers"][1]["health"] = "unhealthy"
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/state", json=state)
    await _tick(hass)
    assert hass.states.get("binary_sensor.new_app_1_health").state == STATE_ON

    # the removed container comes back → entities are created again
    state["containers"].append(worker)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/state", json=state)
    await _tick(hass)
    assert hass.states.get("binary_sensor.worker_app_1_running").state == STATE_OFF


async def test_young_containers_skipped(
    hass: HomeAssistant, aioclient_mock, state, freezer
) -> None:
    """Containers younger than a minute (one-off runs) get no entities until they settle."""
    aioclient_mock.get(f"{API}/state", json=state)
    entry = await _setup(hass)
    created = dt_util.utcnow().isoformat()
    state["containers"].append(
        dict(state["containers"][0], key="oneoff_run_1", name="oneoff-run-1", created=created)
    )
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/state", json=state)
    freezer.tick(timedelta(seconds=31))
    await _tick(hass, 0)
    assert hass.states.get("binary_sensor.oneoff_run_1_running") is None
    assert "myhost_container_oneoff_run_1" not in _container_devices(dr.async_get(hass), entry)

    freezer.tick(timedelta(seconds=31))
    await _tick(hass, 0)
    assert hass.states.get("binary_sensor.oneoff_run_1_running").state == STATE_ON


async def test_stale_devices_cleaned_at_setup(hass: HomeAssistant, aioclient_mock, state) -> None:
    """Devices/entities left over from containers that no longer exist are removed on startup."""
    entry = make_entry()
    entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "myhost")}, name="myhost"
    )
    for i in range(5):
        dev = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"myhost_container_gone_{i}")},
            name=f"gone-{i}",
        )
        ent_reg.async_get_or_create(
            "binary_sensor",
            DOMAIN,
            f"myhost_container_gone_{i}_running",
            config_entry=entry,
            device_id=dev.id,
        )
    ent_reg.async_get_or_create(
        "binary_sensor", DOMAIN, "myhost_site_oldsite_up", config_entry=entry
    )

    aioclient_mock.get(f"{API}/state", json=state)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert _container_devices(dev_reg, entry) == {
        "myhost_container_shortener_app_1",
        "myhost_container_worker_app_1",
    }
    uids = {e.unique_id for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)}
    assert not any("gone_" in uid or "oldsite" in uid for uid in uids)
    assert "myhost_container_worker_app_1_running" in uids


def _container_devices(dev_reg, entry) -> set[str]:
    return {
        ident
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        for d, ident in device.identifiers
        if d == DOMAIN and "_container_" in ident
    }


async def test_dynamic_sites(hass: HomeAssistant, aioclient_mock, state) -> None:
    """New sites appear without reload."""
    aioclient_mock.get(f"{API}/state", json=state)
    await _setup(hass)
    state["sites"].append(dict(state["sites"][0], key="blog", name="blog"))
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/state", json=state)
    await _tick(hass)
    assert hass.states.get("binary_sensor.myhost_site_blog").state == STATE_ON


async def test_button_press(hass: HomeAssistant, aioclient_mock, state) -> None:
    """Pressing a button posts the action and speeds up polling."""
    aioclient_mock.get(f"{API}/state", json=state)
    aioclient_mock.post(f"{API}/actions/check", status=202, json={"ok": True, "action": "check"})
    entry = await _setup(hass)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.myhost_check_for_updates"}, blocking=True
    )
    assert any(
        c[0] == "POST" and str(c[1]).endswith("/actions/check") for c in aioclient_mock.mock_calls
    )
    assert entry.runtime_data.update_interval == timedelta(seconds=5)


async def test_button_busy(hass: HomeAssistant, aioclient_mock, state) -> None:
    """409 → HomeAssistantError."""
    aioclient_mock.get(f"{API}/state", json=state)
    aioclient_mock.post(f"{API}/actions/reboot", status=409, json={"error": "busy"})
    await _setup(hass)
    with pytest.raises(HomeAssistantError, match="Another action is already running"):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.myhost_reboot"}, blocking=True
        )


async def test_busy_polls_fast(hass: HomeAssistant, aioclient_mock, state) -> None:
    """updates.busy switches to a 5 s interval."""
    state["updates"]["busy"] = True
    aioclient_mock.get(f"{API}/state", json=state)
    entry = await _setup(hass)
    assert entry.runtime_data.update_interval == timedelta(seconds=5)
    assert hass.states.get("binary_sensor.myhost_maintenance_running").state == STATE_ON


async def test_update_install(hass: HomeAssistant, aioclient_mock, state) -> None:
    """update.install → POST /actions/upgrade."""
    aioclient_mock.get(f"{API}/state", json=state)
    aioclient_mock.post(f"{API}/actions/upgrade", status=202, json={"ok": True})
    await _setup(hass)
    await hass.services.async_call(
        "update", "install", {"entity_id": "update.myhost_system_packages"}, blocking=True
    )
    assert any(str(c[1]).endswith("/actions/upgrade") for c in aioclient_mock.mock_calls)


async def test_unload(hass: HomeAssistant, aioclient_mock, state) -> None:
    """Entry unloads."""
    aioclient_mock.get(f"{API}/state", json=state)
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_token(hass: HomeAssistant, aioclient_mock, state) -> None:
    """The API key never appears in diagnostics."""
    from custom_components.playground_dashboard.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    aioclient_mock.get(f"{API}/state", json=state)
    entry = await _setup(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["api_key"] == "**REDACTED**"
    assert entry.data["api_key"] not in str(diag)
