"""Serve and register the bundled frontend (card + dashboard strategy)."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = f"/{DOMAIN}_frontend"
JS_FILE = "broetje-neo.js"
_DATA_KEY = f"{DOMAIN}_frontend_registered"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve broetje-neo.js and load it in every browser (once per HA run).

    Skipped when http or frontend is not set up (tests, minimal installs).
    """
    if hass.data.get(_DATA_KEY):
        return
    if hass.http is None or "frontend" not in hass.config.components:
        _LOGGER.debug("http/frontend not loaded, card and strategy not registered")
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    path = Path(__file__).parent / JS_FILE
    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"{URL_BASE}/{JS_FILE}", str(path), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{URL_BASE}/{JS_FILE}?v={version}")
    hass.data[_DATA_KEY] = True
