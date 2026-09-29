"""Sensors for Playground Dashboard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import CONF_CONTAINERS, CONF_SITES
from .coordinator import PlaygroundDashboardConfigEntry
from .entity import (
    ContainerEntity,
    PlaygroundDashboardEntity,
    SiteEntity,
    async_setup_dynamic,
    container_is_settled,
    parse_ts,
)

PARALLEL_UPDATES = 0

type Data = dict[str, Any]


def _metrics(data: Data) -> Data:
    return data.get("metrics") or {}


def _summary(data: Data) -> Data:
    return data.get("summary") or {}


def _updates(data: Data) -> Data:
    return data.get("updates") or {}


@dataclass(frozen=True, kw_only=True)
class DashboardSensorDescription(SensorEntityDescription):
    """Describes a host sensor."""

    value_fn: Callable[[Data], StateType | datetime]
    attrs_fn: Callable[[Data], dict[str, Any]] | None = None
    exists_fn: Callable[[Data], bool] = lambda _: True


def _metric(key: str) -> Callable[[Data], Any]:
    return lambda data: _metrics(data).get(key)


def _pct(**kwargs: Any) -> dict[str, Any]:
    return {
        "native_unit_of_measurement": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "suggested_display_precision": 1,
        **kwargs,
    }


def _rate(**kwargs: Any) -> dict[str, Any]:
    return {
        "device_class": SensorDeviceClass.DATA_RATE,
        "native_unit_of_measurement": UnitOfDataRate.BYTES_PER_SECOND,
        "suggested_unit_of_measurement": UnitOfDataRate.KILOBYTES_PER_SECOND,
        "state_class": SensorStateClass.MEASUREMENT,
        "suggested_display_precision": 1,
        **kwargs,
    }


def _size(**kwargs: Any) -> dict[str, Any]:
    return {
        "device_class": SensorDeviceClass.DATA_SIZE,
        "native_unit_of_measurement": UnitOfInformation.BYTES,
        "suggested_unit_of_measurement": UnitOfInformation.GIBIBYTES,
        "suggested_display_precision": 2,
        **kwargs,
    }


HOST_SENSORS: tuple[DashboardSensorDescription, ...] = (
    DashboardSensorDescription(
        key="cpu", translation_key="cpu", value_fn=_metric("cpuPct"), **_pct()
    ),
    DashboardSensorDescription(
        key="load_1",
        translation_key="load_1",
        value_fn=_metric("load1"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    DashboardSensorDescription(
        key="load_5",
        translation_key="load_5",
        value_fn=_metric("load5"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    DashboardSensorDescription(
        key="load_15",
        translation_key="load_15",
        value_fn=_metric("load15"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    DashboardSensorDescription(
        key="memory_used",
        translation_key="memory_used",
        value_fn=_metric("memPct"),
        attrs_fn=lambda d: {
            "used_bytes": _metrics(d).get("memUsedBytes"),
            "available_bytes": _metrics(d).get("memAvailableBytes"),
            "cached_bytes": _metrics(d).get("memCachedBytes"),
            "total_bytes": _metrics(d).get("memTotalBytes"),
        },
        **_pct(),
    ),
    DashboardSensorDescription(
        key="memory_used_bytes",
        translation_key="memory_used_bytes",
        value_fn=_metric("memUsedBytes"),
        **_size(state_class=SensorStateClass.MEASUREMENT, entity_registry_enabled_default=False),
    ),
    DashboardSensorDescription(
        key="swap_used",
        translation_key="swap_used",
        value_fn=_metric("swapPct"),
        exists_fn=lambda d: ((d.get("system") or {}).get("swapTotalBytes") or 0) > 0,
        attrs_fn=lambda d: {
            "used_bytes": _metrics(d).get("swapUsedBytes"),
            "total_bytes": _metrics(d).get("swapTotalBytes"),
        },
        **_pct(),
    ),
    DashboardSensorDescription(
        key="disk_used",
        translation_key="disk_used",
        value_fn=_metric("diskPct"),
        attrs_fn=lambda d: {
            "used_bytes": _metrics(d).get("diskUsedBytes"),
            "free_bytes": _metrics(d).get("diskFreeBytes"),
            "total_bytes": _metrics(d).get("diskTotalBytes"),
        },
        **_pct(),
    ),
    DashboardSensorDescription(
        key="disk_free",
        translation_key="disk_free",
        value_fn=_metric("diskFreeBytes"),
        **_size(state_class=SensorStateClass.MEASUREMENT),
    ),
    DashboardSensorDescription(
        key="disk_read",
        translation_key="disk_read",
        value_fn=_metric("diskReadBytesPerSec"),
        **_rate(entity_registry_enabled_default=False),
    ),
    DashboardSensorDescription(
        key="disk_write",
        translation_key="disk_write",
        value_fn=_metric("diskWriteBytesPerSec"),
        **_rate(entity_registry_enabled_default=False),
    ),
    DashboardSensorDescription(
        key="network_in",
        translation_key="network_in",
        value_fn=_metric("netRxBytesPerSec"),
        **_rate(),
    ),
    DashboardSensorDescription(
        key="network_out",
        translation_key="network_out",
        value_fn=_metric("netTxBytesPerSec"),
        **_rate(),
    ),
    DashboardSensorDescription(
        key="network_total_in",
        translation_key="network_total_in",
        value_fn=_metric("netRxBytesTotal"),
        **_size(
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_registry_enabled_default=False,
        ),
    ),
    DashboardSensorDescription(
        key="network_total_out",
        translation_key="network_total_out",
        value_fn=_metric("netTxBytesTotal"),
        **_size(
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_registry_enabled_default=False,
        ),
    ),
    DashboardSensorDescription(
        key="cpu_iowait",
        translation_key="cpu_iowait",
        value_fn=_metric("cpuIowaitPct"),
        **_pct(
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
    ),
    DashboardSensorDescription(
        key="cpu_steal",
        translation_key="cpu_steal",
        value_fn=_metric("cpuStealPct"),
        **_pct(
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
    ),
    DashboardSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: parse_ts((d.get("system") or {}).get("bootTime")),
    ),
    DashboardSensorDescription(
        key="containers_running",
        translation_key="containers_running",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _summary(d).get("containersRunning"),
        attrs_fn=lambda d: {
            "total": _summary(d).get("containersTotal"),
            "stopped": _summary(d).get("containersStopped"),
            "unhealthy": _summary(d).get("containersUnhealthy"),
        },
    ),
    DashboardSensorDescription(
        key="sites_up",
        translation_key="sites_up",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _summary(d).get("sitesUp"),
        attrs_fn=lambda d: {
            "total": _summary(d).get("sitesTotal"),
            "down": _summary(d).get("sitesDown"),
        },
    ),
    DashboardSensorDescription(
        key="cert_min_days_left",
        translation_key="cert_min_days_left",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _summary(d).get("certMinDaysLeft"),
    ),
    DashboardSensorDescription(
        key="pending_updates",
        translation_key="pending_updates",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _updates(d).get("updates"),
        attrs_fn=lambda d: {
            "security": _updates(d).get("security"),
            "checked": _updates(d).get("checked"),
            "packages": [
                {"name": p.get("name"), "from": p.get("from"), "to": p.get("to")}
                for p in _updates(d).get("packages") or []
            ],
        },
    ),
    DashboardSensorDescription(
        key="pending_security_updates",
        translation_key="pending_security_updates",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _updates(d).get("security"),
        attrs_fn=lambda d: {
            "packages": [
                {"name": p.get("name"), "from": p.get("from"), "to": p.get("to")}
                for p in _updates(d).get("packages") or []
                if p.get("security")
            ],
        },
    ),
    DashboardSensorDescription(
        key="last_job",
        translation_key="last_job",
        device_class=SensorDeviceClass.ENUM,
        options=["running", "done", "failed"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (_updates(d).get("job") or {}).get("state"),
        attrs_fn=lambda d: {
            k: (_updates(d).get("job") or {}).get(k)
            for k in ("action", "started", "finished", "exit")
        },
    ),
)


@dataclass(frozen=True, kw_only=True)
class ItemSensorDescription(SensorEntityDescription):
    """Describes a per-container / per-site sensor."""

    value_fn: Callable[[Data], StateType | datetime]
    attrs_fn: Callable[[Data], dict[str, Any]] | None = None


CONTAINER_SENSORS: tuple[ItemSensorDescription, ...] = (
    ItemSensorDescription(
        key="cpu",
        translation_key="container_cpu",
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.get("cpuPct"),
        **_pct(),
    ),
    ItemSensorDescription(
        key="memory",
        translation_key="container_memory",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.get("memBytes"),
        attrs_fn=lambda c: {
            "memory_pct": c.get("memPct"),
            "memory_limit_bytes": c.get("memLimitBytes"),
        },
    ),
)

SITE_CERT_SENSOR = ItemSensorDescription(
    key="cert_expiry",
    translation_key="site_cert_expiry",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda s: parse_ts(s.get("certExpires")),
    attrs_fn=lambda s: {"days_left": s.get("certDaysLeft")},
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlaygroundDashboardConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}

    entities: list[SensorEntity] = []
    for description in HOST_SENSORS:
        if not description.exists_fn(data):
            continue
        cls = LastBootSensor if description.key == "last_boot" else HostSensor
        entities.append(cls(coordinator, description))
    async_add_entities(entities)

    if entry.options.get(CONF_CONTAINERS, True):
        entry.async_on_unload(
            async_setup_dynamic(
                coordinator,
                async_add_entities,
                "containers",
                lambda item: [
                    ContainerSensor(coordinator, desc, item) for desc in CONTAINER_SENSORS
                ],
                include_fn=container_is_settled,
            )
        )
    if entry.options.get(CONF_SITES, True):
        entry.async_on_unload(
            async_setup_dynamic(
                coordinator,
                async_add_entities,
                "sites",
                lambda item: [SiteSensor(coordinator, SITE_CERT_SENSOR, item)],
            )
        )


class HostSensor(PlaygroundDashboardEntity, SensorEntity):
    """Host-level sensor."""

    entity_description: DashboardSensorDescription
    _unrecorded_attributes = frozenset({"packages"})

    @property
    def native_value(self) -> StateType | datetime:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})


class LastBootSensor(HostSensor):
    """Boot time; ignores sub-minute jitter so the state doesn't change every poll."""

    _last: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        """Return the boot time."""
        value = super().native_value
        if not isinstance(value, datetime):
            return None
        if self._last is None or abs(value - self._last) > timedelta(seconds=60):
            self._last = value.replace(microsecond=0)
        return self._last


class _ItemSensor(SensorEntity):
    entity_description: ItemSensorDescription
    item: dict[str, Any] | None

    @property
    def native_value(self) -> StateType | datetime:
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


class ContainerSensor(ContainerEntity, _ItemSensor):
    """Per-container sensor."""


class SiteSensor(SiteEntity, _ItemSensor):
    """Per-site sensor."""
