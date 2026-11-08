"""Config flow tests."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.broetje_neo.const import (
    CONF_ALLOW_PV,
    CONF_ALLOW_WRITE,
    CONF_PV_MAX_POWER,
    CONF_PV_WATCHDOG,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

USER_INPUT = {"name": "WP", "host": "192.0.2.10", "port": 502, "unit_id": 1, "model": "BLW NEO 18b"}


async def test_user_flow(hass: HomeAssistant, fake_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "192.0.2.10"


async def test_user_flow_cannot_connect(hass: HomeAssistant, fake_client) -> None:
    fake_client.fail_reads = True
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow(hass: HomeAssistant, fake_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "heating_system": "radiator",
            "room_sensors": ["sensor.wohnzimmer"],
            "expected_spf": 3.8,
            CONF_ALLOW_WRITE: True,
            CONF_ALLOW_PV: False,
            CONF_SCAN_INTERVAL: 30,
            CONF_PV_WATCHDOG: 0,
            CONF_PV_MAX_POWER: 5000,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_SCAN_INTERVAL] == 30
    assert config_entry.options[CONF_ALLOW_WRITE] is True
    assert config_entry.options[CONF_ALLOW_PV] is False
    assert config_entry.options["heating_system"] == "radiator"
    assert config_entry.options["room_sensors"] == ["sensor.wohnzimmer"]
    assert config_entry.options["expected_spf"] == 3.8
