"""Binary sensors for Playground Dashboard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CONTAINERS, CONF_SITES
from .coordinator import PlaygroundDashboardConfigEntry
from .entity import (
    ContainerEntity,
    PlaygroundDashboardEntity,
    ServiceEntity,
    SiteEntity,
    async_setup_dynamic,
)

PARALLEL_UPDATES = 0

type Data = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class DashboardBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor; the functions receive /state or a list item."""

    value_fn: Callable[[Data], bool | None]
    attrs_fn: Callable[[Data], dict[str, Any]] | None = None


def _updates(data: Data) -> Data:
    return data.get("updates") or {}


def _bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


HOST_BINARY_SENSORS: tuple[DashboardBinarySensorDescription, ...] = (
    DashboardBinarySensorDescription(
        key="reboot_required",
        translation_key="reboot_required",
        device_class=BinarySensorDeviceClass.UPDATE,
        value_fn=lambda d: _bool(_updates(d).get("rebootRequired")),
        attrs_fn=lambda d: {"reboot_packages": _updates(d).get("rebootPackages") or []},
    ),
    DashboardBinarySensorDescription(
        key="maintenance_running",
        translation_key="maintenance_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: _bool(_updates(d).get("busy")),
        attrs_fn=lambda d: {"action": (_updates(d).get("job") or {}).get("action")},
    ),
)

SERVICE_SENSOR = DashboardBinarySensorDescription(
    key="running",
    translation_key="service",
    device_class=BinarySensorDeviceClass.RUNNING,
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda s: _bool(s.get("running")),
)

CONTAINER_RUNNING = DashboardBinarySensorDescription(
    key="running",
    translation_key="container_running",
    device_class=BinarySensorDeviceClass.RUNNING,
    value_fn=lambda c: _bool(c.get("running")),
    attrs_fn=lambda c: {
        k: c.get(k) for k in ("stack", "service", "image", "state", "status", "health", "id")
    },
)

CONTAINER_HEALTH = DashboardBinarySensorDescription(
    key="health",
    translation_key="container_health",
    device_class=BinarySensorDeviceClass.PROBLEM,
    value_fn=lambda c: None if c.get("health") is None else c.get("health") != "healthy",
    attrs_fn=lambda c: {"health": c.get("health")},
)

SITE_UP = DashboardBinarySensorDescription(
    key="up",
    translation_key="site",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    value_fn=lambda s: _bool(s.get("up")),
    attrs_fn=lambda s: {
        "url": s.get("url"),
        "aliases": s.get("aliases") or [],
        "http_status": s.get("httpStatus"),
        "response_ms": s.get("responseMs"),
        "error": s.get("error"),
        "failing_host": s.get("failingHost"),
        "checked": s.get("checked"),
    },
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlaygroundDashboardConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data

    async_add_entities(HostBinarySensor(coordinator, d) for d in HOST_BINARY_SENSORS)

    entry.async_on_unload(
        async_setup_dynamic(
            coordinator,
            async_add_entities,
            "services",
            lambda item: [ServiceBinarySensor(coordinator, SERVICE_SENSOR, item)],
            key_field="name",
        )
    )

    if entry.options.get(CONF_CONTAINERS, True):

        def _containers(item: Data) -> list[BinarySensorEntity]:
            entities: list[BinarySensorEntity] = [
                ContainerBinarySensor(coordinator, CONTAINER_RUNNING, item)
            ]
            if item.get("health") is not None:
                entities.append(ContainerBinarySensor(coordinator, CONTAINER_HEALTH, item))
            return entities

        entry.async_on_unload(
            async_setup_dynamic(coordinator, async_add_entities, "containers", _containers)
        )

    if entry.options.get(CONF_SITES, True):
        entry.async_on_unload(
            async_setup_dynamic(
                coordinator,
                async_add_entities,
                "sites",
                lambda item: [SiteBinarySensor(coordinator, SITE_UP, item)],
            )
        )


class HostBinarySensor(PlaygroundDashboardEntity, BinarySensorEntity):
    """Host-level binary sensor."""

    entity_description: DashboardBinarySensorDescription
    _unrecorded_attributes = frozenset({"reboot_packages"})

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})


class _ItemBinarySensor(BinarySensorEntity):
    entity_description: DashboardBinarySensorDescription
    item: Data | None

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        if (item := self.item) is None:
            return None
        return self.entity_description.value_fn(item)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None or (item := self.item) is None:
            return None
        return self.entity_description.attrs_fn(item)


class ServiceBinarySensor(ServiceEntity, _ItemBinarySensor):
    """Host service (caddy, dockerd, ...)."""


class ContainerBinarySensor(ContainerEntity, _ItemBinarySensor):
    """Per-container binary sensor."""


class SiteBinarySensor(SiteEntity, _ItemBinarySensor):
    """Per-site connectivity."""
