"""Register decoding tests (no Home Assistant needed)."""

import pytest

from custom_components.broetje_neo import registers as r


def test_int16_signed_scaled() -> None:
    assert r.decode(r.T_OUTDOOR, {10: (-35) & 0xFFFF}) == -3.5


def test_temperature_sentinel() -> None:
    assert r.decode(r.T_SOURCE_OUT, {16: (-500) & 0xFFFF}) is None


def test_uint32_high_word_first() -> None:
    assert r.decode(r.E_TH_TOTAL, {72: 1, 73: 2}) == 65538


def test_uint32_zero_invalid_and_sentinel() -> None:
    assert r.decode(r.E_EL_TOTAL, {68: 0, 69: 0}) is None
    assert r.decode(r.P_EL, {70: 0, 71: 0}) == 0
    assert r.decode(r.P_EL, {70: 0xFFFF, 71: 0xFFFF}) is None


def test_missing_register() -> None:
    assert r.decode(r.HOURS_DHW, {}) is None
    assert r.raw_value(r.HOURS_DHW, {42: 0}) is None


def test_encode() -> None:
    assert r.encode(r.ROOM_SETPOINT, 21.5) == 215
    assert r.encode(r.OUTDOOR_VALUE, -8.5) == (-85) & 0xFFFF
    assert r.encode(r.PV_POWER, 1500) == 1500
    with pytest.raises(ValueError):
        r.encode(r.PV_POWER, -1)
    with pytest.raises(ValueError):
        r.encode(r.E_EL_TOTAL, 1)


def test_blocks_cover_all_registers() -> None:
    regs = [v for v in vars(r).values() if isinstance(v, r.Register)]
    for reg in regs:
        for addr in range(reg.address, reg.address + reg.count):
            assert any(b.table is reg.table and b.contains(addr) for b in r.READ_BLOCKS), (
                f"{reg} not covered"
            )


def test_operating_modes() -> None:
    assert r.OPERATING_MODES[9] == "evu_lock"
    assert 9 not in r.WRITABLE_OPERATING_MODES
