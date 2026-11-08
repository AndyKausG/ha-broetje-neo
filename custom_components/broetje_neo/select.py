"""Operating mode selects for the Brötje NEO integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import registers as r
from .coordinator import BroetjeConfigEntry
from .entity import BroetjeNeoEntity

PARALLEL_UPDATES = 1

_OPTIONS = list(r.WRITABLE_OPERATING_MODES.values())
_REVERSE = {v: k for k, v in r.WRITABLE_OPERATING_MODES.items()}


@dataclass(frozen=True, kw_only=True)
class BroetjeSelectDescription(SelectEntityDescription):
    """Select description."""

    register: r.Register


SELECTS: tuple[BroetjeSelectDescription, ...] = (
    BroetjeSelectDescription(
        key="operating_mode",
        options=_OPTIONS,
        register=r.OPERATING_MODE,
    ),
    BroetjeSelectDescription(
        key="mkr1_operating_mode",
        options=_OPTIONS,
        register=r.MKR1_MODE,
        entity_registry_enabled_default=False,
    ),
    BroetjeSelectDescription(
        key="mkr2_operating_mode",
        options=_OPTIONS,
        register=r.MKR2_MODE,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroetjeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    coordinator = entry.runtime_data
    async_add_entities(BroetjeNeoSelect(coordinator, d) for d in SELECTS)


class BroetjeNeoSelect(BroetjeNeoEntity, SelectEntity):
    """Operating mode select (values 8-10 are read-only and shown as unknown)."""

    entity_description: BroetjeSelectDescription

    @property
    def current_option(self) -> str | None:
        """Return current mode."""
        raw = self.coordinator.raw(self.entity_description.register)
        return r.WRITABLE_OPERATING_MODES.get(raw) if raw is not None else None

    async def async_select_option(self, option: str) -> None:
        """Write the mode."""
        await self.coordinator.async_write(self.entity_description.register, _REVERSE[option])
