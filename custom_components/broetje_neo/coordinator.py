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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from . import safety
from .const import (
    CONF_ALLOW_PRICE_LOCK,
    CONF_ALLOW_PV,
    CONF_ALLOW_WRITE,
    CONF_PRICE_LOCK_MAX,
    CONF_PV_MAX_POWER,
    CONF_PV_WATCHDOG,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_ALLOW_PRICE_LOCK,
    DEFAULT_ALLOW_PV,
    DEFAULT_ALLOW_WRITE,
    DEFAULT_PV_MAX_POWER,
    DEFAULT_PV_WATCHDOG,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MIN_WRITE_INTERVAL,
    MODBUS_TIMEOUT,
    write_allowed,
)
from .registers import (
    EVU_ACTIVE,
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

        await self._async_pv_watchdog(data)
        await self._async_price_lock_guard(data)
        return data

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
        if data is None:
            return False
        return raw_value(EVU_ACTIVE, data[Table.HOLDING]) == 1

    async def _async_price_lock_guard(self, data: RegisterData) -> None:
        """Release the price lock when it is stale, too long or too cold."""
        if not self.allow_price_lock or not self._lock_active(data):
            return
        reason = None
        if self._lock_started is None:
            reason = "left over from a previous run"
        elif time.monotonic() - self._lock_started > self.price_lock_max_s:
            reason = f"maximum duration of {self.price_lock_max_s // 60} min reached"
        else:
            t_out = decode(T_OUTDOOR, data[Table.INPUT])
            if t_out is not None and t_out < safety.PRICE_LOCK_MIN_OUTDOOR_TEMP:
                reason = f"outdoor temperature {t_out} °C too low"
        if reason is None:
            return
        _LOGGER.warning("Releasing price lock: %s", reason)
        try:
            await self._release_price_lock()
            data[Table.HOLDING][EVU_ACTIVE.address] = 0
        except HomeAssistantError as err:
            _LOGGER.error("Releasing price lock failed: %s", err)

    async def _release_price_lock(self) -> None:
        await self._write_raw(EVU_ACTIVE, 0)
        if self._lock_started is not None:
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
        if self.data is None or EVU_ACTIVE.address not in self.data[Table.HOLDING]:
            raise HomeAssistantError("Preissperre wird von dieser Anlage nicht unterstützt")
        if self._lock_ended is not None:
            pause = time.monotonic() - self._lock_ended
            need = safety.PRICE_LOCK_MIN_PAUSE_MINUTES * 60
            if pause < need:
                raise HomeAssistantError(
                    f"Preissperre erst in {int((need - pause) // 60) + 1} min wieder möglich "
                    "(Mindestpause zum Schutz der Anlage)"
                )
        t_out = self.value(T_OUTDOOR)
        if t_out is None or t_out < safety.PRICE_LOCK_MIN_OUTDOOR_TEMP:
            raise HomeAssistantError(
                f"Preissperre bei Außentemperatur unter "
                f"{safety.PRICE_LOCK_MIN_OUTDOOR_TEMP:.0f} °C nicht erlaubt"
            )
        await self._write_raw(EVU_VALUE, 0)
        await self._write_raw(EVU_ACTIVE, 1)
        self._lock_started = time.monotonic()
        self.async_update_listeners()
        await self.async_request_refresh()

    @property
    def price_lock_active(self) -> bool | None:
        """Return True while the price lock holds the heat pump."""
        if self.data is None or EVU_ACTIVE.address not in self.data[Table.HOLDING]:
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
