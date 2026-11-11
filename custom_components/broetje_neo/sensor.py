"""Sensors for the Brötje NEO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from . import advisor, registers as r
from .coordinator import BroetjeConfigEntry, BroetjeNeoCoordinator
from .entity import BroetjeNeoEntity

PARALLEL_UPDATES = 0

type ValueFn = Callable[[BroetjeNeoCoordinator], StateType]


@dataclass(frozen=True, kw_only=True)
class BroetjeSensorDescription(SensorEntityDescription):
    """Sensor description with a value function."""

    value_fn: ValueFn
    attr_fn: Callable[[BroetjeNeoCoordinator], dict[str, Any]] | None = None


def _reg(reg: r.Register) -> ValueFn:
    return lambda c: c.value(reg)


def _diff(a: r.Register, b: r.Register) -> ValueFn:
    def fn(c: BroetjeNeoCoordinator) -> StateType:
        va, vb = c.value(a), c.value(b)
        if va is None or vb is None:
            return None
        return round(va - vb, 1)

    return fn


def _ratio(num: r.Register, den: r.Register, num_scale: float = 1.0) -> ValueFn:
    def fn(c: BroetjeNeoCoordinator) -> StateType:
        vn, vd = c.value(num), c.value(den)
        if vn is None or not vd:
            return None
        return round(vn * num_scale / vd, 2)

    return fn


def _enum(reg: r.Register, mapping: dict[int, str]) -> ValueFn:
    return lambda c: mapping.get(c.raw(reg)) if c.raw(reg) is not None else None


def _cop_calc(c: BroetjeNeoCoordinator) -> StateType:
    p_el = c.value(r.P_EL)
    p_th = c.value(r.P_TH)
    if p_th is None or not p_el or p_el < 100:
        return None
    return round(p_th * 1000 / p_el, 2)


def _mixer_setpoint(reg_flow: r.Register, reg_mode: r.Register) -> ValueFn:
    """Mixer flow setpoint, unknown while the mixing circuit is not active."""

    def fn(c: BroetjeNeoCoordinator) -> StateType:
        flow, mode = c.value(reg_flow), c.raw(reg_mode)
        if flow is None or flow <= 0 or mode is None or mode == 0:
            return None
        return flow

    return fn


def _temp(
    key: str,
    reg: r.Register,
    enabled: bool = True,
    value_fn: ValueFn | None = None,
) -> BroetjeSensorDescription:
    return BroetjeSensorDescription(
        key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=enabled,
        value_fn=value_fn or _reg(reg),
    )


def _kdiff(key: str, a: r.Register, b: r.Register) -> BroetjeSensorDescription:
    return BroetjeSensorDescription(
        key=key,
        native_unit_of_measurement=UnitOfTemperature.KELVIN,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_diff(a, b),
    )


def _energy(key: str, reg: r.Register) -> BroetjeSensorDescription:
    return BroetjeSensorDescription(
        key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_reg(reg),
    )


def _hours(key: str, reg: r.Register) -> BroetjeSensorDescription:
    return BroetjeSensorDescription(
        key=key,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_reg(reg),
    )


def _ratio_desc(key: str, num: r.Register, den: r.Register) -> BroetjeSensorDescription:
    return BroetjeSensorDescription(
        key=key,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_ratio(num, den),
    )


SENSORS: tuple[BroetjeSensorDescription, ...] = (
    _temp("outdoor_temperature", r.T_OUTDOOR),
    _temp("outdoor_temperature_delayed", r.T_OUTDOOR_DELAYED),
    _temp("dhw_temperature", r.T_DHW),
    _temp("flow_temperature", r.T_FLOW),
    _temp("return_temperature", r.T_RETURN),
    _temp("buffer_temperature", r.T_BUFFER),
    _temp("source_inlet_temperature", r.T_SOURCE_IN),
    _temp("source_outlet_temperature", r.T_SOURCE_OUT),
    _temp("suction_gas_temperature", r.T_SUCTION_GAS),
    _temp("evaporation_temperature", r.T_EVAPORATION),
    _temp("condensation_temperature", r.T_CONDENSATION),
    _temp("hot_gas_temperature", r.T_HOT_GAS),
    _temp("fresh_water_temperature", r.T_FRESH_WATER, enabled=False),
    _temp("return_setpoint_actual", r.T_RETURN_SETPOINT),
    _temp(
        "mkr1_flow_setpoint_actual",
        r.T_MKR1_FLOW_SETPOINT,
        value_fn=_mixer_setpoint(r.T_MKR1_FLOW_SETPOINT, r.MKR1_MODE),
    ),
    _temp(
        "mkr2_flow_setpoint_actual",
        r.T_MKR2_FLOW_SETPOINT,
        enabled=False,
        value_fn=_mixer_setpoint(r.T_MKR2_FLOW_SETPOINT, r.MKR2_MODE),
    ),
    BroetjeSensorDescription(
        key="low_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_reg(r.P_LOW),
    ),
    BroetjeSensorDescription(
        key="high_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_reg(r.P_HIGH),
    ),
    BroetjeSensorDescription(
        key="flow_rate",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_reg(r.FLOW_RATE),
    ),
    BroetjeSensorDescription(
        key="compressor_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_reg(r.COMPRESSOR_SPEED),
    ),
    BroetjeSensorDescription(
        key="expansion_valve",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_reg(r.EXPANSION_VALVE),
    ),
    BroetjeSensorDescription(
        key="cop",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_reg(r.COP),
    ),
    BroetjeSensorDescription(
        key="cop_calculated",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_cop_calc,
    ),
    BroetjeSensorDescription(
        key="electrical_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_reg(r.P_EL),
    ),
    BroetjeSensorDescription(
        key="thermal_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_reg(r.P_TH),
    ),
    _energy("thermal_energy_heating", r.E_TH_HEATING),
    _energy("electrical_energy_heating", r.E_EL_HEATING),
    _energy("thermal_energy_dhw", r.E_TH_DHW),
    _energy("electrical_energy_dhw", r.E_EL_DHW),
    _energy("electrical_energy_total", r.E_EL_TOTAL),
    _energy("thermal_energy_total", r.E_TH_TOTAL),
    _hours("operating_hours_dhw", r.HOURS_DHW),
    _hours("operating_hours_heating", r.HOURS_HEATING),
    BroetjeSensorDescription(
        key="demand",
        device_class=SensorDeviceClass.ENUM,
        options=list(dict.fromkeys(r.DEMANDS.values())),
        value_fn=_enum(r.DEMAND, r.DEMANDS),
        attr_fn=lambda c: {"raw": c.raw(r.DEMAND)},
    ),
    BroetjeSensorDescription(
        key="operating_mode_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(r.OPERATING_MODES.values()),
        value_fn=_enum(r.OPERATING_MODE, r.OPERATING_MODES),
        attr_fn=lambda c: {"raw": c.raw(r.OPERATING_MODE)},
    ),
    BroetjeSensorDescription(
        key="mkr1_operating_mode_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(r.OPERATING_MODES.values()),
        value_fn=_enum(r.MKR1_MODE, r.OPERATING_MODES),
        attr_fn=lambda c: {"raw": c.raw(r.MKR1_MODE)},
    ),
    BroetjeSensorDescription(
        key="mkr2_operating_mode_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(r.OPERATING_MODES.values()),
        entity_registry_enabled_default=False,
        value_fn=_enum(r.MKR2_MODE, r.OPERATING_MODES),
        attr_fn=lambda c: {"raw": c.raw(r.MKR2_MODE)},
    ),
    # derived values
    _kdiff("flow_return_spread", r.T_FLOW, r.T_RETURN),
    _kdiff("superheat", r.T_SUCTION_GAS, r.T_EVAPORATION),
    _kdiff("temperature_lift", r.T_CONDENSATION, r.T_EVAPORATION),
    _kdiff("condenser_approach", r.T_CONDENSATION, r.T_FLOW),
    _kdiff("source_spread", r.T_SOURCE_IN, r.T_SOURCE_OUT),
    _ratio_desc("spf_total", r.E_TH_TOTAL, r.E_EL_TOTAL),
    _ratio_desc("spf_heating", r.E_TH_HEATING, r.E_EL_HEATING),
    _ratio_desc("spf_dhw", r.E_TH_DHW, r.E_EL_DHW),
)


# --- efficiency check ------------------------------------------------------
def _fig(key: str) -> ValueFn:
    return lambda c: c.figures.get(key)


def _hints_attr(c: BroetjeNeoCoordinator) -> dict[str, Any]:
    return {
        "hint_count": len(c.hints),
        "circuit": c.circuit,
        "circuit_setting": c.circuit_setting,
        "data_days": c.data_days,
        "hints": [
            {
                "id": h.id,
                "severity": h.severity,
                "title": h.title,
                "finding": h.finding,
                "suggestion": h.suggestion,
                "who": h.who,
            }
            for h in c.hints
        ],
        "rooms": c.rooms,
        "coldest_room": c.coldest_room,
        "note": "Vorschläge ohne Gewähr. Änderungen am Bedienteil oder mit dem Fachbetrieb.",
    }


def _spf_attr(c: BroetjeNeoCoordinator) -> dict[str, Any]:
    """Where the 30-day SPF comes from (measured power or controller counters)."""
    return {
        "source": c.figures.get("spf_source"),
        "days": c.figures.get("spf_days"),
        "meter_el_ratio": c.figures.get("meter_el_ratio"),
    }


def _check(
    key: str, unit: str | None = None, *, precision: int = 1, **kw
) -> BroetjeSensorDescription:
    return BroetjeSensorDescription(
        key=key,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
        value_fn=_fig(kw.pop("fig", key)),
        **kw,
    )


def _plant_state(c: BroetjeNeoCoordinator) -> StateType:
    def flag(reg: r.Register) -> bool | None:
        raw = c.raw(reg)
        return None if raw is None else raw != 0

    return advisor.plant_state(
        fault=flag(r.FAULT),
        evu_release=flag(r.EVU_RELEASE),
        price_lock=c.price_lock_active,
        mode=r.OPERATING_MODES.get(c.raw(r.OPERATING_MODE)),
        compressor=flag(r.HEAT_PUMP_RUNNING),
        demand=r.DEMANDS.get(c.raw(r.DEMAND)),
        defrost=flag(r.FOUR_WAY_VALVE),
        passive_cooling=flag(r.PASSIVE_COOLING),
    )


def _day(key: str) -> ValueFn:
    return lambda c: c.daily.get(key)


def _ts(key: str) -> ValueFn:
    def fn(c: BroetjeNeoCoordinator) -> Any:
        v = c.daily.get(key)
        return None if v is None else dt_util.utc_from_timestamp(v)

    return fn


def _runtime(key: str, total: bool = False) -> BroetjeSensorDescription:
    return BroetjeSensorDescription(
        key=key,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=(SensorStateClass.TOTAL_INCREASING if total else SensorStateClass.MEASUREMENT),
        suggested_display_precision=1,
        value_fn=_day(_RUNTIME_SRC[key]),
    )


_RUNTIME_SRC = {
    f"{name}_{period}": f"{src}_{period}"
    for name, src in (
        ("heating_demand", "heating_demand_h"),
        ("compressor_runtime", "compressor_h"),
        ("compressor_heating_runtime", "compressor_heating_h"),
    )
    for period in ("today", "yesterday", "7d")
}


def _heat_limit_attr(c: BroetjeNeoCoordinator) -> dict[str, Any]:
    d = dict(c.heat_limit_detail)
    d["setting"] = c.heating_limit_setting
    if d.get("confirmed_at") is not None:
        d["confirmed_at"] = dt_util.utc_from_timestamp(d["confirmed_at"]).isoformat()
    return d


# Operation overview: plant state, run times and day values (from the tracker)
OPERATION_SENSORS: tuple[BroetjeSensorDescription, ...] = (
    BroetjeSensorDescription(
        key="plant_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(advisor.PLANT_STATES),
        icon="mdi:heat-pump-outline",
        value_fn=_plant_state,
    ),
    BroetjeSensorDescription(
        key="heating_demand_last_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:radiator",
        value_fn=_ts("last_heat_start"),
    ),
    BroetjeSensorDescription(
        key="compressor_heating_last_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:heat-pump",
        value_fn=_ts("last_comp_heat_start"),
    ),
    BroetjeSensorDescription(
        key="heating_season_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-start",
        value_fn=_ts("season_start"),
    ),
    *(_runtime(key, total=key.endswith("_today")) for key in _RUNTIME_SRC),
    BroetjeSensorDescription(
        key="electrical_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=_day("e_el_today"),
    ),
    BroetjeSensorDescription(
        key="thermal_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=_day("e_th_today"),
    ),
    BroetjeSensorDescription(
        key="cop_today",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:calendar-today",
        value_fn=_day("cop_today"),
    ),
)


ADVISOR_SENSORS: tuple[BroetjeSensorDescription, ...] = (
    BroetjeSensorDescription(
        key="efficiency_check",
        device_class=SensorDeviceClass.ENUM,
        options=["collecting", "good", "improvable", "check"],
        icon="mdi:stethoscope",
        value_fn=lambda c: c.advice_status,
        attr_fn=_hints_attr,
    ),
    _check("starts_24h", fig="starts_24h", precision=0, icon="mdi:restart"),
    _check(
        "run_time_per_start",
        UnitOfTime.MINUTES,
        fig="run_median_min_24h",
        precision=0,
        device_class=SensorDeviceClass.DURATION,
    ),
    _check("defrosts_24h", precision=0, icon="mdi:snowflake-melt"),
    _check(
        "rl_set_18",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _check(
        "rl_set_0",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _check(
        "rl_set_m15",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _check(
        "mkr_set_18",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _check(
        "mkr_set_0",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _check(
        "mkr_set_m15",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    _check("room_dev_7d", UnitOfTemperature.KELVIN, precision=1),
    _check("room_dev_min_7d", UnitOfTemperature.KELVIN, precision=1),
    _check("room_spread_7d", UnitOfTemperature.KELVIN, precision=1),
    _check("heating_spread_7d", UnitOfTemperature.KELVIN),
    _check(
        "room_avg_7d",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    BroetjeSensorDescription(
        key="grid_lock_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        # daily counter: resets at midnight (and on HA restart)
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:transmission-tower-off",
        value_fn=lambda c: c.grid_lock_today_min,
    ),
    _check(
        "heating_limit_observed",
        UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-lines",
        attr_fn=_heat_limit_attr,
    ),
    BroetjeSensorDescription(
        key="heating_limit_setting",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        value_fn=lambda c: c.heating_limit_setting,
    ),
    _check("spf_30d", precision=2, attr_fn=_spf_attr),
    _check("spf_heating_30d", precision=2, attr_fn=_spf_attr),
    _check("spf_dhw_30d", precision=2, attr_fn=_spf_attr),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BroetjeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        BroetjeNeoSensor(coordinator, d) for d in SENSORS + OPERATION_SENSORS + ADVISOR_SENSORS
    )


class BroetjeNeoSensor(BroetjeNeoEntity, SensorEntity):
    """Brötje NEO sensor."""

    entity_description: BroetjeSensorDescription

    @property
    def native_value(self) -> StateType:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator)
