"""Buttons for Playground Dashboard host actions (requires the `control` scope)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_CHECK, ACTION_REBOOT, ACTION_UPGRADE
from .coordinator import PlaygroundDashboardConfigEntry
from .entity import PlaygroundDashboardEntity
from .helpers import async_run_action

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class DashboardButtonDescription(ButtonEntityDescription):
    """Describes a host action button."""

    action: str


BUTTONS: tuple[DashboardButtonDescription, ...] = (
    DashboardButtonDescription(
        key="check_updates",
        translation_key="check_updates",
        action=ACTION_CHECK,
    ),
    DashboardButtonDescription(
        key="install_updates",
        translation_key="install_updates",
        action=ACTION_UPGRADE,
    ),
    DashboardButtonDescription(
        key="reboot",
        translation_key="reboot",
        action=ACTION_REBOOT,
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlaygroundDashboardConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons (only when the key has the control scope)."""
    coordinator = entry.runtime_data
    if not coordinator.can_control:
        return
    async_add_entities(DashboardButton(coordinator, d) for d in BUTTONS)


class DashboardButton(PlaygroundDashboardEntity, ButtonEntity):
    """Triggers a host action."""

    entity_description: DashboardButtonDescription

    async def async_press(self) -> None:
        """Queue the action."""
        await async_run_action(self.coordinator, self.entity_description.action)
