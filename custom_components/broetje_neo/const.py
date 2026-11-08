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

DEFAULT_NAME: Final = "Brötje NEO"
DEFAULT_MODEL: Final = "BLW NEO"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 15
DEFAULT_PV_WATCHDOG: Final = 120
DEFAULT_PV_MAX_POWER: Final = 6000

MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

# NEO-RKM manual 7734937-01, chapter 7.1: holding registers should not be
# written faster than every 5 seconds.
MIN_WRITE_INTERVAL: Final = 5.0

MODBUS_TIMEOUT: Final = 5
