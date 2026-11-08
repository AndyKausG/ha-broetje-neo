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
        "switch.wp_price_lock",
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


# --------------------------------------------------------------- safety
async def test_unsafe_values_rejected(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.ROOM_SETPOINT, 30)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.DHW_NORMAL, 65)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.COOLING_RLT_MIN, 15)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.OPERATING_MODE, 0)  # "off"
    for reg in (
        r.RETURN_SETPOINT_ACTIVE,
        r.OUTDOOR_VALUE,
        r.SPEED_SETPOINT,
        r.STAGE2_ACTIVE,
        r.RESET_FAULT,
        r.EXT_SPEED_REQUEST,
    ):
        with pytest.raises(HomeAssistantError):
            await coordinator.async_write(reg, 1)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.EVU_VALUE, 1)  # never force release
    assert all(not c.writes for c in fake_client.instances)
    assert "off" not in hass.states.get("select.wp_operating_mode").attributes["options"]


async def test_dhw_min_not_above_normal(hass: HomeAssistant, fake_client, config_entry) -> None:
    fake_client.holding[105] = 460  # normal 46 °C, min 45 °C
    await _setup(hass, config_entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.wp_dhw_minimum_temperature", "value": 48.0},
            blocking=True,
        )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.wp_dhw_normal_temperature", "value": 42.0},
            blocking=True,
        )
    assert fake_client.holding[106] == 450


# ----------------------------------------------------------- price lock
async def _lock(hass: HomeAssistant, on: bool) -> None:
    await hass.services.async_call(
        "switch",
        "turn_on" if on else "turn_off",
        {"entity_id": "switch.wp_price_lock"},
        blocking=True,
    )


async def test_price_lock_on_off(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    assert hass.states.get("switch.wp_price_lock").state == STATE_OFF
    await _lock(hass, True)
    assert fake_client.holding[149] == 0 and fake_client.holding[150] == 1
    assert hass.states.get("switch.wp_price_lock").state == STATE_ON
    await _lock(hass, False)
    assert fake_client.holding[150] == 0
    assert hass.states.get("switch.wp_price_lock").state == STATE_OFF
    # minimum pause between locks
    with pytest.raises(HomeAssistantError, match="Mindestpause"):
        await _lock(hass, True)
    assert fake_client.holding[150] == 0


async def test_price_lock_refused_when_cold(hass: HomeAssistant, fake_client, config_entry) -> None:
    fake_client.input[10] = (-120) & 0xFFFF  # -12 °C
    await _setup(hass, config_entry)
    with pytest.raises(HomeAssistantError, match="Außentemperatur"):
        await _lock(hass, True)
    assert fake_client.holding[150] == 0


async def test_price_lock_max_duration(
    hass: HomeAssistant, fake_client, config_entry, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, config_entry)
    await _lock(hass, True)
    coordinator = config_entry.runtime_data
    coordinator._lock_started -= coordinator.price_lock_max_s + 1  # noqa: SLF001
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert fake_client.holding[150] == 0


async def test_price_lock_released_when_getting_cold(
    hass: HomeAssistant, fake_client, config_entry, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, config_entry)
    await _lock(hass, True)
    fake_client.input[10] = (-110) & 0xFFFF
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert fake_client.holding[150] == 0


async def test_stale_price_lock_released_on_start(
    hass: HomeAssistant, fake_client, config_entry
) -> None:
    fake_client.holding[149] = 0
    fake_client.holding[150] = 1
    await _setup(hass, config_entry)
    assert fake_client.holding[150] == 0


async def test_price_lock_released_on_unload(
    hass: HomeAssistant, fake_client, config_entry
) -> None:
    await _setup(hass, config_entry)
    await _lock(hass, True)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert fake_client.holding[150] == 0


async def test_price_lock_unsupported(hass: HomeAssistant, fake_client, config_entry) -> None:
    fake_client.missing = {147}
    await _setup(hass, config_entry)
    assert hass.states.get("switch.wp_price_lock").state == STATE_UNAVAILABLE


async def test_readonly_does_not_touch_lock(
    hass: HomeAssistant, fake_client, readonly_entry
) -> None:
    fake_client.holding[150] = 1  # e.g. set by the installer
    await _setup(hass, readonly_entry)
    assert await hass.config_entries.async_unload(readonly_entry.entry_id)
    assert fake_client.holding[150] == 1
