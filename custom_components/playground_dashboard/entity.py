"""Base entities and helpers for Playground Dashboard."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import PlaygroundDashboardCoordinator


def parse_ts(value: Any):
    """Parse an ISO 8601 timestamp (or return None)."""
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)


def container_device_id(hostname: str, key: str) -> str:
    """Device identifier for a container sub-device."""
    return f"{hostname}_container_{key}"


class PlaygroundDashboardEntity(CoordinatorEntity[PlaygroundDashboardCoordinator]):
    """Entity attached to the server device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PlaygroundDashboardCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.hostname}_{description.key}"
        self._attr_device_info = coordinator.device_info


class PlaygroundDashboardItemEntity(PlaygroundDashboardEntity):
    """Entity bound to one element of a list in /state (container, site, service).

    The entity becomes unavailable when its key disappears from the list.
    """

    collection: str
    item_key_field: str = "key"
    unique_prefix: str

    def __init__(
        self,
        coordinator: PlaygroundDashboardCoordinator,
        description: EntityDescription,
        item: dict[str, Any],
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)
        self.item_key: str = str(item[self.item_key_field])
        self._attr_unique_id = (
            f"{coordinator.hostname}_{self.unique_prefix}_{self.item_key}_{description.key}"
        )
        self._attr_translation_placeholders = {"name": str(item.get("name") or self.item_key)}

    @property
    def item(self) -> dict[str, Any] | None:
        """Return the current item, or None if it's gone."""
        for item in (self.coordinator.data or {}).get(self.collection) or []:
            if str(item.get(self.item_key_field)) == self.item_key:
                return item
        return None

    @property
    def available(self) -> bool:
        """Unavailable when the item disappeared."""
        return super().available and self.item is not None


class ContainerEntity(PlaygroundDashboardItemEntity):
    """Entity on a per-container sub-device."""

    collection = "containers"
    unique_prefix = "container"

    def __init__(
        self,
        coordinator: PlaygroundDashboardCoordinator,
        description: EntityDescription,
        item: dict[str, Any],
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description, item)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, container_device_id(coordinator.hostname, self.item_key))},
            name=item.get("name") or self.item_key,
            manufacturer="Docker",
            model=item.get("image"),
            via_device=(DOMAIN, coordinator.hostname),
        )


class SiteEntity(PlaygroundDashboardItemEntity):
    """Entity for a public site (on the server device)."""

    collection = "sites"
    unique_prefix = "site"


class ServiceEntity(PlaygroundDashboardItemEntity):
    """Entity for a host service (on the server device)."""

    collection = "services"
    item_key_field = "name"
    unique_prefix = "service"


@callback
def async_setup_dynamic(
    coordinator: PlaygroundDashboardCoordinator,
    async_add_entities: AddEntitiesCallback,
    collection: str,
    factory: Callable[[dict[str, Any]], Iterable[Entity]],
    key_field: str = "key",
) -> Callable[[], None]:
    """Add entities for list items now and whenever new ones appear.

    `factory` is called with every item on every update; entities whose
    unique_id was already added are skipped, so a factory may start returning
    an entity later (e.g. once a container gets a healthcheck).
    """
    known: set[str] = set()

    @callback
    def _check() -> None:
        new: list[Entity] = []
        for item in (coordinator.data or {}).get(collection) or []:
            if not isinstance(item, dict) or item.get(key_field) in (None, ""):
                continue
            for entity in factory(item):
                if entity.unique_id not in known:
                    known.add(entity.unique_id)
                    new.append(entity)
        if new:
            async_add_entities(new)

    _check()
    return coordinator.async_add_listener(_check)
