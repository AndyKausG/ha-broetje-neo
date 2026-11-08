"""Pytest configuration for the Brötje NEO tests.

The integration tests need ``pytest-homeassistant-custom-component``.
The pure tests (register map, efficiency check, analysis script) run without
Home Assistant: they load their module straight from the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # Home Assistant test harness available?
    import pytest_homeassistant_custom_component  # noqa: F401

    HAS_HA = True
except ImportError:  # pragma: no cover - plain environment
    HAS_HA = False


_HA_MARKERS = ("homeassistant", "custom_components.broetje_neo")


def pytest_ignore_collect(collection_path, config):
    """Skip the HA based tests when the harness is not installed.

    A test module counts as HA based when it imports Home Assistant, the harness
    or the integration package (the pure tests load their module straight from
    the file instead). No list to maintain for new test files.
    """
    if HAS_HA or collection_path.suffix != ".py" or not collection_path.name.startswith("test_"):
        return None
    try:
        source = collection_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return True if any(marker in source for marker in _HA_MARKERS) else None


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


if HAS_HA:
    from collections.abc import Generator
    from unittest.mock import patch

    from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
    import pytest
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.broetje_neo.const import (
        CONF_ALLOW_PRICE_LOCK,
        CONF_ALLOW_PV,
        CONF_ALLOW_WRITE,
        CONF_UNIT_ID,
        DOMAIN,
    )

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
            options={CONF_ALLOW_WRITE: True, CONF_ALLOW_PV: True, CONF_ALLOW_PRICE_LOCK: True},
        )

    @pytest.fixture
    def readonly_entry() -> MockConfigEntry:
        """Config entry with default (read-only) options."""
        return MockConfigEntry(
            domain=DOMAIN,
            title="WP",
            unique_id="192.0.2.10:502:1",
            data={CONF_NAME: "WP", CONF_HOST: "192.0.2.10", CONF_PORT: 502, CONF_UNIT_ID: 1},
        )
