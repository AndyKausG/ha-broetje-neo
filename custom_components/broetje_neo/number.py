"""Writable setpoints for the Brötje NEO integration."""

from __future__ import annotations

from dataclasses import dataclass, replace

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import registers as r
from .const import CONF_PV_MAX_POWER, DEFAULT_PV_MAX_POWER
from .coordinator import BroetjeConfigEntry
from .entity import BroetjeNeoEntity
from .safety import SETTING_LIMITS

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class BroetjeNumberDescription(NumberEntityDescription):
    """Number description."""

    register: r.Register


def _setpoint(
    key: str, reg: r.Register, *, step: float = 0.5, enabled: bool = True
) -> BroetjeNumberDescription:
    lim = SETTING_LIMITS[reg.address]
    return BroetjeNumberDescription(
        key=key,
        register=reg,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=lim.vmin,
        native_max_value=lim.vmax,
        native_step=step,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=enabled,
    )


# Only safe user settings; ranges come from safety.SETTING_LIMITS.
NUMBERS: tuple[BroetjeNumberDescription, ...] = (
    _setpoint("room_setpoint", r.ROOM_SETPOINT),
    _setpoint("dhw_normal_setpoint", r.DHW_NORMAL),
    _setpoint("dhw_min_setpoint", r.DHW_MIN),
    _setpoint("cooling_return_min", r.COOLING_RLT_MIN),
    _setpoint("mkr1_room_setpoint", r.MKR1_ROOM_SETPOINT, enabled=False),
    _setpoint("mkr1_cooling_return_min", r.MKR1_COOLING_RLT_MIN, enabled=False),
    _setpoint("mkr2_room_setpoint", r.MKR2_ROOM_SETPOINT, enabled=False),
    _setpoint("mkr2_cooling_return_min", r.MKR2_COOLING_RLT_MIN, enabled=False),
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
    async_add_entities(
        BroetjeNeoNumber(coordinator, d)
        for d in descriptions
        if coordinator.entity_allowed("number", d.key)
    )


class BroetjeNeoNumber(BroetjeNeoEntity, NumberEntity):
    """Writable holding register."""

    entity_description: BroetjeNumberDescription

    @property
    def native_value(self) -> float | None:
        """Return current register value."""
        value = self.coordinator.value(self.entity_description.register)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write value (DHW minimum must stay below DHW normal)."""
        key = self.entity_description.key
        if key == "dhw_min_setpoint":
            normal = self.coordinator.value(r.DHW_NORMAL)
            if normal is not None and value > normal:
                raise HomeAssistantError(
                    f"WW-Minimaltemperatur ({value} °C) darf nicht über der "
                    f"WW-Normaltemperatur ({normal} °C) liegen"
                )
        if key == "dhw_normal_setpoint":
            minimum = self.coordinator.value(r.DHW_MIN)
            if minimum is not None and value < minimum:
                raise HomeAssistantError(
                    f"WW-Normaltemperatur ({value} °C) darf nicht unter der "
                    f"WW-Minimaltemperatur ({minimum} °C) liegen"
                )
        await self.coordinator.async_write(self.entity_description.register, value)
