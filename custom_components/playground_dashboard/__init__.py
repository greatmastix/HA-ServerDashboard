"""The Playground Dashboard integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PlaygroundDashboardApi
from .const import CONF_CONTAINERS, CONF_SITES, DOMAIN
from .coordinator import PlaygroundDashboardConfigEntry, PlaygroundDashboardCoordinator
from .entity import container_device_id

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.UPDATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: PlaygroundDashboardConfigEntry) -> bool:
    """Set up Playground Dashboard from a config entry."""
    session = async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True))
    api = PlaygroundDashboardApi(session, entry.data[CONF_URL], entry.data[CONF_API_KEY])
    coordinator = PlaygroundDashboardCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _async_cleanup_disabled(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlaygroundDashboardConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: PlaygroundDashboardConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_cleanup_disabled(hass: HomeAssistant, entry: PlaygroundDashboardConfigEntry) -> None:
    """Remove container/site entities when those groups are switched off in the options."""
    hostname = entry.runtime_data.hostname
    prefixes: list[str] = []
    if not entry.options.get(CONF_CONTAINERS, True):
        prefixes.append(f"{hostname}_container_")
    if not entry.options.get(CONF_SITES, True):
        prefixes.append(f"{hostname}_site_")
    if not prefixes:
        return

    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id.startswith(tuple(prefixes)):
            ent_reg.async_remove(ent.entity_id)

    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if any(
            d == DOMAIN and ident.startswith(tuple(prefixes)) for d, ident in device.identifiers
        ):
            dev_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: PlaygroundDashboardConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting container devices whose container no longer exists."""
    coordinator = entry.runtime_data
    current = {
        container_device_id(coordinator.hostname, str(c.get("key")))
        for c in (coordinator.data or {}).get("containers") or []
    }
    return not any(
        d == DOMAIN and (ident == coordinator.hostname or ident in current)
        for d, ident in device.identifiers
    )
