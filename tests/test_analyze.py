"""Test the offline analysis script with a synthetic HA database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sqlite3
import sys

SCRIPT = Path(__file__).parent.parent / "extras" / "tools" / "analyze_heatpump.py"
_spec = importlib.util.spec_from_file_location("analyze_heatpump", SCRIPT)
analyze = importlib.util.module_from_spec(_spec)
sys.modules["analyze_heatpump"] = analyze
_spec.loader.exec_module(analyze)

P = "brotje_blw_neo18b"


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE states_meta (metadata_id INTEGER PRIMARY KEY, entity_id TEXT);
        CREATE TABLE states (state_id INTEGER PRIMARY KEY, state TEXT,
                             last_updated_ts REAL, metadata_id INTEGER);
        CREATE TABLE statistics_meta (id INTEGER PRIMARY KEY, statistic_id TEXT);
        CREATE TABLE statistics (id INTEGER PRIMARY KEY, metadata_id INTEGER,
                                 start_ts REAL, mean REAL, state REAL);
        """
    )
    meta: dict[str, int] = {}

    def mid(table: str, eid: str) -> int:
        key = f"{table}:{eid}"
        if key not in meta:
            col = "entity_id" if table == "states_meta" else "statistic_id"
            cur = con.execute(f"INSERT INTO {table} ({col}) VALUES (?)", (eid,))
            meta[key] = cur.lastrowid
        return meta[key]

    def state(eid: str, ts: float, val) -> None:
        con.execute(
            "INSERT INTO states (state, last_updated_ts, metadata_id) VALUES (?,?,?)",
            (str(val), ts, mid("states_meta", eid)),
        )

    start = datetime(2026, 8, 1, tzinfo=UTC)
    # counters: 3 months, thermal 4x electrical
    for h in range(24 * 92):
        ts = (start + timedelta(hours=h)).timestamp()
        el = 1000 + h * 0.5
        for name, val in (
            ("stromzahler_gesamt", el),
            ("wmz_gesamt", 4 * el),
            ("stromzahler_heizung", 0.8 * el),
            ("wmz_heizung", 3.4 * el),
            ("stromzahler_brauchwasser", 0.2 * el),
            ("wmz_brauchwasser", 0.6 * el),
        ):
            con.execute(
                "INSERT INTO statistics (metadata_id, start_ts, mean, state) VALUES (?,?,?,?)",
                (mid("statistics_meta", f"sensor.{P}_{name}"), ts, None, round(val)),
            )

    # raw states: 2 days, compressor 45 min on / 45 min off
    t0 = datetime(2026, 10, 30, tzinfo=UTC).timestamp()
    for i in range(0, 2 * 24 * 60, 15):  # every 15 min
        ts = t0 + i * 60
        on = (i // 45) % 2 == 0
        out = -4 + (i % 1440) / 1440 * 10  # -4..+6 °C
        state(f"binary_sensor.{P}_verdichter", ts, "on" if on else "off")
        state(f"sensor.{P}_anforderung", ts, "Heizen" if on else "Keine")
        state(f"sensor.{P}_temp_aussen", ts, round(out, 1))
        state(f"sensor.{P}_temp_vorlauf", ts, round(32 - 0.5 * out, 1))
        state(f"sensor.{P}_temp_rucklauf", ts, round(28 - 0.5 * out, 1))
        state(f"sensor.{P}_temp_verdampfung", ts, round(out - 8, 1))
        state(f"sensor.{P}_temp_sauggas", ts, round(out - 2, 1))
        state(f"sensor.{P}_temp_kondensation", ts, round(35 - 0.5 * out, 1))
        defrost = "Abtaubetrieb" if i % 240 == 0 else "Aus"
        state(f"sensor.{P}_vierwegeventil_luft", ts, defrost)
    con.commit()
    con.close()


def test_report(tmp_path: Path, capsys) -> None:
    db = tmp_path / "ha.db"
    _make_db(db)
    assert analyze.main([str(db), "--profile", "heliotherm", "--until", "2026-11-01"]) == 0
    out = capsys.readouterr().out
    assert "2026-09" in out
    # monthly SPF thermal/electric = 4.0
    assert " 4.00 " in out
    assert "Starts pro Tag" in out
    assert "Spreizung VL-RL (Median, K)" in out and "4.00" in out
    assert "Überhitzung (Median, K)" in out and "6.00" in out
    assert "Fit: VL = 32.0 -0.50" in out
    assert "Abtauungen gesamt" in out


def test_monthly_counter_dip() -> None:
    rows = [(datetime(2026, 1, 1, h, tzinfo=UTC).timestamp(), None, v)
            for h, v in enumerate([100, 101, 0, 102])]
    assert analyze.monthly_counter(rows) == {"2026-01": 2}
