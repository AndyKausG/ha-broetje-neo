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
    assert st("number.wp_room_setpoint_heating_curve_shift").state == "21.5"


async def test_write_number_and_select(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.wp_room_setpoint_heating_curve_shift", "value": 22.0},
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
        "number.wp_room_setpoint_heating_curve_shift",
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
    assert hass.states.get("number.wp_room_setpoint_heating_curve_shift") is not None
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
    assert hass.states.get("number.wp_room_setpoint_heating_curve_shift") is None
    assert hass.states.get("select.wp_operating_mode") is None


async def test_disabling_write_removes_entities(
    hass: HomeAssistant, fake_client, config_entry
) -> None:
    await _setup(hass, config_entry)
    reg = er.async_get(hass)
    assert reg.async_get("number.wp_room_setpoint_heating_curve_shift") is not None
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_ALLOW_WRITE: False, CONF_ALLOW_PV: False}
    )
    await hass.async_block_till_done()
    assert reg.async_get("number.wp_room_setpoint_heating_curve_shift") is None
    assert reg.async_get("number.wp_pv_power") is None
    assert reg.async_get("sensor.wp_outdoor_temperature") is not None


# --------------------------------------------------------------- safety
async def test_unsafe_values_rejected(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.ROOM_SETPOINT, 30)
    with pytest.raises(HomeAssistantError):
        await coordinator.async_write(r.DHW_NORMAL, 52)
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
    fake_client.holding[105] = 420  # normal 42 °C
    fake_client.holding[106] = 430  # min 43 °C
    await _setup(hass, config_entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.wp_dhw_minimum_frost_protection", "value": 44.0},
            blocking=True,
        )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.wp_dhw_normal_temperature", "value": 42.0},
            blocking=True,
        )
    assert fake_client.holding[106] == 430


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


# ------------------------------------------------------- efficiency check
async def test_efficiency_check_sensor(hass: HomeAssistant, fake_client, readonly_entry) -> None:
    hass.states.async_set("sensor.wohnzimmer", "21.4", {"device_class": "temperature"})
    entry = MockConfigEntry(
        domain=readonly_entry.domain,
        data=readonly_entry.data,
        options={"room_sensors": ["sensor.wohnzimmer"], "heating_system": "underfloor"},
        unique_id="adv",
    )
    await _setup(hass, entry)
    st = hass.states.get("sensor.wp_efficiency_check")
    assert st.state == "collecting"
    assert st.attributes["data_days"] == 0
    assert isinstance(st.attributes["hints"], list)
    assert hass.states.get("sensor.wp_compressor_starts_24_h") is not None
    assert hass.states.get("sensor.wp_room_temperature_7_days").state == "21.4"
    # read-only: the check never writes
    assert all(not c.writes for c in fake_client.instances)


async def test_efficiency_data_persisted(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    assert coordinator.tracker.buckets
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.runtime_data.tracker.first_ts == coordinator.tracker.first_ts


async def test_fault_hint_immediately(hass: HomeAssistant, fake_client, readonly_entry) -> None:
    fake_client.input[26] = 1
    await _setup(hass, readonly_entry)
    st = hass.states.get("sensor.wp_efficiency_check")
    assert st.state == "collecting"
    assert any(h["id"] == "fault" for h in st.attributes["hints"])


async def test_price_lock_daily_limit(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    coordinator._locked_today_s()  # noqa: SLF001 - init day
    coordinator._lock_day_s = 6 * 3600  # noqa: SLF001
    with pytest.raises(HomeAssistantError, match="Tageslimit"):
        await _lock(hass, True)
    assert fake_client.holding[150] == 0


async def test_price_lock_option_capped(hass: HomeAssistant, fake_client, config_entry) -> None:
    entry = MockConfigEntry(
        domain=config_entry.domain,
        data=config_entry.data,
        options={**config_entry.options, "price_lock_max_minutes": 300},
        unique_id="cap",
    )
    await _setup(hass, entry)
    assert entry.runtime_data.price_lock_max_s == 120 * 60


# ------------------------------------------- price lock via external switch
async def _setup_shelly(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"relay": {}}})
    assert await async_setup_component(
        hass,
        "switch",
        {
            "switch": [
                {
                    "platform": "template",
                    "switches": {
                        "shelly": {
                            "value_template": "{{ is_state('input_boolean.relay', 'on') }}",
                            "turn_on": {
                                "action": "input_boolean.turn_on",
                                "target": {"entity_id": "input_boolean.relay"},
                            },
                            "turn_off": {
                                "action": "input_boolean.turn_off",
                                "target": {"entity_id": "input_boolean.relay"},
                            },
                        }
                    },
                }
            ]
        },
    )
    await hass.async_block_till_done()
    entry = MockConfigEntry(
        domain=config_entry.domain,
        data=config_entry.data,
        options={**config_entry.options, "price_lock_switch": "switch.shelly"},
        unique_id="shelly",
    )
    await _setup(hass, entry)
    return entry


async def test_shelly_lock(hass: HomeAssistant, fake_client, config_entry) -> None:
    entry = await _setup_shelly(hass, config_entry)
    assert hass.states.get("switch.wp_price_lock").state == STATE_OFF
    await _lock(hass, True)
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.relay").state == STATE_ON
    assert hass.states.get("switch.shelly").state == STATE_ON
    assert fake_client.holding[150] == 0  # no Modbus override used
    fake_client.input[32] = 0  # heat pump reports EVU lock
    coordinator = entry.runtime_data
    coordinator._lock_verify_at -= 1000  # noqa: SLF001
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.relay").state == STATE_ON
    assert coordinator.price_lock_problem is None
    await _lock(hass, False)
    assert hass.states.get("input_boolean.relay").state == STATE_OFF


async def test_shelly_lock_without_effect(hass: HomeAssistant, fake_client, config_entry) -> None:
    entry = await _setup_shelly(hass, config_entry)
    await _lock(hass, True)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    coordinator._lock_verify_at -= 1000  # noqa: SLF001 - EVU release stays 1
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.relay").state == STATE_OFF
    assert coordinator.price_lock_problem
    st = hass.states.get("sensor.wp_efficiency_check")
    assert st.attributes["hints"][0]["id"] == "price_lock_ineffective"
    coordinator._lock_ended = None  # noqa: SLF001 - skip pause check
    with pytest.raises(HomeAssistantError, match="nicht an"):
        await _lock(hass, True)


async def test_shelly_stale_on_is_released(hass: HomeAssistant, fake_client, config_entry) -> None:
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"relay": {}}})
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": "input_boolean.relay"}, blocking=True
    )
    await _setup_shelly(hass, config_entry)
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.relay").state == STATE_OFF


# --------------------------------------------------- grid operator (§14a)
async def test_grid_lock_has_priority(
    hass: HomeAssistant, fake_client, config_entry, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.wp_pv_power", "value": 1500}, blocking=True
    )
    assert fake_client.holding[125] == 1500
    fake_client.input[32] = 0  # EVU input: grid operator locks
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.wp_grid_operator_control").state == STATE_ON
    assert fake_client.holding[125] == 0  # PV target dropped
    with pytest.raises(HomeAssistantError, match="Netzbetreiber"):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": "number.wp_pv_power", "value": 1000}, blocking=True
        )
    with pytest.raises(HomeAssistantError, match="Netzbetreiber"):
        await _lock(hass, True)
    assert fake_client.holding[150] == 0
    # grid lock time counts, and a pause follows its end
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data
    assert coordinator._grid_day_s > 0  # noqa: SLF001
    fake_client.input[32] = 1
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.wp_grid_operator_control").state == STATE_OFF
    with pytest.raises(HomeAssistantError, match="Mindestpause"):
        await _lock(hass, True)


async def test_grid_signal_entity(hass: HomeAssistant, fake_client, config_entry) -> None:
    hass.states.async_set("binary_sensor.steuerbox", "on")
    entry = MockConfigEntry(
        domain=config_entry.domain,
        data=config_entry.data,
        options={**config_entry.options, "grid_signal": "binary_sensor.steuerbox"},
        unique_id="grid",
    )
    await _setup(hass, entry)
    assert hass.states.get("binary_sensor.wp_grid_operator_control").state == STATE_ON
    with pytest.raises(HomeAssistantError, match="Netzbetreiber"):
        await _lock(hass, True)


async def test_own_lock_is_not_grid_lock(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await _lock(hass, True)
    fake_client.input[32] = 0  # caused by our own lock
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.wp_grid_operator_control").state == STATE_OFF
