"""Brötje NEO heat pumps via NEO-RKM (Modbus TCP)."""

from __future__ import annotations

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er

from .coordinator import BroetjeConfigEntry, BroetjeNeoCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: BroetjeConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = BroetjeNeoCoordinator(hass, entry)
    await coordinator.async_load_advisor()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    async def _on_stop(_event: Event) -> None:
        await coordinator.async_shutdown()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _async_remove_disallowed_entities(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _async_remove_disallowed_entities(
    hass: HomeAssistant, entry: BroetjeConfigEntry, coordinator: BroetjeNeoCoordinator
) -> None:
    """Remove entities disabled by the options or no longer provided."""
    from .binary_sensor import BINARY_SENSORS
    from .number import NUMBERS
    from .select import SELECTS
    from .sensor import ADVISOR_SENSORS, SENSORS
    from .switch import PRICE_LOCK

    known = (
        {("binary_sensor", d.key) for d in BINARY_SENSORS}
        | {("sensor", d.key) for d in SENSORS + ADVISOR_SENSORS}
        | {("number", d.key) for d in NUMBERS}
        | {("select", d.key) for d in SELECTS}
        | {("switch", PRICE_LOCK.key)}
    )
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = ent.unique_id.removeprefix(prefix)
        if (ent.domain, key) not in known or not coordinator.entity_allowed(ent.domain, key):
            registry.async_remove(ent.entity_id)


async def _async_reload(hass: HomeAssistant, entry: BroetjeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BroetjeConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()
        await coordinator.async_close()
    return unloaded
