"""Dashboard package: heating start / heating season (no recorder needed)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import parse_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

DASH_PACKAGE = Path(__file__).parent.parent / "extras" / "packages" / "broetje_neo_dashboard.yaml"


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def _setup(hass: HomeAssistant, config_entry) -> MockConfigEntry:
    hass.config.language = "de"
    entry = MockConfigEntry(
        domain=config_entry.domain,
        data={**config_entry.data, "name": "Brötje NEO"},
        options=config_entry.options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    conf = parse_yaml(DASH_PACKAGE.read_text(encoding="utf-8"))
    assert await async_setup_component(hass, "template", {"template": conf["template"]})
    await _settle(hass)
    return entry


async def test_dashboard_heating_start(
    hass: HomeAssistant, fake_client, config_entry, freezer
) -> None:
    fake_client.input[41] = 0  # no demand at start
    entry = await _setup(hass, config_entry)
    coordinator = entry.runtime_data
    last = "sensor.wpd_heizanforderung_zuletzt_gestartet"
    season = "sensor.wpd_heizperiode_gestartet"

    async def demand(value: int) -> None:
        fake_client.input[41] = value
        await coordinator.async_refresh()
        await _settle(hass)

    await demand(20)
    t0 = hass.states.get(season).state
    assert t0 not in ("unknown", "unavailable")
    assert hass.states.get(last).state == t0
    assert hass.states.get("sensor.wpd_verdichter_heizen_zuletzt_gestartet").state == t0

    # short pause: same heating season, new "last" timestamp
    await demand(0)
    freezer.tick(timedelta(days=2))
    await demand(20)
    assert hass.states.get(season).state == t0
    assert hass.states.get(last).state != t0

    # summer break > 14 days: new heating season
    await demand(0)
    freezer.tick(timedelta(days=30))
    await demand(20)
    t1 = hass.states.get(season).state
    assert t1 != t0
    assert dt_util.parse_datetime(t1) > dt_util.parse_datetime(t0) + timedelta(days=30)
