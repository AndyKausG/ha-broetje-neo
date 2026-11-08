"""Base entity for the Brötje NEO integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL, DEFAULT_MODEL, DEFAULT_NAME, DOMAIN, MANUFACTURER
from .coordinator import BroetjeNeoCoordinator


class BroetjeNeoEntity(CoordinatorEntity[BroetjeNeoCoordinator]):
    """Common base: device info, unique id, translated name."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BroetjeNeoCoordinator, description: EntityDescription) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer=MANUFACTURER,
            model=entry.data.get(CONF_MODEL) or DEFAULT_MODEL,
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        )
        if description.translation_key is None:
            self._attr_translation_key = description.key
