"""Shared helpers for Playground Dashboard."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError

from .api import ApiError, AuthError, BusyError, ForbiddenError
from .const import DOMAIN
from .coordinator import PlaygroundDashboardCoordinator


async def async_run_action(coordinator: PlaygroundDashboardCoordinator, action: str) -> None:
    """Run a host action and map API errors to HomeAssistantError."""
    try:
        await coordinator.api.action(action)
    except BusyError as err:
        raise HomeAssistantError(
            "Another action is already running",
            translation_domain=DOMAIN,
            translation_key="action_busy",
        ) from err
    except ForbiddenError as err:
        raise HomeAssistantError(
            "The API key lacks the control scope",
            translation_domain=DOMAIN,
            translation_key="action_forbidden",
        ) from err
    except AuthError as err:
        coordinator.config_entry.async_start_reauth(coordinator.hass)
        raise HomeAssistantError(
            "The API key was rejected",
            translation_domain=DOMAIN,
            translation_key="action_auth",
        ) from err
    except ApiError as err:
        raise HomeAssistantError(
            f"Action {action} failed: {err}",
            translation_domain=DOMAIN,
            translation_key="action_failed",
            translation_placeholders={"action": action, "error": str(err)},
        ) from err
    await coordinator.async_action_started()
