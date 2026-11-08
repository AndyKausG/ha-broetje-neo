"""Buttons for the Brötje NEO integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import registers as r
from .coordinator import BroetjeConfigEntry
from .entity import BroetjeNeoEntity

PARALLEL_UPDATES = 1

RESET_FAULT = ButtonEntityDescription(key="reset_fault", entity_category=EntityCategory.CONFIG)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroetjeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    if coordinator.entity_allowed("button", RESET_FAULT.key):
        async_add_entities([BroetjeNeoResetButton(coordinator, RESET_FAULT)])


class BroetjeNeoResetButton(BroetjeNeoEntity, ButtonEntity):
    """Fault reset: pulse register 128 (1, then 0 after the write interval)."""

    async def async_press(self) -> None:
        """Pulse the reset register."""
        await self.coordinator.async_write(r.RESET_FAULT, 1, refresh=False)
        await self.coordinator.async_write(r.RESET_FAULT, 0)
