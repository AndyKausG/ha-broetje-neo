"""Efficiency check: tracker figures and rules."""

from __future__ import annotations

from custom_components.broetje_neo import advisor as a

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
    rl_fn=lambda t: 27 - 0.2 * t,
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
                room_set=21.0,
                rl_set=rl_fn(t_out),
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
    assert fig["spf_30d"] == 3.6


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
    now = _feed_days(tr, 4, flow_fn=lambda t: 28 - 0.4 * t)
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
