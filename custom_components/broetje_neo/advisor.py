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

SYSTEM_LIMITS = {
    # heating system: (max flow at -10 °C, max flow at 0 °C, max spread K)
    "underfloor": (35.0, 30.0, 6.0),
    "radiator": (50.0, 42.0, 8.0),
    "mixed": (45.0, 38.0, 7.0),
}


@dataclass
class Sample:
    """One poll worth of values (None = not available)."""

    ts: float
    t_out: float | None = None
    t_flow: float | None = None
    t_return: float | None = None
    compressor: bool | None = None
    demand: str | None = None  # "heating", "hot_water", ...
    defrost: bool | None = None
    superheat: float | None = None
    room: float | None = None
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
        if s.defrost is not None:
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
        fig |= self._curve(now)
        fig |= self._spf(now)
        return fig

    def _curve(self, now: float) -> dict[str, float | None]:
        """Fit flow = a + b * outdoor from hourly heating means (14 days)."""
        pts = [
            (b.heat_t_out_sum / b.heat_n, b.heat_flow_sum / b.heat_n)
            for b in self._window(now, KEEP_S)
            if b.heat_n >= 10
        ]
        res: dict[str, float | None] = {
            "curve_points": float(len(pts)),
            "curve_flow_m10": None,
            "curve_flow_0": None,
            "curve_flow_p10": None,
            "curve_slope": None,
        }
        xs = [p[0] for p in pts]
        if len(pts) < 12 or max(xs) - min(xs) < 4:
            return res
        mx, my = st.fmean(xs), st.fmean(p[1] for p in pts)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in pts) / sxx
        a = my - slope * mx
        res |= {
            "curve_flow_m10": round(a - 10 * slope, 1),
            "curve_flow_0": round(a, 1),
            "curve_flow_p10": round(a + 10 * slope, 1),
            "curve_slope": round(-slope, 2),
        }
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


def _fmt(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def advise(fig: dict[str, float | None], ctx: Context, data_days: float) -> list[Hint]:
    """Derive hints from figures. Ordered: warnings first."""
    hints: list[Hint] = []
    add = hints.append
    lim_m10, lim_0, lim_spread = SYSTEM_LIMITS.get(ctx.heating_system, SYSTEM_LIMITS["underfloor"])
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
    room_hot = room is not None and room_set is not None and room > room_set + 0.7
    room_cold = room is not None and room_set is not None and room < room_set - 0.7

    # Heating curve
    f_m10, f_0 = fig.get("curve_flow_m10"), fig.get("curve_flow_0")
    curve_high = (f_m10 is not None and f_m10 > lim_m10) or (f_0 is not None and f_0 > lim_0)
    if curve_high and not room_cold:
        finding = (
            f"Gemessene Heizkurve: Vorlauf ca. {_fmt(f_0)} °C bei 0 °C und "
            f"{_fmt(f_m10)} °C bei −10 °C außen. Richtwert für {system_name}: "
            f"höchstens ca. {lim_0:.0f} °C bzw. {lim_m10:.0f} °C."
        )
        if room_hot:
            finding += f" Die Räume sind im Mittel {_fmt(room)} °C warm, eingestellt sind {_fmt(room_set)} °C."
        add(
            Hint(
                "curve_high",
                "warning" if room_hot or not ctx.has_room_sensor else "info",
                "Heizkurve vermutlich höher als nötig",
                finding,
                "Heizkurve (Parallelverschiebung/Fußpunkt) um 1 K senken, dann 1–2 Tage "
                "beobachten, ob es warm genug bleibt. Schrittweise wiederholen. Jedes Grad "
                "weniger Vorlauf spart ca. 2,5 % Strom (Quelle: DUH-Ratgeber).",
                "selbst oder Fachbetrieb",
            )
        )
    elif room_hot:
        add(
            Hint(
                "room_hot",
                "info",
                "Räume wärmer als eingestellt",
                f"Raumtemperatur im Mittel {_fmt(room)} °C, eingestellt {_fmt(room_set)} °C.",
                "Heizkurve um 1 K senken und 1–2 Tage beobachten. Prüfen, ob Thermostate "
                "oder Einzelraumregler sinnvoll eingestellt sind.",
                "selbst",
            )
        )
    if room_cold:
        add(
            Hint(
                "room_cold",
                "warning",
                "Räume erreichen die Solltemperatur nicht",
                f"Raumtemperatur im Mittel {_fmt(room)} °C, eingestellt {_fmt(room_set)} °C.",
                "Heizkurve vorerst nicht senken. Prüfen: Ventile/Thermostate offen, "
                "hydraulischer Abgleich, Luft im System. Bei Bedarf Fachbetrieb.",
                "selbst oder Fachbetrieb",
            )
        )
    if room_set is not None and room_set > 21.5:
        add(
            Hint(
                "room_set_high",
                "info",
                "Hohe Raumsolltemperatur",
                f"Eingestellte Raumtemperatur {_fmt(room_set)} °C.",
                "Faustregel: Jedes Grad weniger Raumtemperatur spart ca. 6 % Heizenergie. "
                "Wenig genutzte Räume kühler halten.",
                "selbst",
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
