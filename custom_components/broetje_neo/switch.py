"""Override / request switches for the Brötje NEO integration.

All switches are disabled by default: they take control away from the
heat pump's own controller. Turning a switch off always writes 0, so an
override can never get stuck (cf. ha_heliotherm issue #68).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import registers as r
from .coordinator import BroetjeConfigEntry
from .entity import BroetjeNeoEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class BroetjeSwitchDescription(SwitchEntityDescription):
    """Switch description."""

    register: r.Register


def _sw(key: str, reg: r.Register) -> BroetjeSwitchDescription:
    return BroetjeSwitchDescription(
        key=key,
        register=reg,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    )


SWITCHES: tuple[BroetjeSwitchDescription, ...] = (
    _sw("return_setpoint_active", r.RETURN_SETPOINT_ACTIVE),
    _sw("mkr1_flow_setpoint_active", r.MKR1_FLOW_SETPOINT_ACTIVE),
    _sw("mkr2_flow_setpoint_active", r.MKR2_FLOW_SETPOINT_ACTIVE),
    _sw("external_speed_request", r.EXT_SPEED_REQUEST),
    _sw("external_request", r.EXT_REQUEST),
    _sw("outdoor_override_active", r.OUTDOOR_ACTIVE),
    _sw("buffer_override_active", r.BUFFER_ACTIVE),
    _sw("dhw_override_active", r.DHW_ACTIVE),
    _sw("stage2_value", r.STAGE2_VALUE),
    _sw("stage2_active", r.STAGE2_ACTIVE),
    _sw("evu_release_value", r.EVU_VALUE),
    _sw("evu_release_active", r.EVU_ACTIVE),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroetjeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities(BroetjeNeoSwitch(coordinator, d) for d in SWITCHES)


class BroetjeNeoSwitch(BroetjeNeoEntity, SwitchEntity):
    """Boolean holding register."""

    entity_description: BroetjeSwitchDescription

    @property
    def is_on(self) -> bool | None:
        """Return state."""
        raw = self.coordinator.raw(self.entity_description.register)
        return None if raw is None else raw != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Write 1."""
        await self.coordinator.async_write(self.entity_description.register, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Write 0."""
        await self.coordinator.async_write(self.entity_description.register, 0)
