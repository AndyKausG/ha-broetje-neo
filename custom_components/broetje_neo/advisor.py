"""Efficiency check: collects real operating data and derives advice.

Pure Python (no Home Assistant imports) so it can be unit tested directly.

The tracker is fed with one sample per poll and aggregates into hourly
buckets (kept 14 days) plus completed compressor runs and daily energy
counter snapshots. From that, key figures and plain-language hints are
derived. Hints are suggestions only; the integration never changes
settings by itself.

Guide values: Deutsche Umwelthilfe, FactSheet "Ratgeber zur optimalen
Einstellung der Wärmepumpe" (01/2023) – flat and low heating curve, lower
the flow temperature in 1 K steps (~2.5 % per K), heating limit ~15 °C,
compare the seasonal performance factor with the planning value. Other
thresholds are common rules of thumb and marked as such.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import statistics as st
from typing import Any

HOUR = 3600
DAY = 24 * HOUR
KEEP_S = 14 * DAY
MAX_DT = 120  # s; longer gaps (outages) are not counted as runtime
MIN_DAYS = 3  # data needed before advice is given

# max. flow/return spread in heating mode (rule of thumb)
SPREAD_LIMITS = {"underfloor": 6.0, "radiator": 8.0, "mixed": 7.0}

# Heating curve of the NEO-RWP: return setpoint at 18 / 0 / -15 °C outdoor.
# Factory setting for underfloor heating (BLW NEO operating manual 7709599-04).
CURVE_POINTS = (18.0, 0.0, -15.0)
FACTORY_CURVE_UNDERFLOOR = {18.0: 22.0, 0.0: 27.0, -15.0: 30.0}
MENU_CURVE = "Hauptmenü → Heizkreis → Heizkurve"
MENU_CURVE_M1 = "Hauptmenü → Mischer 1 → Heizkurve"


@dataclass
class Sample:
    """One poll worth of values (None = not available)."""

    ts: float
    t_out: float | None = None
    t_out_delayed: float | None = None
    rl_set: float | None = None  # return setpoint of the controller (heating curve)
    mkr_set: float | None = None  # flow setpoint of mixing circuit 1 (reg. 35)
    room_set: float | None = None
    t_flow: float | None = None
    t_return: float | None = None
    compressor: bool | None = None
    demand: str | None = None  # "heating", "hot_water", ...
    defrost: bool | None = None
    superheat: float | None = None
    room: float | None = None  # mean of all room sensors
    rooms: dict[str, float] | None = None  # per sensor (e.g. one per floor)
    e_th_total: float | None = None
    e_el_total: float | None = None
    e_th_heat: float | None = None
    e_el_heat: float | None = None
    e_th_dhw: float | None = None
    e_el_dhw: float | None = None


@dataclass
class Bucket:
    """Aggregates of one hour."""

    hour: int  # epoch // 3600
    t_out_sum: float = 0.0
    t_out_n: int = 0
    heat_n: int = 0
    heat_t_out_sum: float = 0.0
    heat_flow_sum: float = 0.0
    heat_return_sum: float = 0.0
    heat_s: float = 0.0
    comp_on_s: float = 0.0
    starts: int = 0
    defrosts: int = 0
    defrosts_warm: int = 0  # defrost starts at outdoor > +5 °C
    sh_sum: float = 0.0
    sh_n: int = 0
    room_sum: float = 0.0
    room_n: int = 0
    rs_sum: float = 0.0  # return setpoint
    rs_x_sum: float = 0.0  # outdoor (delayed) at that time
    rs_n: int = 0
    ms_sum: float = 0.0  # mixing circuit 1 flow setpoint
    ms_x_sum: float = 0.0  # outdoor (delayed) at that time
    ms_n: int = 0
    dev_sum: float = 0.0  # room - room setpoint
    dev_n: int = 0
    # per room sensor: [temp_sum, temp_n, dev_sum, dev_n]
    rooms: dict[str, list[float]] = field(default_factory=dict)

    @property
    def t_out(self) -> float | None:
        return self.t_out_sum / self.t_out_n if self.t_out_n else None


@dataclass
class Hint:
    """A piece of advice."""

    id: str
    severity: str  # "info" | "warning"
    title: str
    finding: str
    suggestion: str
    who: str  # "selbst" | "Fachbetrieb" | "selbst oder Fachbetrieb"


@dataclass
class Tracker:
    """Rolling operating data."""

    buckets: dict[int, Bucket] = field(default_factory=dict)
    runs: list[tuple[float, float]] = field(default_factory=list)  # (end_ts, duration_s)
    counters: dict[str, dict[str, float]] = field(default_factory=dict)  # day -> values
    first_ts: float | None = None
    _last_ts: float | None = None
    _last_comp: bool | None = None
    _run_start: float | None = None
    _last_defrost: bool | None = None

    # ----------------------------------------------------------- feeding
    def feed(self, s: Sample) -> None:
        """Add one sample."""
        if self.first_ts is None:
            self.first_ts = s.ts
        dt = 0.0
        if self._last_ts is not None:
            dt = max(0.0, min(s.ts - self._last_ts, MAX_DT))
        b = self.buckets.setdefault(int(s.ts // HOUR), Bucket(int(s.ts // HOUR)))

        if s.t_out is not None:
            b.t_out_sum += s.t_out
            b.t_out_n += 1
        if s.compressor is not None:
            if s.compressor:
                b.comp_on_s += dt if self._last_comp else 0.0
                if self._last_comp is False:
                    b.starts += 1
                    self._run_start = s.ts
            elif self._last_comp and self._run_start is not None:
                self.runs.append((s.ts, s.ts - self._run_start))
                self._run_start = None
            self._last_comp = s.compressor
        heating = bool(s.compressor) and s.demand == "heating"
        if heating and None not in (s.t_out, s.t_flow, s.t_return):
            b.heat_n += 1
            b.heat_t_out_sum += s.t_out
            b.heat_flow_sum += s.t_flow
            b.heat_return_sum += s.t_return
            b.heat_s += dt
        if s.defrost is not None and s.demand != "cooling":
            # reg. 27 is "defrost / reversing operation": in cooling mode the
            # four-way valve is reversed as well, that is not a defrost
            if s.defrost and self._last_defrost is False:
                b.defrosts += 1
                if s.t_out is not None and s.t_out > 5:
                    b.defrosts_warm += 1
            self._last_defrost = s.defrost
        if s.compressor and s.superheat is not None:
            b.sh_sum += s.superheat
            b.sh_n += 1
        if s.room is not None:
            b.room_sum += s.room
            b.room_n += 1
            if s.room_set is not None:
                b.dev_sum += s.room - s.room_set
                b.dev_n += 1
        for eid, v in (s.rooms or {}).items():
            acc = b.rooms.setdefault(eid, [0.0, 0, 0.0, 0])
            acc[0] += v
            acc[1] += 1
            if s.room_set is not None:
                acc[2] += v - s.room_set
                acc[3] += 1
        x = s.t_out_delayed if s.t_out_delayed is not None else s.t_out
        if s.rl_set is not None and x is not None:
            b.rs_sum += s.rl_set
            b.rs_x_sum += x
            b.rs_n += 1
        if s.mkr_set is not None and x is not None:
            b.ms_sum += s.mkr_set
            b.ms_x_sum += x
            b.ms_n += 1
        self._snapshot_counters(s)
        self._last_ts = s.ts
        self._prune(s.ts)

    def _snapshot_counters(self, s: Sample) -> None:
        values = {
            k: getattr(s, k)
            for k in ("e_th_total", "e_el_total", "e_th_heat", "e_el_heat", "e_th_dhw", "e_el_dhw")
            if getattr(s, k) is not None
        }
        if not values:
            return
        day = str(int(s.ts // DAY))
        self.counters.setdefault(day, {}).update(values)  # last value of the day

    def _prune(self, now: float) -> None:
        h_min = int((now - KEEP_S) // HOUR)
        for h in [h for h in self.buckets if h < h_min]:
            del self.buckets[h]
        self.runs = [r for r in self.runs if r[0] >= now - KEEP_S]
        d_min = int((now - 40 * DAY) // DAY)
        for d in [d for d in self.counters if int(d) < d_min]:
            del self.counters[d]

    # ------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        return {
            "buckets": [asdict(b) for b in self.buckets.values()],
            "runs": self.runs,
            "counters": self.counters,
            "first_ts": self.first_ts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Tracker:
        t = cls()
        if not data:
            return t
        for raw in data.get("buckets", []):
            b = Bucket(**raw)
            t.buckets[b.hour] = b
        t.runs = [tuple(r) for r in data.get("runs", [])]
        t.counters = data.get("counters", {})
        t.first_ts = data.get("first_ts")
        return t

    # ---------------------------------------------------------- figures
    def _window(self, now: float, seconds: float) -> list[Bucket]:
        h_min = int((now - seconds) // HOUR)
        return [b for h, b in sorted(self.buckets.items()) if h >= h_min]

    def data_days(self, now: float) -> float:
        if self.first_ts is None:
            return 0.0
        return min((now - self.first_ts) / DAY, KEEP_S / DAY)

    def figures(self, now: float) -> dict[str, float | None]:
        """Key figures for sensors and rules."""
        d1 = self._window(now, DAY)
        d7 = self._window(now, 7 * DAY)
        runs24 = [d for end, d in self.runs if end >= now - DAY]
        heat_n = sum(b.heat_n for b in d7)
        sh_n = sum(b.sh_n for b in d7)
        room_n = sum(b.room_n for b in d7)
        fig: dict[str, float | None] = {
            "starts_24h": float(sum(b.starts for b in d1)),
            "runtime_24h_h": round(sum(b.comp_on_s for b in d1) / HOUR, 1),
            "run_median_min_24h": round(st.median(runs24) / 60, 0) if runs24 else None,
            "runs_short_share_24h": (
                round(100 * sum(1 for d in runs24 if d < 600) / len(runs24), 0) if runs24 else None
            ),
            "defrosts_24h": float(sum(b.defrosts for b in d1)),
            "defrosts_warm_per_day_7d": round(sum(b.defrosts_warm for b in d7) / 7, 1),
            "heating_spread_7d": (
                round(sum(b.heat_flow_sum - b.heat_return_sum for b in d7) / heat_n, 1)
                if heat_n
                else None
            ),
            "superheat_7d": round(sum(b.sh_sum for b in d7) / sh_n, 1) if sh_n >= 50 else None,
            "room_avg_7d": round(sum(b.room_sum for b in d7) / room_n, 1) if room_n else None,
            "heating_hours_warm_7d": round(
                sum(b.heat_s for b in d7 if b.t_out is not None and b.t_out >= 16) / HOUR, 1
            ),
        }
        dev_n = sum(b.dev_n for b in d7)
        fig["room_dev_7d"] = round(sum(b.dev_sum for b in d7) / dev_n, 2) if dev_n else None
        fig |= self._room_dev_by_weather(now)
        rooms = [r for r in self.room_detail(now) if r["dev_7d"] is not None]
        fig["room_dev_min_7d"] = min(r["dev_7d"] for r in rooms) if rooms else None
        fig["room_spread_7d"] = (
            round(max(r["avg_7d"] for r in rooms) - min(r["avg_7d"] for r in rooms), 1)
            if len(rooms) >= 2
            else None
        )
        fig |= self._curve(now, "rs", "rl_set", with_meta=True)
        fig |= self._curve(now, "ms", "mkr_set")
        fig |= self._spf(now)
        return fig

    def room_detail(self, now: float) -> list[dict[str, Any]]:
        """Per room sensor: 7-day mean, deviation, deviation in cold/mild hours."""
        d7 = {b.hour for b in self._window(now, 7 * DAY)}
        acc: dict[str, dict[str, Any]] = {}
        for b in self._window(now, KEEP_S):
            for eid, (t_sum, t_n, d_sum, d_n) in b.rooms.items():
                r = acc.setdefault(eid, {"t": [0.0, 0], "d": [0.0, 0], "cold": [], "mild": []})
                if b.hour in d7:
                    r["t"][0] += t_sum
                    r["t"][1] += t_n
                    r["d"][0] += d_sum
                    r["d"][1] += d_n
                if d_n and b.t_out is not None:
                    if b.t_out < 3:
                        r["cold"].append(d_sum / d_n)
                    elif b.t_out > 8:
                        r["mild"].append(d_sum / d_n)
        out = []
        for eid, r in acc.items():
            if not r["t"][1]:
                continue
            out.append(
                {
                    "entity_id": eid,
                    "avg_7d": round(r["t"][0] / r["t"][1], 1),
                    "dev_7d": round(r["d"][0] / r["d"][1], 2) if r["d"][1] else None,
                    "dev_cold": round(st.fmean(r["cold"]), 2) if len(r["cold"]) >= 12 else None,
                    "dev_mild": round(st.fmean(r["mild"]), 2) if len(r["mild"]) >= 12 else None,
                }
            )
        return sorted(out, key=lambda r: r["avg_7d"])

    def _room_dev_by_weather(self, now: float) -> dict[str, float | None]:
        """Room deviation from setpoint in cold (< 3 °C) and mild (> 8 °C) hours."""
        cold, mild = [], []
        for b in self._window(now, KEEP_S):
            if not b.dev_n or b.t_out is None:
                continue
            dev = b.dev_sum / b.dev_n
            if b.t_out < 3:
                cold.append(dev)
            elif b.t_out > 8:
                mild.append(dev)
        return {
            "room_dev_cold": round(st.fmean(cold), 2) if len(cold) >= 12 else None,
            "room_dev_mild": round(st.fmean(mild), 2) if len(mild) >= 12 else None,
        }

    def _curve(
        self, now: float, prefix: str = "rs", name: str = "rl_set", *, with_meta: bool = False
    ) -> dict[str, float | None]:
        """Estimate a configured heating curve from a controller setpoint series.

        prefix selects the bucket fields (rs = return setpoint of the direct
        circuit, ms = flow setpoint of mixing circuit 1). Fit setpoint =
        a + b * outdoor over hourly means (14 days) and evaluate at the menu
        points 18 / 0 / -15 °C outdoor. Values far outside the measured
        outdoor range are not reported.
        """
        pts = []
        for b in self._window(now, KEEP_S):
            n = getattr(b, f"{prefix}_n")
            if n >= 10:
                pts.append((getattr(b, f"{prefix}_x_sum") / n, getattr(b, f"{prefix}_sum") / n))
        keys = ((f"{name}_18", 18.0), (f"{name}_0", 0.0), (f"{name}_m15", -15.0))
        res: dict[str, float | None] = {}
        if with_meta:
            res["curve_points"] = float(len(pts))
        res |= {k: None for k, _ in keys}
        if with_meta:
            res["curve_slope"] = None
        xs = [p[0] for p in pts]
        if len(pts) < 12 or max(xs) - min(xs) < 4:
            return res
        mx, my = st.fmean(xs), st.fmean(p[1] for p in pts)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in pts) / sxx
        a = my - slope * mx
        lo, hi = min(xs) - 10, max(xs) + 10  # limit extrapolation
        for key, x in keys:
            if lo <= x <= hi:
                res[key] = round(a + slope * x, 1)
        if with_meta:
            res["curve_slope"] = round(-slope, 2)
        return res

    def _spf(self, now: float) -> dict[str, float | None]:
        """Seasonal performance factor over the last ~30 days."""
        res: dict[str, float | None] = {
            "spf_30d": None,
            "spf_heating_30d": None,
            "spf_dhw_30d": None,
        }
        if len(self.counters) < 2:
            return res
        days = sorted(self.counters, key=int)
        target = int(now // DAY) - 30
        start = next((d for d in days if int(d) >= target), days[0])
        a, b = self.counters[start], self.counters[days[-1]]

        def ratio(th: str, el: str, min_el: float) -> float | None:
            if th not in a or th not in b or el not in a or el not in b:
                return None
            d_el = b[el] - a[el]
            d_th = b[th] - a[th]
            if d_el < min_el or d_th < 0:
                return None
            return round(d_th / d_el, 2)

        res["spf_30d"] = ratio("e_th_total", "e_el_total", 20)
        res["spf_heating_30d"] = ratio("e_th_heat", "e_el_heat", 20)
        res["spf_dhw_30d"] = ratio("e_th_dhw", "e_el_dhw", 10)
        return res


# ------------------------------------------------------------------ rules
@dataclass
class Context:
    """Settings and configuration needed by the rules."""

    heating_system: str = "underfloor"
    room_setpoint: float | None = None
    dhw_setpoint: float | None = None
    expected_spf: float | None = None
    fault: bool = False
    has_room_sensor: bool = False
    circuit: str = "hkr"  # heated circuit: "hkr" (direct) or "mkr1" (mixing circuit 1)


def _fmt(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def advise(
    fig: dict[str, float | None],
    ctx: Context,
    data_days: float,
    rooms: list[dict[str, Any]] | None = None,
) -> list[Hint]:
    """Derive hints from figures. Ordered: warnings first."""
    hints: list[Hint] = []
    add = hints.append
    lim_spread = SPREAD_LIMITS.get(ctx.heating_system, SPREAD_LIMITS["underfloor"])
    system_name = {
        "underfloor": "Fußbodenheizung",
        "radiator": "Heizkörper",
        "mixed": "gemischte Heizflächen",
    }.get(ctx.heating_system, "Fußbodenheizung")

    if ctx.fault:
        add(
            Hint(
                "fault",
                "warning",
                "Störung aktiv",
                "Die Wärmepumpe meldet eine Störung.",
                "Störungscode am Bedienteil ablesen und den Fachbetrieb informieren. "
                "Nicht wiederholt quittieren, ohne die Ursache zu kennen.",
                "Fachbetrieb",
            )
        )

    room = fig.get("room_avg_7d")
    room_set = ctx.room_setpoint
    dev = fig.get("room_dev_7d")
    dev_cold, dev_mild = fig.get("room_dev_cold"), fig.get("room_dev_mild")
    rooms = [r for r in (rooms or []) if r.get("dev_7d") is not None]
    multi = len(rooms) >= 2
    room_txt = f"Räume im Mittel {_fmt(room)} °C" if room is not None else ""
    if multi:
        # Several sensors (e.g. one per floor in a multi-family house): the
        # coldest room decides. Lower only if every room is too warm, warn as
        # soon as one room is too cold.
        coldest = min(rooms, key=lambda r: r["dev_7d"])
        dev = coldest["dev_7d"]
        colds = [r["dev_cold"] for r in rooms if r["dev_cold"] is not None]
        milds = [r["dev_mild"] for r in rooms if r["dev_mild"] is not None]
        dev_cold = min(colds) if len(colds) == len(rooms) else None
        dev_mild = min(milds) if len(milds) == len(rooms) else None
        room_txt = (
            "Räume: "
            + ", ".join(f"{r.get('name', r['entity_id'])} {_fmt(r['avg_7d'])} °C" for r in rooms)
            + f". Maßgeblich ist der kälteste Raum ({coldest.get('name', coldest['entity_id'])})"
        )
    rl0, rl15, rl18 = fig.get("rl_set_0"), fig.get("rl_set_m15"), fig.get("rl_set_18")
    ms0, ms15, ms18 = fig.get("mkr_set_0"), fig.get("mkr_set_m15"), fig.get("mkr_set_18")
    mkr = ctx.circuit == "mkr1"
    menu = MENU_CURVE_M1 if mkr else MENU_CURVE
    curve_txt = ""
    if mkr and ms0 is not None:
        parts = [
            f"{_fmt(v)} °C bei {p:.0f} °C"
            for p, v in ((18, ms18), (0, ms0), (-15, ms15))
            if v is not None
        ]
        curve_txt = " Gemessenes Vorlauf-Soll Mischer 1: " + ", ".join(parts) + "."
    elif not mkr and rl0 is not None:
        parts = [
            f"{_fmt(v)} °C bei {p:.0f} °C"
            for p, v in ((18, rl18), (0, rl0), (-15, rl15))
            if v is not None
        ]
        curve_txt = " Gemessenes Rücklauf-Soll der Regelung: " + ", ".join(parts) + "."
    method = (
        "Laut Bedienungsanleitung in Schritten von 1–2 K, jeweils 1–2 Tage beobachten, "
        "im meistgenutzten Raum. Kamin/Ofen in dieser Zeit nicht nutzen. Jedes Grad weniger "
        "spart ca. 2,5 % Strom (DUH-Ratgeber)."
    )

    if ctx.has_room_sensor and dev is not None and room is not None and room_set is not None:
        if dev > 0.5:
            where = "parallel"
            if dev_cold is not None and dev_mild is not None:
                if dev_cold - dev_mild > 0.7:
                    where = "steep"
                elif dev_mild - dev_cold > 0.7:
                    where = "foot"
            pt = "VL Soll " if mkr else "RL Soll "
            if where == "steep":
                todo = (
                    "Zu warm vor allem bei Kälte: Heizkurve ist zu steil. "
                    f"{menu} → „{pt}-15°C“ um 1–2 K senken."
                )
            elif where == "foot":
                todo = (
                    "Zu warm vor allem bei mildem Wetter: "
                    f"{menu} → „{pt}18°C“ und „{pt}0°C“ um 1–2 K senken."
                )
            else:
                if mkr:
                    todo = (
                        "Gleichmäßig zu warm: Raumsoll Mischer 1 (Grundbedienung M1) um "
                        "0,5–1 K senken. Das verschiebt die ganze Heizkurve von Mischer 1 "
                        "parallel. In Home Assistant ist das die Entität „MKR1 Raumsoll“ "
                        "(standardmäßig deaktiviert, kann aktiviert werden). "
                        f"Alternativ alle Punkte unter {menu} um 1 K senken."
                    )
                else:
                    todo = (
                        "Gleichmäßig zu warm: Raumsoll (HKR) um 0,5–1 K senken. Das verschiebt "
                        "die ganze Heizkurve parallel und geht auch direkt in Home Assistant. "
                        f"Alternativ alle Punkte unter {MENU_CURVE} um 1 K senken."
                    )
            add(
                Hint(
                    "curve_lower",
                    "info",
                    "Heizkurve kann gesenkt werden",
                    f"{room_txt}, eingestellt {_fmt(room_set)} °C (+{_fmt(dev)} K)." + curve_txt,
                    todo
                    + " "
                    + method
                    + (
                        " Im Mehrfamilienhaus: Bewohner vorher informieren und bei vermieteten "
                        "Wohnungen die üblichen Mindesttemperaturen beachten."
                        if multi
                        else ""
                    ),
                    "selbst",
                )
            )
        elif dev < -0.7:
            add(
                Hint(
                    "room_cold",
                    "warning",
                    "Räume erreichen die Solltemperatur nicht",
                    f"{room_txt}, eingestellt {_fmt(room_set)} °C ({_fmt(dev)} K)." + curve_txt,
                    "Heizkurve nicht senken. Zuerst prüfen: Ventile/Thermostate offen, "
                    f"Fenster, Luft im System. Danach {'Raumsoll Mischer 1' if mkr else 'Raumsoll (HKR)'} oder "
                    f"{menu} um 1 K anheben. Hilft das nicht, Fachbetrieb "
                    "(hydraulischer Abgleich).",
                    "selbst oder Fachbetrieb",
                )
            )
    if multi:
        spread_rooms = fig.get("room_spread_7d")
        if spread_rooms is not None and spread_rooms > 1.5:
            warmest = max(rooms, key=lambda r: r["avg_7d"])
            add(
                Hint(
                    "rooms_uneven",
                    "info",
                    "Räume/Etagen unterschiedlich warm",
                    f"Unterschied {_fmt(spread_rooms)} K zwischen "
                    f"{coldest.get('name', coldest['entity_id'])} ({_fmt(coldest['avg_7d'])} °C) und "
                    f"{warmest.get('name', warmest['entity_id'])} ({_fmt(warmest['avg_7d'])} °C).",
                    "Die Heizkurve muss sich nach dem kältesten Raum richten, wärmere Räume "
                    "verschwenden dann Energie. Ursache ist meist die Wasserverteilung: "
                    "hydraulischer Abgleich, Ventile/Stellantriebe, Durchfluss je Etage. "
                    "Selbst: Raumregler der warmen Etagen prüfen. Fachbetrieb: Abgleich.",
                    "selbst oder Fachbetrieb",
                )
            )
    measured = ctx.has_room_sensor and dev is not None
    if not measured and not mkr and rl0 is not None and ctx.heating_system == "underfloor":
        factory = FACTORY_CURVE_UNDERFLOOR[0.0]
        if rl0 > factory + 3:
            add(
                Hint(
                    "curve_above_factory",
                    "info",
                    "Heizkurve höher als die Werkseinstellung",
                    f"Rücklauf-Soll bei 0 °C außen ca. {_fmt(rl0)} °C, Werkseinstellung "
                    f"für Fußbodenheizung {factory:.0f} °C.",
                    "Mit einem Raumtemperatur-Sensor kann der Check prüfen, ob die Kurve "
                    f"gesenkt werden kann. {method}",
                    "selbst",
                )
            )

    # Without a room sensor only: with one, the measured room temperature
    # decides (curve_lower / room_cold). On the BLW NEO the room setpoint HKR
    # is the parallel shift of the heating curve (operating manual), so a
    # high value does not necessarily mean warm rooms.
    if room_set is not None and room_set > 21.5 and not ctx.has_room_sensor:
        add(
            Hint(
                "room_set_high",
                "info",
                "Hohe Raumsolltemperatur",
                f"Raumsoll {'Mischer 1' if mkr else '(HKR)'} {_fmt(room_set)} °C. "
                "Bei der BLW NEO verschiebt dieser Wert "
                f"die ganze Heizkurve{' von Mischer 1' if mkr else ''}. Ob die Räume wirklich so warm sind, ist ohne "
                "Raumsensor nicht bekannt.",
                "Nicht pauschal senken. Erst einen Raumtemperatur-Sensor in den Optionen "
                "wählen, dann zeigt der Check, ob und wo gesenkt werden kann. Faustregel: "
                "Jedes Grad weniger Raumtemperatur spart ca. 6 % Heizenergie.",
                "selbst",
            )
        )

    # Buffer charged higher than the mixing circuit needs
    if mkr and rl0 is not None and ms0 is not None and rl0 - ms0 > 3.0:
        diff = rl0 - ms0
        add(
            Hint(
                "buffer_overheat",
                "info",
                "Puffer wird höher geladen als nötig",
                f"Ladeziel des Puffers (HKR, Rücklauf-Soll) bei 0 °C außen ca. {_fmt(rl0)} °C, "
                f"Vorlauf-Soll Mischer 1 nur ca. {_fmt(ms0)} °C ({_fmt(diff)} K Unterschied).",
                "Die Wärmepumpe erzeugt mehr Wärme, als der Mischerkreis abnimmt. Die "
                f"Heizkurve des HKR senken ({MENU_CURVE}, oder Raumsoll HKR als Parallelverschiebung), "
                "in kleinen Schritten, bis der Puffer nur noch ca. 2–3 K über dem Bedarf von "
                "Mischer 1 liegt. Jedes Grad weniger spart ca. 2,5 % Strom (DUH-Ratgeber). "
                "Danach prüfen, dass die Räume warm bleiben.",
                "selbst oder Fachbetrieb",
            )
        )

    # Heating limit
    warm_h = fig.get("heating_hours_warm_7d") or 0
    if warm_h > 6:
        add(
            Hint(
                "heating_limit",
                "info",
                "Heizbetrieb bei milden Außentemperaturen",
                f"In den letzten 7 Tagen {_fmt(warm_h)} h Heizbetrieb bei 16 °C und mehr außen.",
                "Heizgrenze bzw. Sommerumschaltung prüfen. In gut gedämmten Häusern sind "
                "ca. 15 °C oft möglich (DUH-Ratgeber).",
                "selbst oder Fachbetrieb",
            )
        )

    # Cycling
    starts = fig.get("starts_24h") or 0
    run_med = fig.get("run_median_min_24h")
    short_runs = run_med is not None and starts >= 5 and run_med < 20
    many_starts = starts > 24 and (run_med is None or run_med < 30)
    if short_runs or many_starts:
        detail = f"{starts:.0f} Verdichterstarts in 24 h"
        if run_med is not None:
            detail += f", mittlere Laufzeit {run_med:.0f} min pro Start"
        add(
            Hint(
                "cycling",
                "warning" if short_runs else "info",
                "Wärmepumpe taktet häufig",
                detail + ". Richtwert (Faustregel): Laufzeit pro Start mindestens 20–30 min, "
                "nicht mehr als ca. 1 Start pro Stunde.",
                "Selbst: Thermostate/Einzelraumregler bei Fußbodenheizung möglichst offen "
                "lassen, Heizkurve nicht höher als nötig. Fachbetrieb: Schaltdifferenz "
                "(Hysterese), Mindestlaufzeit und Durchfluss prüfen.",
                "selbst oder Fachbetrieb",
            )
        )

    # Spread
    spread = fig.get("heating_spread_7d")
    if spread is not None and spread > lim_spread:
        add(
            Hint(
                "spread_high",
                "info",
                "Große Spreizung Vorlauf/Rücklauf",
                f"Im Heizbetrieb im Mittel {_fmt(spread)} K. Richtwert {system_name}: "
                f"höchstens ca. {lim_spread:.0f} K.",
                "Der Durchfluss ist vermutlich zu gering: Pumpeneinstellung, hydraulischer "
                "Abgleich, Schmutzfänger/Filter prüfen lassen.",
                "Fachbetrieb",
            )
        )
    elif spread is not None and spread < 2:
        add(
            Hint(
                "spread_low",
                "info",
                "Sehr kleine Spreizung Vorlauf/Rücklauf",
                f"Im Heizbetrieb im Mittel {_fmt(spread)} K.",
                "Die Umwälzpumpe läuft eventuell stärker als nötig und verbraucht unnötig "
                "Strom. Pumpeneinstellung prüfen lassen.",
                "Fachbetrieb",
            )
        )

    # Hot water
    if ctx.dhw_setpoint is not None and ctx.dhw_setpoint > 52:
        add(
            Hint(
                "dhw_high",
                "info",
                "Hohe Warmwassertemperatur",
                f"Warmwasser-Solltemperatur {_fmt(ctx.dhw_setpoint)} °C.",
                "Höhere Warmwassertemperaturen senken die Effizienz deutlich. Oft reichen "
                "48–50 °C. Legionellenschutz vorher mit dem Fachbetrieb klären.",
                "selbst oder Fachbetrieb",
            )
        )
    spf_dhw = fig.get("spf_dhw_30d")
    if spf_dhw is not None and spf_dhw < 2.3:
        add(
            Hint(
                "dhw_spf_low",
                "info",
                "Warmwasser wenig effizient",
                f"Arbeitszahl Warmwasser (30 Tage) {_fmt(spf_dhw)}.",
                "Warmwassertemperatur und Zeitprogramm (z.B. tagsüber/bei PV laden) prüfen, "
                "Zirkulationspumpe nur mit Zeitprogramm betreiben.",
                "selbst oder Fachbetrieb",
            )
        )

    # Defrost
    dw = fig.get("defrosts_warm_per_day_7d") or 0
    if dw >= 3:
        add(
            Hint(
                "defrost_warm",
                "info",
                "Viele Abtauungen bei milder Witterung",
                f"Im Mittel {_fmt(dw)} Abtauungen pro Tag bei über +5 °C außen.",
                "Außeneinheit auf Verschmutzung, Laub und freien Luftweg prüfen "
                "(Luft-Kurzschluss). Bei Bedarf Fachbetrieb.",
                "selbst oder Fachbetrieb",
            )
        )

    # Refrigerant circuit
    sh = fig.get("superheat_7d")
    if sh is not None and not 2 <= sh <= 12:
        add(
            Hint(
                "superheat",
                "info",
                "Auffälliger Kältekreis-Wert (Überhitzung)",
                f"Überhitzung im Mittel {_fmt(sh)} K, üblich sind ca. 4–8 K.",
                "Nicht selbst eingreifen. Bei der nächsten Wartung ansprechen.",
                "Fachbetrieb",
            )
        )

    # Seasonal performance
    spf = fig.get("spf_30d")
    spf_heat = fig.get("spf_heating_30d")
    if spf is not None:
        if ctx.expected_spf and spf < ctx.expected_spf - 0.3:
            add(
                Hint(
                    "spf_below_plan",
                    "warning",
                    "Arbeitszahl unter der Planung",
                    f"Arbeitszahl der letzten 30 Tage {_fmt(spf)}, geplant {_fmt(ctx.expected_spf)}.",
                    "Die anderen Hinweise zuerst abarbeiten. Werte mit dem Fachbetrieb "
                    "besprechen, die Planung (z.B. Förderantrag) mitnehmen.",
                    "Fachbetrieb",
                )
            )
        elif spf_heat is not None and spf_heat < 3.0:
            add(
                Hint(
                    "spf_low",
                    "info",
                    "Arbeitszahl Heizen eher niedrig",
                    f"Arbeitszahl Heizen der letzten 30 Tage {_fmt(spf_heat)}. "
                    "Richtwert Luft/Wasser-Wärmepumpe: ab ca. 3,0, mit Fußbodenheizung ab ca. 3,5.",
                    "Größte Hebel: Heizkurve senken, Takten vermeiden, Warmwassertemperatur "
                    "prüfen.",
                    "selbst oder Fachbetrieb",
                )
            )

    if not ctx.has_room_sensor:
        add(
            Hint(
                "no_room_sensor",
                "info",
                "Raumtemperatur-Sensor fehlt",
                "Ohne gemessene Raumtemperatur kann nicht geprüft werden, ob die Heizkurve "
                "gesenkt werden kann.",
                "In den Optionen der Integration einen oder mehrere Raumtemperatur-Sensoren "
                "auswählen (z.B. Wohnzimmer).",
                "selbst",
            )
        )

    hints.sort(key=lambda h: h.severity != "warning")
    return hints


def status(hints: list[Hint], data_days: float) -> str:
    """Overall status."""
    if data_days < MIN_DAYS:
        return "collecting"
    relevant = [h for h in hints if h.id != "no_room_sensor"]
    if any(h.severity == "warning" for h in relevant):
        return "check"
    if relevant:
        return "improvable"
    return "good"


def safe_float(value: Any) -> float | None:
    """Convert a HA state to float, None if not numeric."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f
