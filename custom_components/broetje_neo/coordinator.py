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

from .const import (
    CONF_PV_WATCHDOG,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_PV_WATCHDOG,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MIN_WRITE_INTERVAL,
    MODBUS_TIMEOUT,
)
from .registers import (
    PV_POWER,
    READ_BLOCKS,
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
        scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan),
        )
        self._client = AsyncModbusTcpClient(
            entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            timeout=MODBUS_TIMEOUT,
        )
        self._unit = entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
        self._lock = asyncio.Lock()
        self._last_write: dict[int, float] = {}
        self._pv_watchdog = entry.options.get(CONF_PV_WATCHDOG, DEFAULT_PV_WATCHDOG)
        # monotonic time of the last explicit PV power write; None means
        # "never written in this HA run" -> stale values get reset.
        self._pv_last_set: float | None = None
        self.optional_blocks_ok: dict[int, bool] = {}

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
        return data

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

    async def _write_raw(self, reg: Register, word: int) -> None:
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
        _LOGGER.debug("Wrote register %s = %s", reg.address, word)

    async def async_write(self, reg: Register, value: float, *, refresh: bool = True) -> None:
        """Write a scaled value to a holding register."""
        try:
            word = encode(reg, value)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        if reg is PV_POWER:
            self._pv_last_set = time.monotonic()
        await self._write_raw(reg, word)
        if self.data is not None:
            self.data[Table.HOLDING][reg.address] = word
            self.async_update_listeners()
        if refresh:
            await self.async_request_refresh()

    async def async_shutdown_pv(self) -> None:
        """Set PV power target to 0 on unload/stop."""
        if not self._pv_watchdog or self.data is None:
            return
        if raw_value(PV_POWER, self.data[Table.HOLDING]):
            try:
                await self._write_raw(PV_POWER, 0)
            except HomeAssistantError as err:
                _LOGGER.error("Could not reset PV power target: %s", err)

    async def async_close(self) -> None:
        """Close the connection."""
        async with self._lock:
            self._client.close()

    # -------------------------------------------------------------- helpers
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
