#!/usr/bin/env python3
"""Offline-Auswertung einer Brötje-NEO-Wärmepumpe aus der Home-Assistant-Datenbank.

Liest home-assistant_v2.db (SQLite) nur lesend:
  * statistics  -> Langzeitstatistik (stündlich), Energiezähler -> Monats-AZ
  * states      -> Rohverlauf (Recorder, Standard 10 Tage) -> Takten, Abtauen,
                   Heizkurve, Spreizung, Überhitzung

Nur Standardbibliothek. Lizenz: MIT.

Beispiele:
  python3 analyze_heatpump.py /config/home-assistant_v2.db
  python3 analyze_heatpump.py home-assistant_v2.db --profile heliotherm \\
      --prefix brotje_blw_neo18b --since 2025-03-01
  python3 analyze_heatpump.py db --map t_flow=sensor.mein_vorlauf

Tipp: Datenbank vorher kopieren (HA schreibt laufend), z.B.
  sqlite3 /config/home-assistant_v2.db ".backup /tmp/ha.db"
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import sqlite3
import statistics as st
import sys

# role -> entity suffix (after "<domain>.<prefix>_")
PROFILES: dict[str, dict[str, str]] = {
    # broetje_neo integration, HA language German
    "broetje_neo": {
        "t_out": "sensor.{p}_aussentemperatur",
        "t_flow": "sensor.{p}_vorlauftemperatur",
        "t_return": "sensor.{p}_rucklauftemperatur",
        "t_suction": "sensor.{p}_sauggastemperatur",
        "t_evap": "sensor.{p}_verdampfungstemperatur",
        "t_cond": "sensor.{p}_kondensationstemperatur",
        "e_th_total": "sensor.{p}_warmemenge_gesamt",
        "e_el_total": "sensor.{p}_strom_gesamt",
        "e_th_heat": "sensor.{p}_warmemenge_heizen",
        "e_el_heat": "sensor.{p}_strom_heizen",
        "e_th_dhw": "sensor.{p}_warmemenge_warmwasser",
        "e_el_dhw": "sensor.{p}_strom_warmwasser",
        "compressor": "binary_sensor.{p}_verdichter",
        "defrost": "binary_sensor.{p}_abtauen",
        "demand": "sensor.{p}_anforderung",
    },
    # mbuchber/ha_heliotherm (legacy, German entity names)
    "heliotherm": {
        "t_out": "sensor.{p}_temp_aussen",
        "t_flow": "sensor.{p}_temp_vorlauf",
        "t_return": "sensor.{p}_temp_rucklauf",
        "t_suction": "sensor.{p}_temp_sauggas",
        "t_evap": "sensor.{p}_temp_verdampfung",
        "t_cond": "sensor.{p}_temp_kondensation",
        "e_th_total": "sensor.{p}_wmz_gesamt",
        "e_el_total": "sensor.{p}_stromzahler_gesamt",
        "e_th_heat": "sensor.{p}_wmz_heizung",
        "e_el_heat": "sensor.{p}_stromzahler_heizung",
        "e_th_dhw": "sensor.{p}_wmz_brauchwasser",
        "e_el_dhw": "sensor.{p}_stromzahler_brauchwasser",
        "compressor": "binary_sensor.{p}_verdichter",
        "defrost": "sensor.{p}_vierwegeventil_luft",
        "demand": "sensor.{p}_anforderung",
    },
}
DEFAULT_PREFIX = {"broetje_neo": "brotje_neo", "heliotherm": "brotje_blw_neo18b"}

ACTIVE = {"on", "Abtaubetrieb"}
HEATING = {"heating", "Heizen"}
DHW = {"hot_water", "Warmwasser"}
INVALID = {"unknown", "unavailable", "", None}

Series = list[tuple[float, str]]  # (timestamp, state)


@dataclass
class Report:
    lines: list[str]

    def h(self, title: str) -> None:
        self.lines += ["", title, "-" * len(title)]

    def p(self, text: str = "") -> None:
        self.lines.append(text)

    def rate(self, label: str, value: float | None, ok: bool | None, hint: str) -> None:
        if value is None:
            self.p(f"  {label:<38} n/a")
            return
        mark = "  " if ok is None else ("OK" if ok else "!!")
        self.p(f"[{mark}] {label:<36} {value:>8.2f}   {hint}")


# --------------------------------------------------------------------- DB
def connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load_states(con: sqlite3.Connection, entity_id: str, since: float, until: float) -> Series:
    rows = con.execute(
        """SELECT s.last_updated_ts, s.state FROM states s
           JOIN states_meta m ON m.metadata_id = s.metadata_id
           WHERE m.entity_id = ? AND s.last_updated_ts BETWEEN ? AND ?
           ORDER BY s.last_updated_ts""",
        (entity_id, since, until),
    ).fetchall()
    return [(float(ts), state) for ts, state in rows]


def load_statistics(
    con: sqlite3.Connection, statistic_id: str, since: float, until: float
) -> list[tuple[float, float | None, float | None]]:
    """Return (start_ts, mean, state) hourly rows."""
    rows = con.execute(
        """SELECT s.start_ts, s.mean, s.state FROM statistics s
           JOIN statistics_meta m ON m.id = s.metadata_id
           WHERE m.statistic_id = ? AND s.start_ts BETWEEN ? AND ?
           ORDER BY s.start_ts""",
        (statistic_id, since, until),
    ).fetchall()
    return [(float(ts), mean, state) for ts, mean, state in rows]


# ---------------------------------------------------------------- helpers
def numeric(series: Series) -> list[tuple[float, float]]:
    out = []
    for ts, s in series:
        if s in INVALID:
            continue
        try:
            out.append((ts, float(s)))
        except ValueError:
            continue
    return out


class StepLookup:
    """Value of a (sample-and-hold) series at an arbitrary time."""

    def __init__(self, series: list[tuple[float, float]] | Series) -> None:
        self.ts = [t for t, _ in series]
        self.vals = [v for _, v in series]

    def at(self, ts: float):
        i = bisect_right(self.ts, ts) - 1
        return self.vals[i] if i >= 0 else None


def intervals_on(series: Series, until: float) -> list[tuple[float, float]]:
    """Return (start, end) intervals where the state is active."""
    out: list[tuple[float, float]] = []
    start = None
    for ts, s in series:
        active = s in ACTIVE
        if s in INVALID:
            continue
        if active and start is None:
            start = ts
        elif not active and start is not None:
            out.append((start, ts))
            start = None
    if start is not None:
        out.append((start, until))
    return out


def linfit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    if len(xs) < 3 or len(set(xs)) < 2:
        return None
    mx, my = st.fmean(xs), st.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    b = sxy / sxx
    return my - b * mx, b


def day(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def month(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m")


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


# --------------------------------------------------------------- analyses
def monthly_counter(rows) -> dict[str, float]:
    """Monthly delta of a total_increasing counter (robust against dips)."""
    best: dict[str, float] = {}
    for ts, _mean, state in rows:
        if state is None or state <= 0:
            continue
        m = month(ts)
        best[m] = max(best.get(m, 0.0), state)
    first_min: dict[str, float] = {}
    for ts, _mean, state in rows:
        if state and state > 0:
            m = month(ts)
            first_min[m] = min(first_min.get(m, state), state)
    out: dict[str, float] = {}
    prev = None
    for m in sorted(best):
        base = prev if prev is not None else first_min[m]
        out[m] = max(0.0, best[m] - base)
        prev = best[m]
    return out


def section_spf(r: Report, con, ent, since, until) -> None:
    r.h("Arbeitszahlen je Monat (Langzeitstatistik der Energiezähler, 1 kWh Auflösung)")
    pairs = [("gesamt", "e_th_total", "e_el_total"), ("Heizen", "e_th_heat", "e_el_heat"),
             ("WW", "e_th_dhw", "e_el_dhw")]
    data = {}
    for label, th, el in pairs:
        data[label] = (
            monthly_counter(load_statistics(con, ent[th], since, until)),
            monthly_counter(load_statistics(con, ent[el], since, until)),
        )
    months = sorted(set().union(*(set(a) | set(b) for a, b in data.values())))
    if not months:
        r.p("  keine Langzeitstatistik gefunden (Entity-IDs / --profile prüfen)")
        return
    r.p(f"  {'Monat':<8} {'Wärme kWh':>10} {'Strom kWh':>10} {'AZ':>6} {'AZ Heiz':>8} {'AZ WW':>6}")
    tot_th = tot_el = 0.0
    for m in months:
        th, el = data["gesamt"][0].get(m, 0), data["gesamt"][1].get(m, 0)
        tot_th += th
        tot_el += el

        def az(label: str, m: str = m) -> str:
            a, b = data[label][0].get(m, 0), data[label][1].get(m, 0)
            return f"{a / b:.2f}" if b >= 5 else "-"

        r.p(f"  {m:<8} {th:>10.0f} {el:>10.0f} {az('gesamt'):>6} {az('Heizen'):>8} {az('WW'):>6}")
    if tot_el:
        r.p("")
        r.rate("AZ Zeitraum", tot_th / tot_el, tot_th / tot_el >= 3.5,
               "Richtwert L/W mit FBH >= 3,5; mit HK >= 3,0")


def section_cycling(r: Report, comp: Series, until: float) -> None:
    r.h("Takten (Rohverlauf)")
    iv = intervals_on(comp, until)
    if not iv:
        r.p("  keine Verdichterdaten im Recorder-Zeitraum")
        return
    per_day: dict[str, list[float]] = defaultdict(list)
    for a, b in iv:
        per_day[day(a)].append((b - a) / 60)
    r.p(f"  {'Tag':<10} {'Starts':>6} {'Laufzeit h':>10} {'Ø min/Start':>12}")
    for d in sorted(per_day):
        runs = per_day[d]
        r.p(f"  {d:<10} {len(runs):>6} {sum(runs) / 60:>10.1f} {st.fmean(runs):>12.0f}")
    runs = [x for v in per_day.values() for x in v]
    days = max(1, len(per_day))
    r.p("")
    r.rate("Starts pro Tag (Ø)", len(runs) / days, len(runs) / days <= 12,
           "Richtwert <= 10-12 bei Inverter-WP")
    r.rate("Laufzeit pro Start (Median, min)", st.median(runs), st.median(runs) >= 20,
           "Richtwert >= 20-30 min; kurz -> Hysterese/Pufferung prüfen")
    short = sum(1 for x in runs if x < 10)
    r.rate("Anteil Läufe < 10 min (%)", 100 * short / len(runs), short / len(runs) < 0.1,
           "Kurztakter: Mindestlaufzeit, Volumenstrom, Heizkurve")


def section_defrost(r: Report, defrost: Series, t_out: StepLookup, until: float) -> None:
    r.h("Abtauen (Rohverlauf)")
    iv = intervals_on(defrost, until)
    if not iv:
        r.p("  keine Abtauvorgänge im Zeitraum (oder keine Daten)")
        return
    by_bin: dict[int, list[float]] = defaultdict(list)
    for a, b in iv:
        t = t_out.at(a)
        if t is not None:
            by_bin[int((t // 2) * 2)].append((b - a) / 60)
    days = {day(a) for a, _ in iv}
    r.p(f"  Abtauungen gesamt: {len(iv)} an {len(days)} Tagen, Ø Dauer {st.fmean([(b - a) / 60 for a, b in iv]):.1f} min")
    r.p(f"  {'Außen °C':>9} {'Anzahl':>7} {'Ø min':>6}")
    for k in sorted(by_bin):
        r.p(f"  {k:>4}..{k + 2:<3} {len(by_bin[k]):>7} {st.fmean(by_bin[k]):>6.1f}")
    r.p("  Hinweis: viele Abtauungen > +5 °C deuten auf Fühler-/Luftführungsproblem.")


def section_curve(r: Report, ent_series, comp: StepLookup, demand: StepLookup | None) -> None:
    r.h("Heizkurve, Spreizung, Kältekreis (nur Verdichter an, Heizbetrieb)")
    t_out = StepLookup(numeric(ent_series["t_out"]))
    t_ret = StepLookup(numeric(ent_series["t_return"]))
    t_suc = StepLookup(numeric(ent_series["t_suction"]))
    t_cond = StepLookup(numeric(ent_series["t_cond"]))
    xs, ys, spreads, superheat, lift = [], [], [], [], []
    for ts, flow in numeric(ent_series["t_flow"]):
        if comp.at(ts) not in ACTIVE:
            continue
        if demand is not None and demand.at(ts) is not None and demand.at(ts) not in HEATING:
            continue
        out, ret = t_out.at(ts), t_ret.at(ts)
        if out is None or ret is None:
            continue
        xs.append(out)
        ys.append(flow)
        spreads.append(flow - ret)
    for ts, evap in numeric(ent_series["t_evap"]):
        if comp.at(ts) not in ACTIVE:
            continue
        suc, cond = t_suc.at(ts), t_cond.at(ts)
        if suc is not None:
            superheat.append(suc - evap)
        if cond is not None:
            lift.append(cond - evap)
    if not xs:
        r.p("  zu wenig Daten (Recorder-Zeitraum, Heizbetrieb)")
        return
    bins: dict[int, list[float]] = defaultdict(list)
    for x, y in zip(xs, ys, strict=True):
        bins[int((x // 2) * 2)].append(y)
    r.p(f"  {'Außen °C':>9} {'Samples':>8} {'VL Median':>10}")
    for k in sorted(bins):
        r.p(f"  {k:>4}..{k + 2:<3} {len(bins[k]):>8} {st.median(bins[k]):>10.1f}")
    fit = linfit([k + 1 for k in bins], [st.median(v) for v in bins.values()])
    if fit:
        a, b = fit
        r.p(f"  Fit: VL = {a:.1f} {b:+.2f} * Außen  (Steilheit {-b:.2f})")
        r.rate("VL bei -10 °C (extrapoliert)", a - 10 * b, a - 10 * b <= 35,
               "FBH <= 35 °C, HK <= 45-50 °C; jedes K weniger ~2,5 % Strom")
        r.rate("VL bei +15 °C (extrapoliert)", a + 15 * b, None, "Fußpunkt; > Raumsoll+5 K -> senken")
    r.rate("Spreizung VL-RL (Median, K)", st.median(spreads), 3 <= st.median(spreads) <= 7,
           "FBH 3-5 K, HK 5-7 K; groß -> Volumenstrom zu klein")
    if superheat:
        r.rate("Überhitzung (Median, K)", st.median(superheat), 3 <= st.median(superheat) <= 10,
               f"p10 {pct(superheat, .1):.1f} / p90 {pct(superheat, .9):.1f}; typ. 4-8 K")
    if lift:
        r.rate("Temperaturhub Kond-Verd (Median, K)", st.median(lift), None,
               "kleiner = effizienter")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", help="Pfad zu home-assistant_v2.db (Kopie empfohlen)")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="broetje_neo")
    ap.add_argument("--prefix", help="Entity-Präfix (Default je Profil)")
    ap.add_argument("--since", help="Startdatum YYYY-MM-DD (z.B. nach Fehlanschluss-Phase)")
    ap.add_argument("--until", help="Enddatum YYYY-MM-DD")
    ap.add_argument("--map", action="append", default=[], metavar="ROLLE=ENTITY",
                    help="einzelne Entität überschreiben, Rollen: " + ", ".join(PROFILES["broetje_neo"]))
    args = ap.parse_args(argv)

    prefix = args.prefix or DEFAULT_PREFIX[args.profile]
    ent = {k: v.format(p=prefix) for k, v in PROFILES[args.profile].items()}
    for item in args.map:
        k, _, v = item.partition("=")
        if k not in ent:
            ap.error(f"unbekannte Rolle {k}")
        ent[k] = v
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC).timestamp() if args.since else 0.0
    until = (
        (datetime.fromisoformat(args.until) + timedelta(days=1)).replace(tzinfo=UTC).timestamp()
        if args.until
        else datetime.now(UTC).timestamp()
    )

    con = connect(args.db)
    r = Report([f"Wärmepumpen-Auswertung  {datetime.now():%Y-%m-%d %H:%M}",
                f"DB: {args.db}  Profil: {args.profile}  Präfix: {prefix}"])
    section_spf(r, con, ent, since, until)

    series = {k: load_states(con, v, since, until) for k, v in ent.items()
              if not k.startswith("e_")}
    if series["t_flow"]:
        first = series["t_flow"][0][0]
        r.p("")
        r.p(f"Rohverlauf verfügbar ab {datetime.fromtimestamp(first):%Y-%m-%d %H:%M} "
            "(Recorder purge_keep_days)")
    section_cycling(r, series["compressor"], until)
    section_defrost(r, series["defrost"], StepLookup(numeric(series["t_out"])), until)
    demand = StepLookup(series["demand"]) if series["demand"] else None
    section_curve(r, series, StepLookup(series["compressor"]), demand)
    print("\n".join(r.lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
