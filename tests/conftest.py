"""Fixtures for Brötje NEO tests."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.broetje_neo.const import CONF_UNIT_ID, DOMAIN


def _s16(v: int) -> int:
    return v & 0xFFFF


def default_input() -> dict[int, int]:
    regs = {a: 0 for a in range(10, 46)} | {a: 0 for a in range(60, 76)}
    regs |= {
        10: _s16(-35),  # -3.5 °C
        11: 482,
        12: 312,
        13: 268,
        14: 300,
        15: _s16(-30),
        16: _s16(-500),  # sensor not connected
        17: _s16(-20),
        18: _s16(-80),
        19: 350,
        20: 650,
        21: 52,
        22: 189,
        23: 1,
        25: 1,
        28: 254,  # 25.4 l/min
        29: 450,  # 45.0 %
        30: 38,
        31: _s16(-500),
        32: 1,
        33: _s16(-20),
        34: 280,
        37: 1,
        40: 312,
        41: 20,  # heating
        43: 1234,  # hours DHW (low word)
        45: 5678,
        61: 20000,  # thermal heating kWh
        63: 5000,
        65: 3000,
        67: 1000,
        69: 6000,
        71: 1800,  # W
        73: 23000,
        75: 63,  # 6.3 kW
    }
    return regs


def default_holding() -> dict[int, int]:
    regs = {a: 0 for a in range(100, 151)}
    regs |= {100: 1, 101: 215, 102: 280, 104: 180, 105: 500, 106: 450, 107: 1, 112: 1}
    return regs


@dataclass
class _Result:
    registers: list[int] = field(default_factory=list)
    error: bool = False

    def isError(self) -> bool:  # noqa: N802
        return self.error


class FakeModbusClient:
    """In-memory replacement for AsyncModbusTcpClient."""

    instances: list[FakeModbusClient] = []
    input: dict[int, int] = {}
    holding: dict[int, int] = {}
    fail_reads: bool = False
    missing: set[int] = set()

    def __init__(self, host: str, **kwargs) -> None:
        self.host = host
        self.connected = False
        self.writes: list[tuple[int, int]] = []
        FakeModbusClient.instances.append(self)

    async def connect(self) -> bool:
        self.connected = True
        return True

    def close(self) -> None:
        self.connected = False

    def _read(self, table: dict[int, int], address: int, count: int) -> _Result:
        if FakeModbusClient.fail_reads or address in FakeModbusClient.missing:
            return _Result(error=True)
        return _Result([table.get(a, 0) for a in range(address, address + count)])

    async def read_input_registers(self, address, *, count=1, device_id=1):
        return self._read(FakeModbusClient.input, address, count)

    async def read_holding_registers(self, address, *, count=1, device_id=1):
        return self._read(FakeModbusClient.holding, address, count)

    async def write_register(self, address, value, *, device_id=1):
        self.writes.append((address, value))
        FakeModbusClient.holding[address] = value
        return _Result()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
def fake_client() -> Generator[type[FakeModbusClient]]:
    """Patch the Modbus client everywhere."""
    FakeModbusClient.instances = []
    FakeModbusClient.input = default_input()
    FakeModbusClient.holding = default_holding()
    FakeModbusClient.fail_reads = False
    FakeModbusClient.missing = set()
    with (
        patch(
            "custom_components.broetje_neo.coordinator.AsyncModbusTcpClient",
            FakeModbusClient,
        ),
        patch(
            "custom_components.broetje_neo.config_flow.AsyncModbusTcpClient",
            FakeModbusClient,
        ),
        patch("custom_components.broetje_neo.coordinator.MIN_WRITE_INTERVAL", 0),
    ):
        yield FakeModbusClient


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id="192.0.2.10:502:1",
        data={CONF_NAME: "WP", CONF_HOST: "192.0.2.10", CONF_PORT: 502, CONF_UNIT_ID: 1},
    )
