"""Diagnostics for the Brötje NEO integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import BroetjeConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BroetjeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics: config and raw register dump."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "optional_blocks_ok": coordinator.optional_blocks_ok,
        "registers": coordinator.diagnostics(),
    }
