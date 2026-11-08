"""Integration tests with a fake Modbus client."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.broetje_neo import registers as r
from custom_components.broetje_neo.const import (
    CONF_ALLOW_PV,
    CONF_ALLOW_WRITE,
    CONF_PV_WATCHDOG,
)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensors(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    st = hass.states.get
    assert st("sensor.wp_outdoor_temperature").state == "-3.5"
    assert st("sensor.wp_outdoor_temperature").attributes["state_class"] == "measurement"
    assert st("sensor.wp_source_outlet_temperature").state == STATE_UNKNOWN
    assert st("sensor.wp_flow_rate").state == "25.4"
    assert st("sensor.wp_compressor_speed").state == "45.0"
    assert st("sensor.wp_demand").state == "heating"
    assert st("sensor.wp_demand").attributes["raw"] == 20
    assert st("sensor.wp_operating_mode_status").state == "auto"
    assert st("sensor.wp_thermal_energy_total").state == "23000"
    assert st("sensor.wp_spf_total").state == str(round(23000 / 6000, 2))
    assert st("sensor.wp_flow_return_spread").state == "4.4"
    assert st("sensor.wp_superheat").state == "6.0"
    assert st("sensor.wp_cop_calculated").state == "3.5"
    assert st("binary_sensor.wp_compressor").state == STATE_ON
    assert st("binary_sensor.wp_heating").state == STATE_ON
    assert st("binary_sensor.wp_hot_water").state == STATE_OFF
    assert st("binary_sensor.wp_utility_release").state == STATE_ON
    assert st("select.wp_operating_mode").state == "auto"
    assert st("number.wp_room_setpoint").state == "21.5"


async def test_disabled_by_default(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    reg = er.async_get(hass)
    ent = reg.async_get("switch.wp_return_setpoint_override_active")
    assert ent is not None and ent.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_write_number_and_select(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.wp_room_setpoint", "value": 22.0},
        blocking=True,
    )
    assert fake_client.holding[101] == 220
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.wp_operating_mode", "option": "summer"},
        blocking=True,
    )
    assert fake_client.holding[100] == 3
    await hass.async_block_till_done()
    assert hass.states.get("select.wp_operating_mode").state == "summer"


async def test_readonly_mode_shows_unknown(hass: HomeAssistant, fake_client, config_entry) -> None:
    fake_client.holding[100] = 9
    await _setup(hass, config_entry)
    assert hass.states.get("select.wp_operating_mode").state == STATE_UNKNOWN
    assert hass.states.get("sensor.wp_operating_mode_status").state == "evu_lock"


async def test_stale_pv_power_reset_on_start(
    hass: HomeAssistant, fake_client, config_entry
) -> None:
    fake_client.holding[125] = 2000  # left over from previous HA run
    await _setup(hass, config_entry)
    assert fake_client.holding[125] == 0


async def test_pv_watchdog(
    hass: HomeAssistant, fake_client, config_entry, freezer: FrozenDateTimeFactory
) -> None:
    config_entry = MockConfigEntry(
        domain=config_entry.domain,
        data=config_entry.data,
        options={CONF_PV_WATCHDOG: 60, CONF_ALLOW_WRITE: True, CONF_ALLOW_PV: True},
        unique_id="x",
    )
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.wp_pv_power", "value": 1500},
        blocking=True,
    )
    assert fake_client.holding[125] == 1500
    coordinator = config_entry.runtime_data
    # simulate expiry of the watchdog
    coordinator._pv_last_set -= 61  # noqa: SLF001
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert fake_client.holding[125] == 0


async def test_unload_resets_pv(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.wp_pv_power", "value": 1000},
        blocking=True,
    )
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert fake_client.holding[125] == 0


async def test_switch_off_writes_zero(hass: HomeAssistant, fake_client, config_entry) -> None:
    reg = er.async_get(hass)
    await _setup(hass, config_entry)
    reg.async_update_entity("switch.wp_return_setpoint_override_active", disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    fake_client.holding[103] = 1
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.wp_return_setpoint_override_active"},
        blocking=True,
    )
    assert fake_client.holding[103] == 0


async def test_optional_block_missing(hass: HomeAssistant, fake_client, config_entry) -> None:
    fake_client.missing = {42, 147}
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.wp_operating_hours_dhw").state == STATE_UNKNOWN
    assert hass.states.get("sensor.wp_outdoor_temperature").state == "-3.5"


async def test_read_failure_unavailable(
    hass: HomeAssistant, fake_client, config_entry, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, config_entry)
    fake_client.fail_reads = True
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.wp_outdoor_temperature").state == STATE_UNAVAILABLE
    fake_client.fail_reads = False
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.wp_outdoor_temperature").state == "-3.5"


async def test_setup_retry_on_failure(hass: HomeAssistant, fake_client, config_entry) -> None:
    fake_client.fail_reads = True
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_readonly_default(hass: HomeAssistant, fake_client, readonly_entry) -> None:
    """Default options: no write entities, no writes at all (watchdog included)."""
    fake_client.holding[125] = 2000  # stale value must NOT be touched
    await _setup(hass, readonly_entry)
    assert hass.states.get("sensor.wp_outdoor_temperature").state == "-3.5"
    for eid in (
        "number.wp_room_setpoint",
        "number.wp_pv_power",
        "select.wp_operating_mode",
        "button.wp_reset_fault",
    ):
        assert hass.states.get(eid) is None, eid
    coordinator = readonly_entry.runtime_data
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.ROOM_SETPOINT, 22)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.PV_POWER, 1000)
    assert await hass.config_entries.async_unload(readonly_entry.entry_id)
    assert all(not c.writes for c in fake_client.instances)
    assert fake_client.holding[125] == 2000


async def test_write_without_pv(hass: HomeAssistant, fake_client, readonly_entry) -> None:
    """Settings writable, PV control off."""
    entry = MockConfigEntry(
        domain=readonly_entry.domain,
        data=readonly_entry.data,
        options={CONF_ALLOW_WRITE: True, CONF_ALLOW_PV: False},
        unique_id="y",
    )
    fake_client.holding[125] = 2000
    await _setup(hass, entry)
    assert hass.states.get("number.wp_room_setpoint") is not None
    assert hass.states.get("select.wp_operating_mode") is not None
    assert hass.states.get("number.wp_pv_power") is None
    coordinator = entry.runtime_data
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.PV_POWER, 1000)
    assert fake_client.holding[125] == 2000  # watchdog inactive


async def test_pv_without_write(hass: HomeAssistant, fake_client, readonly_entry) -> None:
    """PV control on, settings read-only."""
    entry = MockConfigEntry(
        domain=readonly_entry.domain,
        data=readonly_entry.data,
        options={CONF_ALLOW_WRITE: False, CONF_ALLOW_PV: True},
        unique_id="z",
    )
    await _setup(hass, entry)
    assert hass.states.get("number.wp_pv_power") is not None
    assert hass.states.get("number.wp_room_setpoint") is None
    assert hass.states.get("select.wp_operating_mode") is None


async def test_disabling_write_removes_entities(
    hass: HomeAssistant, fake_client, config_entry
) -> None:
    await _setup(hass, config_entry)
    reg = er.async_get(hass)
    assert reg.async_get("number.wp_room_setpoint") is not None
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_ALLOW_WRITE: False, CONF_ALLOW_PV: False}
    )
    await hass.async_block_till_done()
    assert reg.async_get("number.wp_room_setpoint") is None
    assert reg.async_get("number.wp_pv_power") is None
    assert reg.async_get("sensor.wp_outdoor_temperature") is not None
