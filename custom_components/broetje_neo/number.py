"""Writable setpoints for the Brötje NEO integration."""

from __future__ import annotations

from dataclasses import dataclass, replace

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import registers as r
from .const import CONF_PV_MAX_POWER, DEFAULT_PV_MAX_POWER
from .coordinator import BroetjeConfigEntry
from .entity import BroetjeNeoEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class BroetjeNumberDescription(NumberEntityDescription):
    """Number description."""

    register: r.Register


def _setpoint(
    key: str,
    reg: r.Register,
    vmin: float,
    vmax: float,
    *,
    step: float = 0.5,
    enabled: bool = True,
    config: bool = False,
) -> BroetjeNumberDescription:
    return BroetjeNumberDescription(
        key=key,
        register=reg,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=vmin,
        native_max_value=vmax,
        native_step=step,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=enabled,
        entity_category=EntityCategory.CONFIG if config else None,
    )


NUMBERS: tuple[BroetjeNumberDescription, ...] = (
    _setpoint("room_setpoint", r.ROOM_SETPOINT, 10, 30),
    _setpoint("dhw_normal_setpoint", r.DHW_NORMAL, 30, 65),
    _setpoint("dhw_min_setpoint", r.DHW_MIN, 20, 65),
    _setpoint("cooling_return_min", r.COOLING_RLT_MIN, 15, 25),
    _setpoint("return_setpoint", r.RETURN_SETPOINT, 15, 60, enabled=False, config=True),
    _setpoint("mkr1_room_setpoint", r.MKR1_ROOM_SETPOINT, 10, 30, enabled=False),
    _setpoint("mkr1_flow_setpoint", r.MKR1_FLOW_SETPOINT, 15, 60, enabled=False, config=True),
    _setpoint("mkr1_cooling_return_min", r.MKR1_COOLING_RLT_MIN, 15, 25, enabled=False),
    _setpoint("mkr2_room_setpoint", r.MKR2_ROOM_SETPOINT, 10, 30, enabled=False),
    _setpoint("mkr2_flow_setpoint", r.MKR2_FLOW_SETPOINT, 15, 60, enabled=False, config=True),
    _setpoint("mkr2_cooling_return_min", r.MKR2_COOLING_RLT_MIN, 15, 25, enabled=False),
    _setpoint(
        "outdoor_override_value", r.OUTDOOR_VALUE, -30, 45, step=0.1, enabled=False, config=True
    ),
    _setpoint("buffer_override_value", r.BUFFER_VALUE, 0, 80, step=0.1, enabled=False, config=True),
    _setpoint("dhw_override_value", r.DHW_VALUE, 0, 80, step=0.1, enabled=False, config=True),
    BroetjeNumberDescription(
        key="pv_power",
        register=r.PV_POWER,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=DEFAULT_PV_MAX_POWER,
        native_step=50,
        mode=NumberMode.BOX,
    ),
    BroetjeNumberDescription(
        key="compressor_speed_setpoint",
        register=r.SPEED_SETPOINT,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroetjeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up numbers."""
    coordinator = entry.runtime_data
    pv_max = entry.options.get(CONF_PV_MAX_POWER, DEFAULT_PV_MAX_POWER)
    descriptions = [
        replace(d, native_max_value=pv_max) if d.key == "pv_power" else d for d in NUMBERS
    ]
    async_add_entities(BroetjeNeoNumber(coordinator, d) for d in descriptions)


class BroetjeNeoNumber(BroetjeNeoEntity, NumberEntity):
    """Writable holding register."""

    entity_description: BroetjeNumberDescription

    @property
    def native_value(self) -> float | None:
        """Return current register value."""
        value = self.coordinator.value(self.entity_description.register)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write value."""
        await self.coordinator.async_write(self.entity_description.register, value)
