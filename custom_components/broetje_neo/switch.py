"""Price lock switch for the Brötje NEO integration.

Uses the manufacturer's utility-lock override (reg. 149/150) to pause the
heat pump during expensive hours, exactly like a lock signal from the grid
operator. The heat pump is built for such locks. Guard rails (coordinator):
maximum duration, minimum pause between locks, no lock below -10 °C outdoor,
automatic release on HA start/stop. A real utility lock is never overridden.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BroetjeConfigEntry
from .entity import BroetjeNeoEntity

PARALLEL_UPDATES = 1

PRICE_LOCK = SwitchEntityDescription(key="price_lock", icon="mdi:currency-eur-off")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroetjeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the price lock switch."""
    coordinator = entry.runtime_data
    if coordinator.entity_allowed("switch", PRICE_LOCK.key):
        async_add_entities([BroetjePriceLockSwitch(coordinator, PRICE_LOCK)])


class BroetjePriceLockSwitch(BroetjeNeoEntity, SwitchEntity):
    """On = heat pump paused (utility lock), off = normal operation."""

    @property
    def available(self) -> bool:
        """Only available if the controller supports reg. 149/150."""
        return super().available and self.coordinator.price_lock_active is not None

    @property
    def is_on(self) -> bool | None:
        """Return lock state."""
        return self.coordinator.price_lock_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock."""
        await self.coordinator.async_set_price_lock(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Back to normal operation."""
        await self.coordinator.async_set_price_lock(False)
