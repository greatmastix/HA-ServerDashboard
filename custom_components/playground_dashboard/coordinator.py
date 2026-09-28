"""DataUpdateCoordinator for Playground Dashboard."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthError, PlaygroundDashboardApi
from .const import (
    ACTION_BOOST,
    CONF_SCOPES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FAST_SCAN_INTERVAL,
    SCOPE_CONTROL,
)

_LOGGER = logging.getLogger(__name__)

type PlaygroundDashboardConfigEntry = ConfigEntry[PlaygroundDashboardCoordinator]


class PlaygroundDashboardCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls GET /state."""

    config_entry: PlaygroundDashboardConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PlaygroundDashboardConfigEntry,
        api: PlaygroundDashboardApi,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.hostname: str = entry.unique_id or entry.title
        self._normal_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._boost_until: datetime | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.hostname}",
            update_interval=self._normal_interval,
        )

    @property
    def can_control(self) -> bool:
        """Return True if the API key has the control scope."""
        return SCOPE_CONTROL in self.config_entry.data.get(CONF_SCOPES, [])

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.state()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ApiError as err:
            self._set_interval(busy=False)
            raise UpdateFailed(str(err)) from err
        if not isinstance(data, dict):
            raise UpdateFailed("Unexpected response from dashboard")
        self._set_interval(busy=bool((data.get("updates") or {}).get("busy")))
        return data

    def _set_interval(self, busy: bool) -> None:
        boosting = self._boost_until is not None and dt_util.utcnow() < self._boost_until
        self.update_interval = FAST_SCAN_INTERVAL if busy or boosting else self._normal_interval

    async def async_action_started(self) -> None:
        """Poll quickly for a while after a host action was queued."""
        self._boost_until = dt_util.utcnow() + ACTION_BOOST
        self.update_interval = FAST_SCAN_INTERVAL
        await self.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        """Device info for the server."""
        system = (self.data or {}).get("system") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.hostname)},
            name=system.get("hostname") or self.hostname,
            manufacturer=system.get("virt"),
            model=system.get("cpuModel"),
            sw_version=system.get("os"),
            hw_version=system.get("kernel"),
            configuration_url=system.get("dashboardUrl"),
        )
