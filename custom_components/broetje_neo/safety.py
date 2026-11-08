"""Write safety policy.

Single place that decides WHAT may be written and in WHICH range. The
coordinator enforces it for every write, independent of the UI, so neither
an automation nor a service call can bypass it.

Design rule: only settings a home owner can also change at the heat pump's
own user menu, in conservative ranges, plus the two energy functions the
manufacturer provides for external control (PV power target, utility lock).
Everything that bypasses the heat pump's own control logic (fake sensor
values, compressor speed, flow/return overrides, 2nd stage, fault reset,
forcing the utility release) is deliberately NOT writable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from . import registers as r


@dataclass(frozen=True, slots=True)
class Limit:
    """Allowed value range for a register (scaled units)."""

    vmin: float
    vmax: float


# Settings (option "allow_write")
SETTING_LIMITS: Final[dict[int, Limit]] = {
    r.ROOM_SETPOINT.address: Limit(15, 25),
    r.DHW_NORMAL.address: Limit(40, 55),
    r.DHW_MIN.address: Limit(35, 50),
    # below ~18 °C return temperature, underfloor cooling risks condensation
    r.COOLING_RLT_MIN.address: Limit(18, 25),
    r.MKR1_ROOM_SETPOINT.address: Limit(15, 25),
    r.MKR1_COOLING_RLT_MIN.address: Limit(18, 25),
    r.MKR2_ROOM_SETPOINT.address: Limit(15, 25),
    r.MKR2_COOLING_RLT_MIN.address: Limit(18, 25),
}

# Operating modes that may be selected. "off" (0) is excluded on purpose:
# switching a heat pump off remotely in winter risks frost damage.
SAFE_MODES: Final[dict[int, str]] = {
    k: v for k, v in r.WRITABLE_OPERATING_MODES.items() if v != "off"
}
MODE_REGISTERS: Final = frozenset(
    {r.OPERATING_MODE.address, r.MKR1_MODE.address, r.MKR2_MODE.address}
)

# PV (option "allow_pv"): only the power target, the RKM handles thresholds,
# minimum run time and compressor limits itself.
PV_REGISTERS: Final = frozenset({r.PV_POWER.address})

# Price lock (option "allow_price_lock"): utility lock override. Only the
# values "lock" (149=0, 150=1) and "back to normal" (150=0) are possible,
# a real utility lock can never be overridden.
PRICE_LOCK_REGISTERS: Final = frozenset({r.EVU_VALUE.address, r.EVU_ACTIVE.address})

# Price lock guard rails
PRICE_LOCK_MAX_MINUTES_DEFAULT: Final = 120
PRICE_LOCK_MAX_MINUTES_LIMIT: Final = 180
PRICE_LOCK_MIN_PAUSE_MINUTES: Final = 60
PRICE_LOCK_MIN_OUTDOOR_TEMP: Final = -10.0


class WriteNotAllowed(Exception):
    """Raised when a write violates the safety policy."""


def check_write(
    address: int,
    value: float,
    *,
    allow_write: bool,
    allow_pv: bool,
    allow_price_lock: bool,
    pv_max: float,
) -> None:
    """Raise WriteNotAllowed unless the write is permitted."""
    if address in SETTING_LIMITS:
        if not allow_write:
            raise WriteNotAllowed("Einstellungen schreiben ist in den Optionen deaktiviert")
        lim = SETTING_LIMITS[address]
        if not lim.vmin <= value <= lim.vmax:
            raise WriteNotAllowed(
                f"Wert {value} außerhalb des sicheren Bereichs {lim.vmin}–{lim.vmax}"
            )
        return
    if address in MODE_REGISTERS:
        if not allow_write:
            raise WriteNotAllowed("Einstellungen schreiben ist in den Optionen deaktiviert")
        if int(value) not in SAFE_MODES:
            raise WriteNotAllowed(f"Betriebsart {value} ist nicht erlaubt")
        return
    if address in PV_REGISTERS:
        if not allow_pv:
            raise WriteNotAllowed("PV-Steuerung ist in den Optionen deaktiviert")
        if not 0 <= value <= pv_max:
            raise WriteNotAllowed(f"PV-Leistung {value} W außerhalb 0–{pv_max} W")
        return
    if address in PRICE_LOCK_REGISTERS:
        if not allow_price_lock:
            raise WriteNotAllowed("Preissperre ist in den Optionen deaktiviert")
        if address == r.EVU_VALUE.address and value != 0:
            # never force a release: that could override a real utility lock
            raise WriteNotAllowed("EVU-Freigabe darf nicht erzwungen werden")
        if address == r.EVU_ACTIVE.address and value not in (0, 1):
            raise WriteNotAllowed("ungültiger Wert")
        return
    raise WriteNotAllowed(f"Register {address} ist nicht schreibbar")
