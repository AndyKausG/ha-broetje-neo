"""Efficiency check: tracker figures and rules."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "broetje_neo"


def _load(name: str):
    """Load a pure module straight from its file (no Home Assistant needed)."""
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", _PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


a = _load("advisor")

T0 = 1_760_000_000.0  # fixed start


def _feed_days(
    tr: a.Tracker,
    days: int,
    *,
    flow_fn,
    on_min: int = 45,
    off_min: int = 45,
    room: float | None = 21.0,
    room_fn=None,
    rooms_fn=None,
    rl_fn=lambda t: 27 - 0.2 * t,
    mkr_fn=None,
    dhw_cop: float = 3.0,
) -> float:
    """Feed samples every 60 s; outdoor -6..+14 °C daily cycle."""
    ts = T0
    period = (on_min + off_min) * 60
    e_el = 1000.0
    for i in range(days * 24 * 60):
        ts = T0 + i * 60
        t_out = -6 + 20 * ((i % 1440) / 1440)
        on = (ts - T0) % period < on_min * 60
        flow = flow_fn(t_out)
        e_el += 0.01
        tr.feed(
            a.Sample(
                ts=ts,
                t_out=t_out,
                t_flow=flow,
                t_return=flow - 4,
                compressor=on,
                demand="heating" if on else "none",
                defrost=False,
                superheat=6.0,
                room=room_fn(t_out) if room_fn else room,
                rooms=rooms_fn(t_out) if rooms_fn else None,
                room_set=21.0,
                rl_set=rl_fn(t_out),
                mkr_set=mkr_fn(t_out) if mkr_fn else None,
                e_th_total=e_el * 3.6,
                e_el_total=e_el,
                e_th_heat=e_el * 3.4,
                e_el_heat=e_el * 0.9,
                e_th_dhw=e_el * 0.1 * dhw_cop,
                e_el_dhw=e_el * 0.1,
            )
        )
    return ts


def test_figures_basic() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 5, flow_fn=lambda t: 30 - 0.5 * t)
    fig = tr.figures(now)
    assert fig["starts_24h"] == 16
    assert fig["run_median_min_24h"] == 45
    assert fig["heating_spread_7d"] == 4.0
    assert fig["superheat_7d"] == 6.0
    assert fig["room_avg_7d"] == 21.0
    assert fig["room_dev_7d"] == 0.0
    assert abs(fig["rl_set_0"] - 27) < 0.3
    assert abs(fig["rl_set_18"] - 23.4) < 0.3
    assert abs(fig["rl_set_m15"] - 30) < 0.3
    assert fig["spf_30d"] is None  # less than 7 days of data


def test_spf_counters_fallback_after_7_days() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 8, flow_fn=lambda t: 30 - 0.5 * t)
    fig = tr.figures(now)
    assert fig["spf_30d"] == 3.6  # no power readings -> controller counters
    assert fig["spf_source"] == "counters"


def test_good_installation_no_hints() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 5, flow_fn=lambda t: 28 - 0.4 * t)
    ctx = a.Context(room_setpoint=21.0, dhw_setpoint=48, has_room_sensor=True)
    hints = a.advise(tr.figures(now), ctx, tr.data_days(now))
    assert hints == []
    assert a.status(hints, tr.data_days(now)) == "good"


def _hint(hints, hid):
    return next((h for h in hints if h.id == hid), None)


def test_rooms_evenly_too_warm_parallel_shift() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room=22.2)
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True)
    hints = a.advise(tr.figures(now), ctx, 5)
    h = _hint(hints, "curve_lower")
    assert h is not None and h.who == "selbst"
    assert "Raumsoll (HKR)" in h.suggestion
    assert "1–2 K" in h.suggestion
    assert "Rücklauf-Soll" in h.finding
    assert a.status(hints, 5) == "improvable"


def test_too_warm_when_cold_means_too_steep() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room_fn=lambda t: 22.5 if t < 3 else 21.1
    )
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True)
    h = _hint(a.advise(tr.figures(now), ctx, 5), "curve_lower")
    assert h is not None
    assert "RL Soll -15°C" in h.suggestion


def test_too_warm_when_mild_means_foot_point() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room_fn=lambda t: 23.0 if t > 8 else 21.3
    )
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True)
    h = _hint(a.advise(tr.figures(now), ctx, 5), "curve_lower")
    assert h is not None
    assert "RL Soll 18°C" in h.suggestion


def test_room_cold_blocks_curve_lowering() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room=19.8)
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True)
    hints = a.advise(tr.figures(now), ctx, 5)
    assert _hint(hints, "room_cold") is not None
    assert _hint(hints, "curve_lower") is None
    assert a.status(hints, 5) == "check"


def test_without_room_sensor_compare_factory_curve() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 5, flow_fn=lambda t: 36 - 0.5 * t, rl_fn=lambda t: 32 - 0.3 * t)
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=False)
    hints = a.advise(tr.figures(now), ctx, 5)
    assert _hint(hints, "curve_above_factory") is not None
    assert _hint(hints, "no_room_sensor") is not None


def test_cycling() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 4, flow_fn=lambda t: 28 - 0.4 * t, on_min=8, off_min=12)
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True)
    hints = a.advise(tr.figures(now), ctx, 4)
    assert "cycling" in [h.id for h in hints]


def test_dhw_and_room_setpoint_hints() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 8, flow_fn=lambda t: 28 - 0.4 * t, dhw_cop=1.8)
    ctx = a.Context(room_setpoint=23.0, dhw_setpoint=55, has_room_sensor=False)
    ids = [h.id for h in a.advise(tr.figures(now), ctx, 4)]
    assert {"dhw_high", "dhw_spf_low", "room_set_high", "no_room_sensor"} <= set(ids)


def test_spf_below_plan() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 8, flow_fn=lambda t: 28 - 0.4 * t)
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True, expected_spf=4.2)
    hints = a.advise(tr.figures(now), ctx, 4)
    assert hints[0].id == "spf_below_plan"


def test_persistence_roundtrip() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 3, flow_fn=lambda t: 30 - 0.5 * t)
    tr2 = a.Tracker.from_dict(tr.to_dict())
    assert tr2.figures(now) == tr.figures(now)


def test_pruning_keeps_14_days() -> None:
    tr = a.Tracker()
    tr.feed(a.Sample(ts=T0, t_out=0))
    tr.feed(a.Sample(ts=T0 + 20 * a.DAY, t_out=0))
    assert len(tr.buckets) == 1


def test_status_collecting() -> None:
    assert a.status([], 1.0) == "collecting"


def test_cooling_is_not_counted_as_defrost() -> None:
    tr = a.Tracker()
    for i in range(10):
        tr.feed(a.Sample(ts=T0 + i * 60, t_out=25, defrost=i % 2 == 1, demand="cooling"))
    assert tr.figures(T0 + 600)["defrosts_24h"] == 0


def test_room_set_high_only_without_room_sensor() -> None:
    fig: dict = {}
    with_sensor = a.advise(fig, a.Context(room_setpoint=23.0, has_room_sensor=True), 0)
    without = a.advise(fig, a.Context(room_setpoint=23.0, has_room_sensor=False), 0)
    assert all(h.id != "room_set_high" for h in with_sensor)
    h = next(h for h in without if h.id == "room_set_high")
    assert "Nicht pauschal senken" in h.suggestion


def _floors(eg: float, og: float, dg: float):
    return lambda t: {"sensor.eg": eg, "sensor.og": og, "sensor.dg": dg}


def test_mfh_one_floor_cold_blocks_lowering() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room=22.0, rooms_fn=_floors(22.8, 22.4, 20.0)
    )
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True)
    rooms = tr.room_detail(now)
    assert [r["entity_id"] for r in rooms] == ["sensor.dg", "sensor.og", "sensor.eg"]
    hints = a.advise(tr.figures(now), ctx, 5, rooms)
    ids = [h.id for h in hints]
    assert "curve_lower" not in ids  # mean is too warm, but the attic is cold
    cold = _hint(hints, "room_cold")
    assert cold is not None and "sensor.dg" in cold.finding
    assert "rooms_uneven" in ids
    assert tr.figures(now)["room_spread_7d"] == 2.8


def test_mfh_all_floors_warm_allows_lowering() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room=22.0, rooms_fn=_floors(22.4, 22.0, 21.7)
    )
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True)
    rooms = [{**r, "name": r["entity_id"].split(".")[1].upper()} for r in tr.room_detail(now)]
    h = _hint(a.advise(tr.figures(now), ctx, 5, rooms), "curve_lower")
    assert h is not None
    assert "kälteste Raum (DG)" in h.finding
    assert "+0,7 K" in h.finding  # decided by the coldest floor, not the mean
    assert "Mehrfamilienhaus" in h.suggestion


def test_rooms_persisted() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 3, flow_fn=lambda t: 30, rooms_fn=_floors(21, 21.5, 22))
    tr2 = a.Tracker.from_dict(tr.to_dict())
    assert tr2.room_detail(now) == tr.room_detail(now)


# ------------------------------------------------------ mixing circuit 1
def test_mkr_curve_figures() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 5, flow_fn=lambda t: 30 - 0.5 * t, mkr_fn=lambda t: 32 - 0.5 * t)
    fig = tr.figures(now)
    assert abs(fig["mkr_set_0"] - 32) < 0.3
    assert abs(fig["mkr_set_18"] - 23) < 0.3
    assert abs(fig["mkr_set_m15"] - 39.5) < 0.3
    assert abs(fig["rl_set_0"] - 27) < 0.3  # unchanged
    assert fig["curve_points"] > 0
    # without mkr data nothing is reported
    tr2 = a.Tracker()
    now2 = _feed_days(tr2, 5, flow_fn=lambda t: 30 - 0.5 * t)
    assert tr2.figures(now2)["mkr_set_0"] is None


def test_mkr1_rooms_too_warm_names_mixing_circuit() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room=22.5, mkr_fn=lambda t: 32 - 0.5 * t
    )
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True, circuit="mkr1")
    h = _hint(a.advise(tr.figures(now), ctx, 5), "curve_lower")
    assert h is not None
    assert "Mischer 1" in h.suggestion
    assert "MKR1 Raumsoll" in h.suggestion
    assert "Vorlauf-Soll Mischer 1" in h.finding


def test_mkr1_no_factory_comparison() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr,
        5,
        flow_fn=lambda t: 36 - 0.5 * t,
        rl_fn=lambda t: 32 - 0.3 * t,
        mkr_fn=lambda t: 32 - 0.3 * t,
    )
    fig = tr.figures(now)
    hkr = a.advise(fig, a.Context(room_setpoint=21.0), 5)
    mkr = a.advise(fig, a.Context(room_setpoint=21.0, circuit="mkr1"), 5)
    assert _hint(hkr, "curve_above_factory") is not None
    assert _hint(mkr, "curve_above_factory") is None


def test_mkr1_room_set_high_mentions_mixer() -> None:
    ctx = a.Context(room_setpoint=23.0, circuit="mkr1")
    h = _hint(a.advise({}, ctx, 5), "room_set_high")
    assert h is not None and "Mischer 1" in h.finding


def test_buffer_overheat() -> None:
    def hints(diff: float, circuit: str = "mkr1"):
        tr = a.Tracker()
        now = _feed_days(
            tr,
            5,
            flow_fn=lambda t: 30 - 0.5 * t,
            rl_fn=lambda t: 32 + diff - 0.5 * t,
            mkr_fn=lambda t: 32 - 0.5 * t,
        )
        ctx = a.Context(room_setpoint=21.0, has_room_sensor=True, circuit=circuit)
        return a.advise(tr.figures(now), ctx, 5)

    h = _hint(hints(4.0), "buffer_overheat")
    assert h is not None
    assert h.severity == "info"
    assert "4,0 K" in h.finding
    assert _hint(hints(2.0), "buffer_overheat") is None
    assert _hint(hints(4.0, "hkr"), "buffer_overheat") is None


def test_mkr2_texts() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr, 5, flow_fn=lambda t: 30 - 0.5 * t, room=22.5, mkr_fn=lambda t: 32 - 0.5 * t
    )
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True, circuit="mkr2")
    h = _hint(a.advise(tr.figures(now), ctx, 5), "curve_lower")
    assert h is not None
    assert "Mischer 2" in h.suggestion
    assert "Heizkurve M2" in h.suggestion
    assert "Grundbedienung M2" in h.suggestion
    assert "MKR2 Raumsoll" in h.suggestion
    assert "Mischer 1" not in h.suggestion
    assert "Vorlauf-Soll Mischer 2" in h.finding


def test_buffer_overheat_mkr2() -> None:
    tr = a.Tracker()
    now = _feed_days(
        tr,
        5,
        flow_fn=lambda t: 30 - 0.5 * t,
        rl_fn=lambda t: 36 - 0.5 * t,
        mkr_fn=lambda t: 32 - 0.5 * t,
    )
    ctx = a.Context(room_setpoint=21.0, has_room_sensor=True, circuit="mkr2")
    h = _hint(a.advise(tr.figures(now), ctx, 5), "buffer_overheat")
    assert h is not None
    assert "Mischer 2" in h.finding


def test_old_stored_data_without_mkr_fields() -> None:
    tr = a.Tracker()
    now = _feed_days(tr, 2, flow_fn=lambda t: 30 - 0.5 * t)
    data = tr.to_dict()
    for b in data["buckets"]:
        for k in ("ms_sum", "ms_x_sum", "ms_n"):
            del b[k]
    tr2 = a.Tracker.from_dict(data)
    assert all(b.ms_n == 0 for b in tr2.buckets.values())
    assert tr2.figures(now)["mkr_set_0"] is None


# --- observed heating limit -------------------------------------------------
def _feed_limit(tr, start: float, days: int, t_fn, demand_fn, step: int = 300) -> float:
    """Feed samples every `step` s; t_fn(hour_of_day, ts) -> outdoor (delayed)."""
    ts = start
    for i in range(days * DAY_S // step):
        ts = start + i * step
        t = t_fn((ts % DAY_S) / 3600, ts)
        tr.feed(
            a.Sample(ts=ts, t_out=t, t_out_delayed=t, demand=demand_fn(t, ts), compressor=False)
        )
    return ts + step


DAY_S = 86400


def _autumn(h: float, ts: float) -> float:
    # 8 °C at night, 18 °C in the afternoon (triangle)
    return 8 + 10 * (1 - abs(h - 15) / 15) if h <= 15 else 18 - 10 * (h - 15) / 9


def _winter(h: float, ts: float) -> float:
    return -5 + 10 * (1 - abs(h - 12) / 12)


def _limit14(t: float, ts: float) -> str:
    return "heating" if t < 14 else "none"


def _cycling(t: float, ts: float) -> str:
    return "heating" if (ts // 2700) % 2 == 0 else "none"


def test_heating_limit_learned_and_confirmed() -> None:
    tr = a.Tracker()
    now = _feed_limit(tr, T0, 5, _autumn, _limit14)
    fig = tr.figures(now)
    assert fig["heating_limit_candidate"] is not None
    assert 13.5 <= fig["heating_limit_candidate"] <= 14.0
    # afternoons above 15 °C without demand confirm it
    assert fig["heating_limit_observed"] == fig["heating_limit_candidate"]
    assert fig["heating_limit_starts_60d"] >= 3
    detail = tr.heat_limit_detail(now)
    assert detail["confirmed_at"] is not None
    assert detail["warm_hours_without_demand_14d"] >= 6


def test_heating_limit_kept_through_winter() -> None:
    tr = a.Tracker()
    now = _feed_limit(tr, T0, 5, _autumn, _limit14)
    learned = tr.figures(now)["heating_limit_observed"]
    # 70 cold days: demand cycles at all temperatures, starts only below +5 °C
    now = _feed_limit(tr, now, 70, _winter, _cycling, step=600)
    fig = tr.figures(now)
    assert fig["heating_limit_candidate"] <= 5
    assert fig["heating_limit_observed"] == learned


def test_heating_limit_relearned_after_change() -> None:
    tr = a.Tracker()
    now = _feed_limit(tr, T0, 5, _autumn, _limit14)
    # limit lowered to 12 °C; after the 60-day window the old starts are gone
    now = _feed_limit(tr, now, 65, _autumn, lambda t, ts: "heating" if t < 12 else "none")
    fig = tr.figures(now)
    assert 11.5 <= fig["heating_limit_observed"] <= 12.0


def test_heating_limit_needs_confirmation() -> None:
    tr = a.Tracker()
    now = _feed_limit(tr, T0, 5, _winter, _cycling)
    fig = tr.figures(now)
    assert fig["heating_limit_candidate"] is not None
    assert fig["heating_limit_observed"] is None


def test_heating_limit_persisted() -> None:
    tr = a.Tracker()
    now = _feed_limit(tr, T0, 5, _autumn, _limit14)
    tr2 = a.Tracker.from_dict(tr.to_dict())
    assert tr2.figures(now)["heating_limit_observed"] == tr.figures(now)["heating_limit_observed"]
    assert tr2.heat_starts == tr.heat_starts
    # data stored by older versions has no heating limit fields
    old = tr.to_dict()
    del old["heat_starts"], old["heat_limit"]
    for b in old["buckets"]:
        del b["t_del_sum"], b["t_del_n"], b["demand_heat_n"]
    assert a.Tracker.from_dict(old).figures(now)["heating_limit_observed"] is None


def test_heating_limit_mismatch_hint() -> None:
    fig = {"heating_limit_observed": 17.0}
    ids = lambda ctx: [h.id for h in a.advise(fig, ctx, 10, [])]  # noqa: E731
    assert "heating_limit_mismatch" in ids(a.Context(heating_limit=15.0))
    assert "heating_limit_mismatch" not in ids(a.Context(heating_limit=16.5))
    assert "heating_limit_mismatch" not in ids(a.Context())


# --- operation overview -----------------------------------------------------
def _state(**kw):
    base = dict(
        fault=False,
        evu_release=True,
        price_lock=False,
        mode="auto",
        compressor=False,
        demand="none",
        defrost=False,
        passive_cooling=False,
    )
    return a.plant_state(**(base | kw))


def test_plant_state_priority() -> None:
    assert _state() == "standby"
    assert _state(demand="heating") == "heating_demand"  # buffer still warm enough
    assert _state(demand="heating", compressor=True) == "heating"
    assert _state(demand="hot_water", compressor=True) == "hot_water"
    assert _state(demand="hot_water") == "dhw_demand"
    assert _state(compressor=True) == "compressor_running"
    assert _state(defrost=True, compressor=True, demand="heating") == "defrost"
    # four-way valve during cooling is not a defrost
    assert _state(defrost=True, compressor=True, demand="cooling") == "cooling"
    assert _state(passive_cooling=True) == "cooling"
    assert _state(mode="summer") == "summer"
    assert _state(mode="off") == "off"
    assert _state(evu_release=False, compressor=True) == "utility_lock"
    assert _state(mode="evu_lock") == "utility_lock"
    assert _state(price_lock=True, evu_release=False) == "price_lock"
    assert _state(fault=True, price_lock=True) == "fault"
    assert _state(compressor=None) is None
    assert set(a.PLANT_STATES) >= {_state(), _state(fault=True)}


def test_daily_runtimes_and_energy() -> None:
    tr = a.Tracker()
    day0 = T0 - T0 % DAY_S  # midnight (UTC as "local" day in this test)
    # yesterday: 2 h heating demand, compressor on during the second hour
    for i in range(0, 2 * 3600 + 60, 60):
        ts = day0 - DAY_S + 6 * 3600 + i
        comp = i >= 3600 and i < 2 * 3600
        demand = "heating" if i < 2 * 3600 else "none"
        tr.feed(
            a.Sample(
                ts=ts,
                compressor=comp,
                demand=demand,
                p_el=2000 if comp else 10,
                p_th=8.0 if comp else 0,
            )
        )
    # today: 30 min hot water with compressor
    for i in range(0, 1800 + 60, 60):
        ts = day0 + 3 * 3600 + i
        tr.feed(a.Sample(ts=ts, compressor=i < 1800, demand="hot_water", p_el=1500, p_th=4.5))
    now = day0 + 3 * 3600 + 1860
    d = tr.daily(now, day0, day0 - DAY_S)
    assert d["heating_demand_h_yesterday"] == 2.0
    assert d["compressor_heating_h_yesterday"] == 1.0
    assert d["compressor_h_yesterday"] == pytest_approx(1.0)
    assert d["heating_demand_h_today"] == 0.0
    assert d["compressor_heating_h_today"] == 0.0
    assert d["compressor_h_today"] == pytest_approx(0.5)
    assert d["heating_demand_h_7d"] == 2.0
    assert d["e_el_today"] == pytest_approx(0.75, 0.05)
    assert d["e_th_today"] == pytest_approx(2.25, 0.05)
    assert d["cop_today"] == pytest_approx(3.0, 0.05)
    assert d["last_heat_start"] is None  # no off -> on edge seen yet (first sample)
    assert d["last_comp_heat_start"] == day0 - DAY_S + 6 * 3600 + 3600


def pytest_approx(value: float, rel: float = 0.02):
    import pytest

    return pytest.approx(value, rel=rel, abs=0.02)


def test_heating_season_start() -> None:
    tr = a.Tracker()
    ts = T0
    for demand in ("none", "heating", "none"):
        tr.feed(a.Sample(ts=ts, demand=demand))
        ts += 60
    first = tr.season_start
    assert first == T0 + 60
    assert tr.last_heat_start == first
    # short pause: same season
    ts += 3 * DAY_S
    tr.feed(a.Sample(ts=ts, demand="heating"))
    tr.feed(a.Sample(ts=ts + 60, demand="none"))
    assert tr.season_start == first
    assert tr.last_heat_start == ts
    # summer break > 14 days: new season
    ts += 30 * DAY_S
    tr.feed(a.Sample(ts=ts, demand="heating"))
    assert tr.season_start == ts
    tr2 = a.Tracker.from_dict(tr.to_dict())
    assert tr2.season_start == ts and tr2.last_heat_start == ts


# --- SPF from measured power / meter check ------------------------------------
def _feed_power(tr, days: int, *, counter_el_factor: float = 1.0, step: int = 60) -> float:
    """Heating 12 h/day at 2 kW el / 8 kW th, DHW 2 h/day at 1.5 kW / 4.5 kW, else idle.

    The controller counters grow by counter_el_factor x the real electricity.
    """
    ts = T0
    e_el = e_th = 0.0
    for i in range(days * DAY_S // step):
        ts = T0 + i * step
        h = (ts % DAY_S) / 3600
        if h < 12:
            demand, p_el, p_th = "heating", 2000.0, 8.0
        elif h < 14:
            demand, p_el, p_th = "hot_water", 1500.0, 4.5
        else:
            demand, p_el, p_th = "none", 10.0, 0.0
        e_el += p_el * step / 3600 / 1000 * counter_el_factor
        e_th += p_th * step / 3600
        tr.feed(
            a.Sample(
                ts=ts,
                demand=demand,
                compressor=demand != "none",
                p_el=p_el,
                p_th=p_th,
                e_el_total=round(e_el),
                e_th_total=round(e_th),
                e_el_heat=round(e_el),
                e_th_heat=round(e_th),
            )
        )
    return ts + step


def test_spf_from_measured_power() -> None:
    tr = a.Tracker()
    now = _feed_power(tr, 9, counter_el_factor=0.4)  # counters count far too little
    fig = tr.figures(now)
    assert fig["spf_source"] == "power"
    assert fig["spf_30d"] == pytest_approx(
        (12 * 8 + 2 * 4.5) / (12 * 2 + 2 * 1.5 + 10 * 0.01), 0.03
    )
    assert fig["spf_heating_30d"] == pytest_approx(4.0, 0.03)
    assert fig["spf_dhw_30d"] == pytest_approx(3.0, 0.03)
    assert fig["spf_days"] >= 9
    assert fig["meter_el_ratio"] == pytest_approx(0.4, 0.1)
    hints = [h.id for h in a.advise(fig, a.Context(), 9, [])]
    assert "meter_mismatch" in hints


def test_spf_not_before_7_days_and_meter_ok() -> None:
    tr = a.Tracker()
    now = _feed_power(tr, 5)
    assert tr.figures(now)["spf_30d"] is None
    tr = a.Tracker()
    now = _feed_power(tr, 9)
    fig = tr.figures(now)
    assert fig["meter_el_ratio"] == pytest_approx(1.0, 0.1)
    assert "meter_mismatch" not in [h.id for h in a.advise(fig, a.Context(), 9, [])]


def test_energy_days_persisted() -> None:
    tr = a.Tracker()
    now = _feed_power(tr, 8)
    tr2 = a.Tracker.from_dict(tr.to_dict())
    assert tr2.energy_days == tr.energy_days
    assert tr2.figures(now)["spf_30d"] == tr.figures(now)["spf_30d"]
    old = tr.to_dict()
    del old["energy_days"]
    rebuilt = a.Tracker.from_dict(old)  # 0.6.x data: totals rebuilt from the hourly buckets
    assert rebuilt.figures(now)["spf_30d"] == pytest_approx(tr.figures(now)["spf_30d"], 0.02)
    assert rebuilt.figures(now)["spf_heating_30d"] is None  # no split in old data
