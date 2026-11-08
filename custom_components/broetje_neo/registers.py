"""Register map of the Brötje NEO-RKM Modbus interface.

Source: Brötje NEO-RKM Montageanleitung 7734937-01 (05.07.2019),
chapter 7.1, tables 4 (read access) and 5 (write access).

This module is the single source of truth for addresses, data types and
scaling. It has no Home Assistant dependencies so it can be unit tested
in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Table(StrEnum):
    """Modbus register table."""

    INPUT = "input"  # function code 04
    HOLDING = "holding"  # function code 03 / 06


class DType(StrEnum):
    """Register data type."""

    INT16 = "int16"
    UINT16 = "uint16"
    UINT32 = "uint32"  # two registers, high word first


@dataclass(frozen=True, slots=True)
class Register:
    """A single (logical) Modbus register."""

    table: Table
    address: int
    dtype: DType = DType.INT16
    scale: float = 1.0
    # Raw value that marks "sensor not present / no data".
    sentinel: int | None = None
    # Treat a raw 0 as invalid (used for lifetime counters to avoid
    # bogus resets in long-term statistics on transient read glitches).
    zero_invalid: bool = False

    @property
    def count(self) -> int:
        """Number of 16 bit registers occupied."""
        return 2 if self.dtype is DType.UINT32 else 1


@dataclass(frozen=True, slots=True)
class Block:
    """A contiguous block that is read in one request."""

    table: Table
    start: int
    count: int
    # Optional blocks may be missing on older firmware; a failure does
    # not fail the whole update.
    optional: bool = False

    def contains(self, address: int) -> bool:
        """Return True if address is inside this block."""
        return self.start <= address < self.start + self.count


READ_BLOCKS: Final[tuple[Block, ...]] = (
    Block(Table.INPUT, 10, 32),  # 10..41
    Block(Table.INPUT, 42, 4, optional=True),  # 42..45 operating hours
    Block(Table.INPUT, 60, 16),  # 60..75 energy / power
    Block(Table.HOLDING, 100, 35),  # 100..134
    Block(Table.HOLDING, 147, 4, optional=True),  # 147..150
)

TEMP_SENTINEL: Final = -500  # -50.0 °C -> sensor not connected
U16_SENTINEL: Final = 0xFFFF
U32_SENTINEL: Final = 0xFFFFFFFF


def _temp(address: int, table: Table = Table.INPUT) -> Register:
    return Register(table, address, DType.INT16, 0.1, sentinel=TEMP_SENTINEL)


def _flag(address: int, table: Table = Table.INPUT) -> Register:
    return Register(table, address, DType.INT16)


def _u32(address: int, scale: float = 1.0, zero_invalid: bool = False) -> Register:
    return Register(
        Table.INPUT,
        address,
        DType.UINT32,
        scale,
        sentinel=U32_SENTINEL,
        zero_invalid=zero_invalid,
    )


def _setp(address: int) -> Register:
    """Holding register temperature setpoint, 0.1 °C."""
    return Register(Table.HOLDING, address, DType.INT16, 0.1)


def _bool(address: int) -> Register:
    return Register(Table.HOLDING, address, DType.UINT16)


# --- Table 4: read access (function code 04) -------------------------------
T_OUTDOOR = _temp(10)
T_DHW = _temp(11)
T_FLOW = _temp(12)
T_RETURN = _temp(13)
T_BUFFER = _temp(14)
T_SOURCE_IN = _temp(15)
T_SOURCE_OUT = _temp(16)
T_SUCTION_GAS = _temp(17)
T_EVAPORATION = _temp(18)
T_CONDENSATION = _temp(19)
T_HOT_GAS = _temp(20)
P_LOW = Register(Table.INPUT, 21, DType.INT16, 0.1)
P_HIGH = Register(Table.INPUT, 22, DType.INT16, 0.1)
HEATING_PUMP = _flag(23)
BUFFER_PUMP = _flag(24)
HEAT_PUMP_RUNNING = _flag(25)
FAULT = _flag(26)
FOUR_WAY_VALVE = _flag(27)  # defrost / reversing operation
FLOW_RATE = Register(Table.INPUT, 28, DType.INT16, 0.1)  # l/min
COMPRESSOR_SPEED = Register(Table.INPUT, 29, DType.INT16, 0.1)  # ‰ -> %
COP = Register(Table.INPUT, 30, DType.INT16, 0.1)
T_FRESH_WATER = _temp(31)
EVU_RELEASE = _flag(32)  # utility release: on = operation released
T_OUTDOOR_DELAYED = _temp(33)
T_RETURN_SETPOINT = _temp(34)  # return / storage setpoint (WNA dependent)
T_MKR1_FLOW_SETPOINT = _temp(35)
T_MKR2_FLOW_SETPOINT = _temp(36)
SOURCE_FAN = _flag(37)  # source pump / fan
DHW_PRIORITY = _flag(38)
PASSIVE_COOLING = _flag(39)
EXPANSION_VALVE = Register(Table.INPUT, 40, DType.INT16, 0.1)  # ‰ -> %
DEMAND = Register(Table.INPUT, 41, DType.INT16)
HOURS_DHW = _u32(42)
HOURS_HEATING = _u32(44)
E_TH_HEATING = _u32(60, zero_invalid=True)
E_EL_HEATING = _u32(62, zero_invalid=True)
E_TH_DHW = _u32(64, zero_invalid=True)
E_EL_DHW = _u32(66, zero_invalid=True)
E_EL_TOTAL = _u32(68, zero_invalid=True)
P_EL = _u32(70)  # W
E_TH_TOTAL = _u32(72, zero_invalid=True)
P_TH = _u32(74, 0.1)  # kW

# --- Table 5: write access (function code 03/06) ---------------------------
OPERATING_MODE = Register(Table.HOLDING, 100, DType.UINT16)
ROOM_SETPOINT = _setp(101)
RETURN_SETPOINT = _setp(102)
RETURN_SETPOINT_ACTIVE = _bool(103)
COOLING_RLT_MIN = _setp(104)
DHW_NORMAL = _setp(105)
DHW_MIN = _setp(106)
MKR1_MODE = Register(Table.HOLDING, 107, DType.UINT16)
MKR1_ROOM_SETPOINT = _setp(108)
MKR1_FLOW_SETPOINT = _setp(109)
MKR1_FLOW_SETPOINT_ACTIVE = _bool(110)
MKR1_COOLING_RLT_MIN = _setp(111)
MKR2_MODE = Register(Table.HOLDING, 112, DType.UINT16)
MKR2_ROOM_SETPOINT = _setp(113)
MKR2_FLOW_SETPOINT = _setp(114)
MKR2_FLOW_SETPOINT_ACTIVE = _bool(115)
MKR2_COOLING_RLT_MIN = _setp(116)
EXT_SPEED_REQUEST = _bool(117)
PV_POWER = Register(Table.HOLDING, 125, DType.UINT16)  # W
SPEED_SETPOINT = Register(Table.HOLDING, 126, DType.INT16, 0.1)  # ‰ -> %
EXT_REQUEST = _bool(127)
RESET_FAULT = _bool(128)
OUTDOOR_VALUE = _setp(129)
OUTDOOR_ACTIVE = _bool(130)
BUFFER_VALUE = _setp(131)
BUFFER_ACTIVE = _bool(132)
DHW_VALUE = _setp(133)
DHW_ACTIVE = _bool(134)
STAGE2_VALUE = _bool(147)
STAGE2_ACTIVE = _bool(148)
EVU_VALUE = _bool(149)
EVU_ACTIVE = _bool(150)

# --- Enumerations ----------------------------------------------------------
OPERATING_MODES: Final[dict[int, str]] = {
    0: "off",
    1: "auto",
    2: "cooling",
    3: "summer",
    4: "continuous",
    5: "setback",
    6: "holiday",
    7: "party",
    # informative only, must not be written
    8: "bake_out",
    9: "evu_lock",
    10: "main_switch_off",
}
WRITABLE_OPERATING_MODES: Final[dict[int, str]] = {
    k: v for k, v in OPERATING_MODES.items() if k <= 7
}

DEMANDS: Final[dict[int, str]] = {
    0: "none",
    10: "cooling",
    20: "heating",
    30: "hot_water",
    40: "external",  # reported by Heliotherm users, not in NEO manual
}


def _to_signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def raw_value(reg: Register, regs: dict[int, int]) -> int | None:
    """Return the raw integer value of reg from an address->word map."""
    hi = regs.get(reg.address)
    if hi is None:
        return None
    if reg.dtype is DType.UINT32:
        lo = regs.get(reg.address + 1)
        if lo is None:
            return None
        return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)
    if reg.dtype is DType.INT16:
        return _to_signed16(hi & 0xFFFF)
    return hi & 0xFFFF


def decode(reg: Register, regs: dict[int, int]) -> float | int | None:
    """Decode a register to its scaled value, None if invalid."""
    raw = raw_value(reg, regs)
    if raw is None:
        return None
    if reg.sentinel is not None and raw == reg.sentinel:
        return None
    if reg.zero_invalid and raw == 0:
        return None
    if reg.scale == 1.0:
        return raw
    return round(raw * reg.scale, 2)


def encode(reg: Register, value: float) -> int:
    """Encode a scaled value into a 16 bit word for writing."""
    if reg.dtype is DType.UINT32:
        raise ValueError("UINT32 registers are read-only")
    raw = round(value / reg.scale)
    if reg.dtype is DType.INT16:
        if not -0x8000 <= raw <= 0x7FFF:
            raise ValueError(f"value {value} out of INT16 range")
        return raw & 0xFFFF
    if not 0 <= raw <= 0xFFFF:
        raise ValueError(f"value {value} out of UINT16 range")
    return raw
