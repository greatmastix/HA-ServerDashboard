"""Update entity ("System packages") for Playground Dashboard."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_UPGRADE
from .coordinator import PlaygroundDashboardConfigEntry, PlaygroundDashboardCoordinator
from .entity import PlaygroundDashboardEntity
from .helpers import async_run_action

PARALLEL_UPDATES = 1

SYSTEM_PACKAGES = UpdateEntityDescription(
    key="system_packages",
    translation_key="system_packages",
    device_class=UpdateDeviceClass.FIRMWARE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlaygroundDashboardConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the update entity."""
    async_add_entities([SystemPackagesUpdate(entry.runtime_data, SYSTEM_PACKAGES)])


class SystemPackagesUpdate(PlaygroundDashboardEntity, UpdateEntity):
    """Pending apt packages as an update entity.

    The "installed version" is the running kernel; the "latest version" is the
    same string plus the number of pending package updates, so the entity is on
    whenever apt has something to install.
    """

    def __init__(
        self,
        coordinator: PlaygroundDashboardCoordinator,
        description: UpdateEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)
        features = UpdateEntityFeature.RELEASE_NOTES
        if coordinator.can_control:
            features |= UpdateEntityFeature.INSTALL
        self._attr_supported_features = features

    @property
    def _updates(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("updates") or {}

    @property
    def installed_version(self) -> str | None:
        """Return the running kernel (or 'current')."""
        if self._updates.get("updates") is None:
            return None
        kernel = self._updates.get("kernel") or (self.coordinator.data or {}).get("system", {}).get(
            "kernel"
        )
        return kernel or "current"

    @property
    def latest_version(self) -> str | None:
        """Return installed version, suffixed with the pending update count."""
        installed = self.installed_version
        if installed is None:
            return None
        count = self._updates.get("updates") or 0
        if count <= 0:
            return installed
        return f"{installed} (+{count} {'update' if count == 1 else 'updates'})"

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """Versions are only labels here: any difference means updates are pending."""
        return latest_version != installed_version

    @property
    def in_progress(self) -> bool:
        """Return True while a host action is queued or running."""
        return bool(self._updates.get("busy"))

    @property
    def release_summary(self) -> str | None:
        """Short list of pending packages (max 255 chars)."""
        packages = self._updates.get("packages") or []
        if not packages:
            return None
        security = self._updates.get("security") or 0
        text = f"{len(packages)} package(s), {security} security: " + ", ".join(
            str(p.get("name")) for p in packages
        )
        return text if len(text) <= 255 else text[:252] + "..."

    async def async_release_notes(self) -> str | None:
        """Full package list as markdown."""
        packages = self._updates.get("packages") or []
        if not packages:
            return "No pending updates."
        lines = ["| Package | From | To | Security |", "|---|---|---|---|"]
        lines.extend(
            f"| {p.get('name')} | {p.get('from')} | {p.get('to')} | "
            f"{'yes' if p.get('security') else ''} |"
            for p in packages
        )
        if self._updates.get("rebootRequired"):
            lines.append("\n**A reboot is required.**")
        return "\n".join(lines)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Run apt full-upgrade."""
        await async_run_action(self.coordinator, ACTION_UPGRADE)
