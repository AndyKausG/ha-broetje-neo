"""Binary sensors for the Brötje NEO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import registers as r
from .coordinator import BroetjeConfigEntry, BroetjeNeoCoordinator
from .entity import BroetjeNeoEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BroetjeBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description."""

    is_on_fn: Callable[[BroetjeNeoCoordinator], bool | None]


def _nonzero(reg: r.Register) -> Callable[[BroetjeNeoCoordinator], bool | None]:
    def fn(c: BroetjeNeoCoordinator) -> bool | None:
        raw = c.raw(reg)
        return None if raw is None else raw != 0

    return fn


def _demand(value: int) -> Callable[[BroetjeNeoCoordinator], bool | None]:
    def fn(c: BroetjeNeoCoordinator) -> bool | None:
        raw = c.raw(r.DEMAND)
        return None if raw is None else raw == value

    return fn


def _running(key: str, reg: r.Register) -> BroetjeBinaryDescription:
    return BroetjeBinaryDescription(
        key=key, device_class=BinarySensorDeviceClass.RUNNING, is_on_fn=_nonzero(reg)
    )


BINARY_SENSORS: tuple[BroetjeBinaryDescription, ...] = (
    _running("heating_pump", r.HEATING_PUMP),
    _running("buffer_pump", r.BUFFER_PUMP),
    _running("compressor", r.HEAT_PUMP_RUNNING),
    _running("source_fan", r.SOURCE_FAN),
    BroetjeBinaryDescription(
        key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=_nonzero(r.FAULT),
    ),
    BroetjeBinaryDescription(key="defrost", is_on_fn=_nonzero(r.FOUR_WAY_VALVE)),
    BroetjeBinaryDescription(key="evu_release", is_on_fn=_nonzero(r.EVU_RELEASE)),
    BroetjeBinaryDescription(key="dhw_priority", is_on_fn=_nonzero(r.DHW_PRIORITY)),
    BroetjeBinaryDescription(key="passive_cooling", is_on_fn=_nonzero(r.PASSIVE_COOLING)),
    BroetjeBinaryDescription(key="demand_heating", is_on_fn=_demand(20)),
    BroetjeBinaryDescription(key="demand_dhw", is_on_fn=_demand(30)),
    BroetjeBinaryDescription(key="demand_cooling", is_on_fn=_demand(10)),
    BroetjeBinaryDescription(
        key="grid_control",
        icon="mdi:transmission-tower",
        is_on_fn=lambda c: c.grid_control_active if c.data is not None else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroetjeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(BroetjeNeoBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class BroetjeNeoBinarySensor(BroetjeNeoEntity, BinarySensorEntity):
    """Brötje NEO binary sensor."""

    entity_description: BroetjeBinaryDescription

    @property
    def is_on(self) -> bool | None:
        """Return state."""
        return self.entity_description.is_on_fn(self.coordinator)
