"""Constants for the Brötje NEO (NEO-RKM) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "broetje_neo"
MANUFACTURER: Final = "Brötje"

CONF_UNIT_ID: Final = "unit_id"
CONF_MODEL: Final = "model"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_PV_WATCHDOG: Final = "pv_watchdog"
CONF_PV_MAX_POWER: Final = "pv_max_power"
CONF_ALLOW_WRITE: Final = "allow_write"
CONF_ALLOW_PV: Final = "allow_pv"
CONF_ALLOW_PRICE_LOCK: Final = "allow_price_lock"
CONF_PRICE_LOCK_MAX: Final = "price_lock_max_minutes"
CONF_HEATING_SYSTEM: Final = "heating_system"
CONF_PRICE_LOCK_SWITCH: Final = "price_lock_switch"
CONF_ROOM_SENSORS: Final = "room_sensors"
CONF_EXPECTED_SPF: Final = "expected_spf"
HEATING_SYSTEMS: Final = ["underfloor", "radiator", "mixed"]
DEFAULT_HEATING_SYSTEM: Final = "underfloor"

DEFAULT_NAME: Final = "Brötje NEO"
DEFAULT_MODEL: Final = "BLW NEO"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 15
DEFAULT_PV_WATCHDOG: Final = 120
DEFAULT_PV_MAX_POWER: Final = 6000
# Safe defaults: read-only until explicitly enabled in the options.
DEFAULT_ALLOW_WRITE: Final = False
DEFAULT_ALLOW_PV: Final = False
DEFAULT_ALLOW_PRICE_LOCK: Final = False

# Platforms that write to the heat pump.
WRITE_PLATFORMS: Final = frozenset({"number", "select", "switch"})
PV_KEYS: Final = frozenset({"pv_power"})
PRICE_LOCK_KEYS: Final = frozenset({"price_lock"})


def write_allowed(
    platform: str, key: str, allow_write: bool, allow_pv: bool, allow_price_lock: bool
) -> bool:
    """Return True if an entity of platform/key may be created."""
    if platform not in WRITE_PLATFORMS:
        return True
    if key in PV_KEYS:
        return allow_pv
    if key in PRICE_LOCK_KEYS:
        return allow_price_lock
    return allow_write


MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

# NEO-RKM manual 7734937-01, chapter 7.1: holding registers should not be
# written faster than every 5 seconds.
MIN_WRITE_INTERVAL: Final = 5.0

MODBUS_TIMEOUT: Final = 5
