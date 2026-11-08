"""Data update coordinator for the Brötje NEO-RKM."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from . import advisor, registers as r, safety
from .const import (
    CONF_ALLOW_PRICE_LOCK,
    CONF_ALLOW_PV,
    CONF_ALLOW_WRITE,
    CONF_EXPECTED_SPF,
    CONF_GRID_SIGNAL,
    CONF_HEATING_CIRCUIT,
    CONF_HEATING_LIMIT,
    CONF_HEATING_SYSTEM,
    CONF_PRICE_LOCK_MAX,
    CONF_PRICE_LOCK_SWITCH,
    CONF_PV_MAX_POWER,
    CONF_PV_WATCHDOG,
    CONF_ROOM_GROUPING,
    CONF_ROOM_SENSORS,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_ALLOW_PRICE_LOCK,
    DEFAULT_ALLOW_PV,
    DEFAULT_ALLOW_WRITE,
    DEFAULT_HEATING_CIRCUIT,
    DEFAULT_HEATING_SYSTEM,
    DEFAULT_PV_MAX_POWER,
    DEFAULT_PV_WATCHDOG,
    DEFAULT_ROOM_GROUPING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MIN_WRITE_INTERVAL,
    MODBUS_TIMEOUT,
    write_allowed,
)
from .registers import (
    EVU_ACTIVE,
    EVU_RELEASE,
    EVU_VALUE,
    PV_POWER,
    READ_BLOCKS,
    T_OUTDOOR,
    Block,
    Register,
    Table,
    decode,
    encode,
    raw_value,
)

_LOGGER = logging.getLogger(__name__)

type RegisterData = dict[Table, dict[int, int]]
type BroetjeConfigEntry = ConfigEntry[BroetjeNeoCoordinator]


class BroetjeNeoCoordinator(DataUpdateCoordinator[RegisterData]):
    """Poll the NEO-RKM and serialize all Modbus access."""

    config_entry: BroetjeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BroetjeConfigEntry) -> None:
        """Initialize."""
        opts = entry.options
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self._client = AsyncModbusTcpClient(
            entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            timeout=MODBUS_TIMEOUT,
        )
        self._unit = entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
        self._lock = asyncio.Lock()
        self._last_write: dict[int, float] = {}
        self.optional_blocks_ok: dict[int, bool] = {}

        self.allow_write: bool = opts.get(CONF_ALLOW_WRITE, DEFAULT_ALLOW_WRITE)
        self.allow_pv: bool = opts.get(CONF_ALLOW_PV, DEFAULT_ALLOW_PV)
        self.allow_price_lock: bool = opts.get(CONF_ALLOW_PRICE_LOCK, DEFAULT_ALLOW_PRICE_LOCK)
        self.pv_max: float = opts.get(CONF_PV_MAX_POWER, DEFAULT_PV_MAX_POWER)

        # PV watchdog (writes too, so only with PV control enabled)
        self._pv_watchdog = opts.get(CONF_PV_WATCHDOG, DEFAULT_PV_WATCHDOG) if self.allow_pv else 0
        # monotonic time of the last explicit PV power write; None means
        # "never written in this HA run" -> stale values get reset.
        self._pv_last_set: float | None = None

        # Price lock guard rails
        self.price_lock_max_s = 60 * min(
            opts.get(CONF_PRICE_LOCK_MAX, safety.PRICE_LOCK_MAX_MINUTES_DEFAULT),
            safety.PRICE_LOCK_MAX_MINUTES_LIMIT,
        )
        self._lock_started: float | None = None
        self._lock_ended: float | None = None
        # optional external switch (e.g. Shelly + NC relay in the EVU line)
        self.lock_switch: str | None = opts.get(CONF_PRICE_LOCK_SWITCH) or None
        self._lock_verify_at: float | None = None
        self.price_lock_problem: str | None = None
        # Grid operator control (EVU lock / §14a): always has priority
        self.grid_signal: str | None = opts.get(CONF_GRID_SIGNAL) or None
        self._grid_was_active = False
        self._grid_last_tick: float | None = None
        self._lock_day: str | None = None
        self._lock_day_s: float = 0.0  # locked seconds today (finished own locks)
        self._grid_day_s: float = 0.0  # seconds controlled by the grid operator today

        # Efficiency check
        self.heating_system: str = opts.get(CONF_HEATING_SYSTEM, DEFAULT_HEATING_SYSTEM)
        self.room_sensors: list[str] = list(opts.get(CONF_ROOM_SENSORS, []))
        self.expected_spf: float | None = opts.get(CONF_EXPECTED_SPF) or None
        self.heating_limit_setting: float | None = opts.get(CONF_HEATING_LIMIT) or None
        self.tracker = advisor.Tracker()
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.advisor")
        self.figures: dict[str, float | None] = {}
        self.heat_limit_detail: dict[str, Any] = {}
        self.hints: list[advisor.Hint] = []
        self.circuit_setting: str = opts.get(CONF_HEATING_CIRCUIT, DEFAULT_HEATING_CIRCUIT)
        self.room_grouping: str = opts.get(CONF_ROOM_GROUPING, DEFAULT_ROOM_GROUPING)
        self._room_info: dict[str, dict[str, Any]] = {}
        self.circuit = "hkr"
        self.coldest_room: str | None = None
        self.rooms: list[dict[str, Any]] = []
        self.advice_status: str = "collecting"
        self.data_days: float = 0.0

    # ------------------------------------------------------------------ I/O
    async def _ensure_connected(self) -> None:
        if not self._client.connected:
            await self._client.connect()
        if not self._client.connected:
            raise ConnectionError("cannot connect to NEO-RKM")

    async def _read_block(self, block: Block) -> list[int]:
        if block.table is Table.INPUT:
            result = await self._client.read_input_registers(
                block.start, count=block.count, device_id=self._unit
            )
        else:
            result = await self._client.read_holding_registers(
                block.start, count=block.count, device_id=self._unit
            )
        if result.isError() or len(result.registers) != block.count:
            raise ModbusException(f"invalid response for {block}: {result}")
        return list(result.registers)

    async def _async_update_data(self) -> RegisterData:
        data: RegisterData = {Table.INPUT: {}, Table.HOLDING: {}}
        async with self._lock:
            try:
                await self._ensure_connected()
                for block in READ_BLOCKS:
                    try:
                        words = await self._read_block(block)
                    except ModbusException as err:
                        if not block.optional:
                            raise
                        if self.optional_blocks_ok.get(block.start, True):
                            _LOGGER.info("Optional block %s not available: %s", block, err)
                        self.optional_blocks_ok[block.start] = False
                        continue
                    self.optional_blocks_ok[block.start] = True
                    for offset, word in enumerate(words):
                        data[block.table][block.start + offset] = word
            except (ModbusException, ConnectionError, OSError, TimeoutError) as err:
                self._client.close()
                raise UpdateFailed(f"Modbus read failed: {err}") from err

        self._track_grid_control(data)
        await self._async_grid_priority(data)
        await self._async_pv_watchdog(data)
        await self._async_price_lock_guard(data)
        self._update_advice(data)
        return data

    # ---------------------------------------------------- efficiency check
    async def async_load_advisor(self) -> None:
        """Restore collected operating data."""
        self.tracker = advisor.Tracker.from_dict(await self._store.async_load())

    async def async_save_advisor(self) -> None:
        """Persist collected operating data now."""
        await self._store.async_save(self.tracker.to_dict())

    def _sensor_floor(self, eid: str) -> Any:
        """Floor entry of a sensor (via its area or its device's area), or None."""
        ent = er.async_get(self.hass).async_get(eid)
        if ent is None:
            return None
        area_id = ent.area_id
        if area_id is None and ent.device_id:
            dev = dr.async_get(self.hass).async_get(ent.device_id)
            area_id = dev.area_id if dev is not None else None
        if area_id is None:
            return None
        area = ar.async_get(self.hass).async_get_area(area_id)
        if area is None or not area.floor_id:
            return None
        return fr.async_get(self.hass).async_get_floor(area.floor_id)

    def _room_temperatures(self) -> dict[str, float]:
        """Current room temperatures, one value per floor or per sensor.

        Also fills ``self._room_info`` (display name, floor level, member sensors).
        """
        values: dict[str, list[float]] = {}
        info: dict[str, dict[str, Any]] = {}
        for eid in self.room_sensors:
            # grouping comes from the configuration, so a sensor that is
            # temporarily unavailable keeps its room/floor in the list
            st = self.hass.states.get(eid)
            name = st.name if st is not None else eid
            floor = self._sensor_floor(eid) if self.room_grouping == "floor" else None
            if floor is not None:
                key = f"floor:{floor.floor_id}"
                entry = info.setdefault(
                    key, {"name": floor.name, "level": floor.level, "sensors": []}
                )
            else:
                key = eid
                entry = info.setdefault(key, {"name": name, "level": None, "sensors": []})
            entry["sensors"].append(name)
            if st is not None and (v := advisor.safe_float(st.state)) is not None:
                values.setdefault(key, []).append(v)
        self._room_info = info
        return {k: round(sum(v) / len(v), 2) for k, v in values.items()}

    def _update_advice(self, data: RegisterData) -> None:
        inp, hold = data[Table.INPUT], data[Table.HOLDING]

        def val(reg: Register) -> float | None:
            v = decode(reg, inp if reg.table is Table.INPUT else hold)
            return None if v is None else float(v)

        def flag(reg: Register) -> bool | None:
            raw = raw_value(reg, inp)
            return None if raw is None else raw != 0

        suction, evap = val(r.T_SUCTION_GAS), val(r.T_EVAPORATION)
        mkr1_flow, mkr2_flow = val(r.T_MKR1_FLOW_SETPOINT), val(r.T_MKR2_FLOW_SETPOINT)

        def active(flow: float | None, mode_reg: Register) -> bool:
            mode = raw_value(mode_reg, hold)
            return flow is not None and flow > 0 and mode is not None and mode != 0

        if self.circuit_setting in ("hkr", "mkr1", "mkr2"):
            self.circuit = self.circuit_setting
        elif active(mkr1_flow, r.MKR1_MODE):
            self.circuit = "mkr1"
        elif active(mkr2_flow, r.MKR2_MODE):
            self.circuit = "mkr2"
        else:
            self.circuit = "hkr"
        mkr_flow = {"mkr1": mkr1_flow, "mkr2": mkr2_flow}.get(self.circuit, mkr1_flow)
        room_set_reg = {
            "mkr1": r.MKR1_ROOM_SETPOINT,
            "mkr2": r.MKR2_ROOM_SETPOINT,
        }.get(self.circuit, r.ROOM_SETPOINT)
        room_set = val(room_set_reg)
        rooms = self._room_temperatures()
        now = time.time()
        self.tracker.feed(
            advisor.Sample(
                ts=now,
                t_out=val(r.T_OUTDOOR),
                t_out_delayed=val(r.T_OUTDOOR_DELAYED),
                rl_set=val(r.T_RETURN_SETPOINT),
                mkr_set=mkr_flow,
                room_set=room_set,
                t_flow=val(r.T_FLOW),
                t_return=val(r.T_RETURN),
                compressor=flag(r.HEAT_PUMP_RUNNING),
                demand=r.DEMANDS.get(raw_value(r.DEMAND, inp)),
                defrost=flag(r.FOUR_WAY_VALVE),
                superheat=None if None in (suction, evap) else suction - evap,
                room=round(sum(rooms.values()) / len(rooms), 2) if rooms else None,
                rooms=rooms or None,
                e_th_total=val(r.E_TH_TOTAL),
                e_el_total=val(r.E_EL_TOTAL),
                e_th_heat=val(r.E_TH_HEATING),
                e_el_heat=val(r.E_EL_HEATING),
                e_th_dhw=val(r.E_TH_DHW),
                e_el_dhw=val(r.E_EL_DHW),
            )
        )
        self._store.async_delay_save(self.tracker.to_dict, 300)
        self.data_days = round(self.tracker.data_days(now), 1)
        self.figures = self.tracker.figures(now)
        self.heat_limit_detail = self.tracker.heat_limit_detail(now)
        ctx = advisor.Context(
            heating_system=self.heating_system,
            room_setpoint=room_set,
            circuit=self.circuit,
            dhw_setpoint=val(r.DHW_NORMAL),
            expected_spf=self.expected_spf,
            heating_limit=self.heating_limit_setting,
            fault=bool(flag(r.FAULT)),
            has_room_sensor=bool(self.room_sensors),
        )
        rooms_list = []
        for room in self.tracker.room_detail(now):
            # only rooms/floors of the current configuration; history of removed
            # sensors or of the other grouping mode must not drive the advice
            meta = self._room_info.get(room["entity_id"])
            if meta is not None:
                rooms_list.append({**room, **meta})
        if rooms_list and all(x["level"] is not None for x in rooms_list):
            rooms_list.sort(key=lambda x: x["level"], reverse=True)
        else:
            rooms_list.sort(key=lambda x: x["avg_7d"])
        self.rooms = rooms_list
        with_dev = [x for x in rooms_list if x["dev_7d"] is not None]
        self.coldest_room = min(with_dev, key=lambda x: x["dev_7d"])["name"] if with_dev else None
        hints = advisor.advise(self.figures, ctx, self.data_days, self.rooms)
        if self.data_days < advisor.MIN_DAYS:
            # only immediate findings until enough data is collected
            hints = [
                h for h in hints if h.id in ("fault", "no_room_sensor", "room_set_high", "dhw_high")
            ]
        if self.price_lock_problem:
            hints.insert(
                0,
                advisor.Hint(
                    "price_lock_ineffective",
                    "warning",
                    "Preissperre wirkt nicht",
                    self.price_lock_problem,
                    "Preissperre bleibt deaktiviert, bis die Integration neu geladen wird. "
                    "Anschluss am EVU-Eingang von einer Elektrofachkraft prüfen lassen.",
                    "Fachbetrieb",
                ),
            )
        self.hints = hints
        self.advice_status = advisor.status(hints, self.data_days)

    # ------------------------------------------------------------ safety
    async def _async_pv_watchdog(self, data: RegisterData) -> None:
        """Reset a stale PV power target to 0."""
        if not self._pv_watchdog:
            return
        current = raw_value(PV_POWER, data[Table.HOLDING])
        if not current:
            return
        stale = self._pv_last_set is None or (
            time.monotonic() - self._pv_last_set > self._pv_watchdog
        )
        if not stale:
            return
        _LOGGER.warning(
            "PV power target %s W not refreshed within %s s, resetting to 0",
            current,
            self._pv_watchdog,
        )
        try:
            await self._write_raw(PV_POWER, 0)
            data[Table.HOLDING][PV_POWER.address] = 0
        except HomeAssistantError as err:
            _LOGGER.error("PV watchdog reset failed: %s", err)

    def _lock_active(self, data: RegisterData | None) -> bool:
        if self.lock_switch:
            st = self.hass.states.get(self.lock_switch)
            return st is not None and st.state == "on"
        if data is None:
            return False
        return raw_value(EVU_ACTIVE, data[Table.HOLDING]) == 1

    def _lock_supported(self) -> bool:
        if self.lock_switch:
            st = self.hass.states.get(self.lock_switch)
            return st is not None and st.state in ("on", "off")
        return self.data is not None and EVU_ACTIVE.address in self.data[Table.HOLDING]

    async def _switch(self, on: bool) -> None:
        if not self.allow_price_lock:
            raise HomeAssistantError("Preissperre ist in den Optionen deaktiviert")
        try:
            await self.hass.services.async_call(
                "switch",
                "turn_on" if on else "turn_off",
                {"entity_id": self.lock_switch},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - any failure of the external device
            raise HomeAssistantError(
                f"Schalten von {self.lock_switch} fehlgeschlagen: {err}"
            ) from err

    async def _engage_lock(self) -> None:
        if self.lock_switch:
            await self._switch(True)
            self._lock_verify_at = time.monotonic() + safety.PRICE_LOCK_VERIFY_SECONDS
        else:
            await self._write_raw(EVU_VALUE, 0)
            await self._write_raw(EVU_ACTIVE, 1)

    async def _async_price_lock_guard(self, data: RegisterData) -> None:
        """Release the price lock when it is stale, too long or too cold."""
        if not self.allow_price_lock or not self._lock_active(data):
            return
        reason = None
        if self._lock_started is None:
            reason = "left over from a previous run"
        elif (
            self.lock_switch
            and self._lock_verify_at is not None
            and time.monotonic() > self._lock_verify_at
            and raw_value(EVU_RELEASE, data[Table.INPUT])
        ):
            reason = "no effect at the heat pump"
            self.price_lock_problem = (
                f"Die Sperre über {self.lock_switch} kommt an der Wärmepumpe nicht an "
                "(EVU-Freigabe bleibt aktiv). Verdrahtung prüfen lassen."
            )
        elif time.monotonic() - self._lock_started > self.price_lock_max_s:
            reason = f"maximum duration of {self.price_lock_max_s // 60} min reached"
        elif self._locked_today_s() >= safety.PRICE_LOCK_MAX_MINUTES_PER_DAY * 60:
            reason = "daily maximum reached"
        else:
            t_out = decode(T_OUTDOOR, data[Table.INPUT])
            if t_out is not None and t_out < safety.PRICE_LOCK_MIN_OUTDOOR_TEMP:
                reason = f"outdoor temperature {t_out} °C too low"
        if reason is None:
            return
        _LOGGER.warning("Releasing price lock: %s", reason)
        try:
            await self._release_price_lock()
            if not self.lock_switch:
                data[Table.HOLDING][EVU_ACTIVE.address] = 0
        except HomeAssistantError as err:
            _LOGGER.error("Releasing price lock failed: %s", err)

    # ------------------------------------------------- grid operator control
    def _grid_active(self, data: RegisterData | None) -> bool:
        """True while the grid operator locks/limits the heat pump.

        EVU release off (reg. 32) while no own price lock is engaged, or the
        optional external signal (e.g. control box / SG-Ready via a sensor).
        """
        if self.grid_signal:
            st = self.hass.states.get(self.grid_signal)
            if st is not None and st.state == "on":
                return True
        if data is None or self._lock_active(data):
            return False
        release = raw_value(EVU_RELEASE, data[Table.INPUT])
        return release == 0

    @property
    def grid_control_active(self) -> bool:
        """Public state for the binary sensor."""
        return self._grid_active(self.data)

    def _track_grid_control(self, data: RegisterData) -> None:
        now = time.monotonic()
        active = self._grid_active(data)
        self._locked_today_s()  # roll the day if needed
        if self._grid_was_active and self._grid_last_tick is not None:
            self._grid_day_s += min(now - self._grid_last_tick, 120.0)
        if self._grid_was_active and not active:
            self._lock_ended = now  # pause also after a grid operator lock
        self._grid_was_active = active
        self._grid_last_tick = now

    @property
    def grid_lock_today_min(self) -> float:
        """Minutes the grid operator controlled the heat pump today."""
        self._locked_today_s()
        return round(self._grid_day_s / 60, 0)

    async def _async_grid_priority(self, data: RegisterData) -> None:
        """No PV power target while the grid operator controls the heat pump."""
        if not self.allow_pv or not self._grid_active(data):
            return
        if raw_value(PV_POWER, data[Table.HOLDING]):
            _LOGGER.info("Grid operator control active, PV power target set to 0")
            try:
                await self._write_raw(PV_POWER, 0)
                data[Table.HOLDING][PV_POWER.address] = 0
            except HomeAssistantError as err:
                _LOGGER.error("Could not reset PV power target: %s", err)

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _locked_today_s(self) -> float:
        """Locked seconds today incl. a running lock."""
        if self._lock_day != self._today():
            self._lock_day, self._lock_day_s, self._grid_day_s = self._today(), 0.0, 0.0
        running = time.monotonic() - self._lock_started if self._lock_started else 0.0
        return self._lock_day_s + self._grid_day_s + running

    async def _release_price_lock(self) -> None:
        if self.lock_switch:
            await self._switch(False)
        else:
            await self._write_raw(EVU_ACTIVE, 0)
        self._lock_verify_at = None
        if self._lock_started is not None:
            self._locked_today_s()  # roll the day if needed
            self._lock_day_s += time.monotonic() - self._lock_started
            self._lock_ended = time.monotonic()
        self._lock_started = None

    # ------------------------------------------------------------- writes
    async def _write_raw(self, reg: Register, value: float) -> None:
        """Check the safety policy, encode and write one register."""
        try:
            safety.check_write(
                reg.address,
                value,
                allow_write=self.allow_write,
                allow_pv=self.allow_pv,
                allow_price_lock=self.allow_price_lock,
                pv_max=self.pv_max,
            )
            word = encode(reg, value)
        except (safety.WriteNotAllowed, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        if reg.table is not Table.HOLDING:
            raise HomeAssistantError(f"register {reg.address} is read-only")
        last = self._last_write.get(reg.address)
        if last is not None:
            wait = MIN_WRITE_INTERVAL - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        async with self._lock:
            try:
                await self._ensure_connected()
                result = await self._client.write_register(reg.address, word, device_id=self._unit)
                if result.isError():
                    raise ModbusException(str(result))
            except (ModbusException, ConnectionError, OSError, TimeoutError) as err:
                self._client.close()
                raise HomeAssistantError(f"Writing register {reg.address} failed: {err}") from err
            finally:
                self._last_write[reg.address] = time.monotonic()
        if self.data is not None:
            self.data[Table.HOLDING][reg.address] = word
        _LOGGER.debug("Wrote register %s = %s", reg.address, word)

    async def async_write(self, reg: Register, value: float, *, refresh: bool = True) -> None:
        """Write a scaled value to a holding register (safety checked)."""
        if reg is PV_POWER and value > 0 and self._grid_active(self.data):
            raise HomeAssistantError(
                "Netzbetreiber steuert die Wärmepumpe gerade (EVU/§14a), keine PV-Vorgabe"
            )
        await self._write_raw(reg, value)
        if reg is PV_POWER:
            self._pv_last_set = time.monotonic()
        self.async_update_listeners()
        if refresh:
            await self.async_request_refresh()

    async def async_set_price_lock(self, on: bool) -> None:
        """Lock (on) or return to normal operation (off)."""
        if not on:
            if self._lock_active(self.data):
                await self._release_price_lock()
            self.async_update_listeners()
            await self.async_request_refresh()
            return
        if self._lock_active(self.data):
            return
        if not self._lock_supported():
            raise HomeAssistantError("Preissperre ist nicht verfügbar")
        if self._grid_active(self.data):
            raise HomeAssistantError(
                "Netzbetreiber steuert die Wärmepumpe gerade (EVU/§14a), keine eigene Sperre"
            )
        if self.price_lock_problem:
            raise HomeAssistantError(self.price_lock_problem)
        if self._lock_ended is not None:
            pause = time.monotonic() - self._lock_ended
            need = safety.PRICE_LOCK_MIN_PAUSE_MINUTES * 60
            if pause < need:
                raise HomeAssistantError(
                    f"Preissperre erst in {int((need - pause) // 60) + 1} min wieder möglich "
                    "(Mindestpause zum Schutz der Anlage)"
                )
        if self._locked_today_s() >= safety.PRICE_LOCK_MAX_MINUTES_PER_DAY * 60:
            raise HomeAssistantError(
                "Wärmepumpe heute bereits "
                f"{safety.PRICE_LOCK_MAX_MINUTES_PER_DAY // 60} h gesperrt "
                "(eigene Sperren und Netzbetreiber zusammen, Tageslimit)"
            )
        t_out = self.value(T_OUTDOOR)
        if t_out is None or t_out < safety.PRICE_LOCK_MIN_OUTDOOR_TEMP:
            raise HomeAssistantError(
                f"Preissperre bei Außentemperatur unter "
                f"{safety.PRICE_LOCK_MIN_OUTDOOR_TEMP:.0f} °C nicht erlaubt"
            )
        await self._engage_lock()
        self._lock_started = time.monotonic()
        self.async_update_listeners()
        await self.async_request_refresh()

    @property
    def price_lock_active(self) -> bool | None:
        """Return True while the price lock holds the heat pump."""
        if not self._lock_supported():
            return None
        return self._lock_active(self.data)

    async def async_shutdown(self) -> None:  # type: ignore[override]
        """Hand control back to the heat pump on unload/stop."""
        if self.data is not None:
            if self._pv_watchdog and raw_value(PV_POWER, self.data[Table.HOLDING]):
                try:
                    await self._write_raw(PV_POWER, 0)
                except HomeAssistantError as err:
                    _LOGGER.error("Could not reset PV power target: %s", err)
            if self.allow_price_lock and self._lock_active(self.data):
                try:
                    await self._release_price_lock()
                except HomeAssistantError as err:
                    _LOGGER.error("Could not release price lock: %s", err)
        await self.async_save_advisor()
        await super().async_shutdown()

    async def async_close(self) -> None:
        """Close the connection."""
        async with self._lock:
            self._client.close()

    # -------------------------------------------------------------- helpers
    def entity_allowed(self, platform: str, key: str) -> bool:
        """Return True if the entity may be created with the current options."""
        return write_allowed(platform, key, self.allow_write, self.allow_pv, self.allow_price_lock)

    def value(self, reg: Register) -> float | int | None:
        """Return the decoded value of reg from the last poll."""
        if self.data is None:
            return None
        return decode(reg, self.data[reg.table])

    def raw(self, reg: Register) -> int | None:
        """Return the raw value of reg from the last poll."""
        if self.data is None:
            return None
        return raw_value(reg, self.data[reg.table])

    def diagnostics(self) -> dict[str, Any]:
        """Raw register dump."""
        if self.data is None:
            return {}
        return {
            table.value: {str(k): v for k, v in sorted(regs.items())}
            for table, regs in self.data.items()
        }
