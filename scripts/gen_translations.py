"""Generate strings.json and translations/{en,de}.json.

Entity names are kept in one table here to keep both languages in sync.
Run: python scripts/gen_translations.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "broetje_neo"

MODES = {
    "off": ("Off", "Aus"),
    "auto": ("Auto", "Automatik"),
    "cooling": ("Cooling", "Kühlen"),
    "summer": ("Summer", "Sommer"),
    "continuous": ("Continuous", "Dauerbetrieb"),
    "setback": ("Setback", "Absenken"),
    "holiday": ("Holiday", "Urlaub"),
    "party": ("Party", "Party"),
    "bake_out": ("Bake-out", "Ausheizen"),
    "evu_lock": ("Utility lock", "EVU-Sperre"),
    "main_switch_off": ("Main switch off", "Hauptschalter aus"),
}
WRITABLE = [k for k in MODES if k not in ("bake_out", "evu_lock", "main_switch_off")]
CHECK = {
    "collecting": ("Collecting data", "Sammle Daten"),
    "good": ("Good", "Gut"),
    "improvable": ("Improvable", "Verbesserbar"),
    "check": ("Please check", "Bitte prüfen"),
}
SYSTEMS = {
    "underfloor": ("Underfloor heating", "Fußbodenheizung"),
    "radiator": ("Radiators", "Heizkörper"),
    "mixed": ("Mixed", "Gemischt"),
}
CIRCUITS = {
    "auto": ("Automatic", "Automatisch"),
    "hkr": ("Direct heating circuit (HKR)", "Heizkreis direkt (HKR)"),
    "mkr1": ("Mixing circuit 1", "Mischerkreis 1"),
    "mkr2": ("Mixing circuit 2", "Mischerkreis 2"),
}
GROUPINGS = {
    "floor": ("By floor", "Nach Stockwerk"),
    "sensor": ("Each sensor", "Jeder Sensor einzeln"),
}
DEMANDS = {
    "none": ("None", "Keine"),
    "cooling": ("Cooling", "Kühlen"),
    "heating": ("Heating", "Heizen"),
    "hot_water": ("Hot water", "Warmwasser"),
    "external": ("External", "Externe Anforderung"),
}

ENTITIES: dict[str, dict[str, tuple[str, str]]] = {
    "sensor": {
        "outdoor_temperature": ("Outdoor temperature", "Außentemperatur"),
        "outdoor_temperature_delayed": ("Outdoor temperature delayed", "Außentemperatur verzögert"),
        "dhw_temperature": ("DHW temperature", "Warmwassertemperatur"),
        "flow_temperature": ("Flow temperature", "Vorlauftemperatur"),
        "return_temperature": ("Return temperature", "Rücklauftemperatur"),
        "buffer_temperature": ("Buffer temperature", "Puffertemperatur"),
        "source_inlet_temperature": ("Source inlet temperature", "Quelle Eintritt"),
        "source_outlet_temperature": ("Source outlet temperature", "Quelle Austritt"),
        "suction_gas_temperature": ("Suction gas temperature", "Sauggastemperatur"),
        "evaporation_temperature": ("Evaporation temperature", "Verdampfungstemperatur"),
        "condensation_temperature": ("Condensation temperature", "Kondensationstemperatur"),
        "hot_gas_temperature": ("Hot gas temperature", "Heißgastemperatur"),
        "fresh_water_temperature": ("Fresh water temperature", "Frischwassertemperatur"),
        "return_setpoint_actual": ("Return setpoint", "Rücklaufsolltemperatur"),
        "mkr1_flow_setpoint_actual": ("MKR1 flow setpoint", "MKR1 Vorlaufsoll"),
        "mkr2_flow_setpoint_actual": ("MKR2 flow setpoint", "MKR2 Vorlaufsoll"),
        "low_pressure": ("Low pressure", "Niederdruck"),
        "high_pressure": ("High pressure", "Hochdruck"),
        "flow_rate": ("Flow rate", "Durchfluss"),
        "compressor_speed": ("Compressor speed", "Verdichterdrehzahl"),
        "expansion_valve": ("Expansion valve", "Expansionsventil"),
        "cop": ("COP", "COP"),
        "cop_calculated": ("COP calculated", "COP berechnet"),
        "electrical_power": ("Electrical power", "Elektrische Leistung"),
        "thermal_power": ("Thermal power", "Heizleistung"),
        "thermal_energy_heating": ("Thermal energy heating", "Wärmemenge Heizen"),
        "electrical_energy_heating": ("Electrical energy heating", "Strom Heizen"),
        "thermal_energy_dhw": ("Thermal energy DHW", "Wärmemenge Warmwasser"),
        "electrical_energy_dhw": ("Electrical energy DHW", "Strom Warmwasser"),
        "electrical_energy_total": ("Electrical energy total", "Strom gesamt"),
        "thermal_energy_total": ("Thermal energy total", "Wärmemenge gesamt"),
        "operating_hours_dhw": ("Operating hours DHW", "Betriebsstunden Warmwasser"),
        "operating_hours_heating": ("Operating hours heating", "Betriebsstunden Heizen"),
        "demand": ("Demand", "Anforderung"),
        "operating_mode_status": ("Operating mode status", "Betriebsart Status"),
        "flow_return_spread": ("Flow/return spread", "Spreizung VL/RL"),
        "superheat": ("Superheat", "Überhitzung"),
        "temperature_lift": ("Temperature lift", "Temperaturhub"),
        "condenser_approach": ("Condenser approach", "Kondensator-Grädigkeit"),
        "source_spread": ("Source spread", "Spreizung Quelle"),
        "spf_total": ("SPF total", "Arbeitszahl gesamt"),
        "spf_heating": ("SPF heating", "Arbeitszahl Heizen"),
        "spf_dhw": ("SPF DHW", "Arbeitszahl Warmwasser"),
        "efficiency_check": ("Efficiency check", "Effizienz-Check"),
        "grid_lock_today": ("Grid operator control today", "Netzbetreiber-Steuerung heute"),
        "starts_24h": ("Compressor starts 24 h", "Verdichterstarts 24 h"),
        "run_time_per_start": ("Run time per start", "Laufzeit pro Start"),
        "defrosts_24h": ("Defrosts 24 h", "Abtauungen 24 h"),
        "rl_set_18": (
            "Heating curve return setpoint at 18 degrees",
            "Heizkurve RL-Soll bei 18 Grad",
        ),
        "rl_set_0": ("Heating curve return setpoint at 0 degrees", "Heizkurve RL-Soll bei 0 Grad"),
        "rl_set_m15": (
            "Heating curve return setpoint at minus 15 degrees",
            "Heizkurve RL-Soll bei minus 15 Grad",
        ),
        "mkr_set_18": (
            "Mixer 1 curve flow setpoint at 18 degrees",
            "Mischer 1 Heizkurve VL-Soll bei 18 Grad",
        ),
        "mkr_set_0": (
            "Mixer 1 curve flow setpoint at 0 degrees",
            "Mischer 1 Heizkurve VL-Soll bei 0 Grad",
        ),
        "mkr_set_m15": (
            "Mixer 1 curve flow setpoint at minus 15 degrees",
            "Mischer 1 Heizkurve VL-Soll bei minus 15 Grad",
        ),
        "room_dev_7d": ("Room vs. setpoint 7 days", "Raum Abweichung vom Soll 7 Tage"),
        "room_dev_min_7d": ("Coldest room vs. setpoint 7 days", "Kältester Raum Abweichung 7 Tage"),
        "room_spread_7d": ("Room temperature spread 7 days", "Raum Unterschied 7 Tage"),
        "heating_spread_7d": ("Heating spread 7 days", "Spreizung Heizen 7 Tage"),
        "room_avg_7d": ("Room temperature 7 days", "Raumtemperatur 7 Tage"),
        "spf_30d": ("SPF 30 days", "Arbeitszahl 30 Tage"),
        "spf_heating_30d": ("SPF heating 30 days", "Arbeitszahl Heizen 30 Tage"),
        "spf_dhw_30d": ("SPF DHW 30 days", "Arbeitszahl Warmwasser 30 Tage"),
    },
    "binary_sensor": {
        "heating_pump": ("Heating circuit pump", "Heizkreispumpe"),
        "buffer_pump": ("Buffer charging pump", "Pufferladepumpe"),
        "compressor": ("Compressor", "Verdichter"),
        "source_fan": ("Source fan", "Ventilator"),
        "fault": ("Fault", "Störung"),
        "defrost": ("Defrost", "Abtauen"),
        "evu_release": ("Utility release", "EVU-Freigabe"),
        "dhw_priority": ("DHW priority", "Warmwasservorrang"),
        "passive_cooling": ("Passive cooling", "Kühlen passiv"),
        "demand_heating": ("Heating", "Heizen"),
        "demand_dhw": ("Hot water", "Warmwasser"),
        "demand_cooling": ("Cooling", "Kühlen"),
        "grid_control": ("Grid operator control", "Netzbetreiber steuert"),
    },
    "select": {
        "operating_mode": ("Operating mode", "Betriebsart"),
        "mkr1_operating_mode": ("MKR1 operating mode", "MKR1 Betriebsart"),
        "mkr2_operating_mode": ("MKR2 operating mode", "MKR2 Betriebsart"),
    },
    "number": {
        "room_setpoint": (
            "Room setpoint (heating curve shift)",
            "Raumsoll (Heizkurve verschieben)",
        ),
        "dhw_normal_setpoint": ("DHW normal temperature", "WW Normaltemperatur"),
        "dhw_min_setpoint": (
            "DHW minimum (frost protection)",
            "WW Minimaltemperatur (Frostschutz)",
        ),
        "cooling_return_min": ("Cooling return min", "Kühlen RLT min"),
        "mkr1_room_setpoint": ("MKR1 room setpoint", "MKR1 Raumsoll"),
        "mkr1_cooling_return_min": ("MKR1 cooling return min", "MKR1 Kühlen RLT min"),
        "mkr2_room_setpoint": ("MKR2 room setpoint", "MKR2 Raumsoll"),
        "mkr2_cooling_return_min": ("MKR2 cooling return min", "MKR2 Kühlen RLT min"),
        "pv_power": ("PV power", "PV-Leistung"),
    },
    "switch": {
        "price_lock": ("Price lock", "Preissperre"),
    },
}

TEXT = {
    "en": {
        "user_title": "Brötje NEO-RKM",
        "user_desc": "Modbus TCP must be enabled in the NEO-RKM web interface (Service → Grundbedienung → Modbus).\n\nUse at your own risk, without any warranty or liability (see README). After setup the integration is read-only.",
        "name": "Name",
        "host": "Host",
        "port": "Port",
        "unit_id": "Unit ID",
        "model": "Model",
        "cannot_connect": "Failed to connect or read register 10.",
        "already_configured": "Device is already configured",
        "opt_title": "Options",
        "heating_system": "Heating system",
        "heating_circuit": "Heating circuit for the efficiency check",
        "heating_circuit_desc": "Auto detects a mixing circuit. Choose manually if the detection is wrong.",
        "room_grouping": "Group room sensors",
        "room_grouping_desc": "By floor uses the floors of the areas in Home Assistant (average per floor).",
        "room_sensors": "Room temperature sensors (for the efficiency check)",
        "expected_spf": "Planned seasonal performance factor (0 = unknown)",
        "allow_write": "Allow writing settings",
        "allow_write_desc": "Operating mode (not 'off') and setpoints within safe limits. Off = read-only.",
        "allow_pv": "Allow PV / power control",
        "allow_pv_desc": "PV power target (reg. 125) incl. watchdog. The NEO-RKM decides itself when and how strongly the heat pump runs.",
        "allow_price_lock": "Allow price lock",
        "allow_price_lock_desc": "Pause the heat pump during expensive hours like a utility lock. Max. 2 h per lock and 6 h per day, min. 60 min pause, not below -10 °C outdoor.",
        "price_lock_max_minutes": "Price lock max. duration (min)",
        "price_lock_switch": "Price lock via external switch (optional, e.g. Shelly)",
        "grid_signal": "Grid operator signal (optional, e.g. control box / SG-Ready via binary sensor)",
        "grid_signal_desc": "On = the grid operator controls the heat pump (§14a EnWG). The utility lock input is detected automatically.",
        "price_lock_switch_desc": "Empty = Modbus registers 149/150. Switch on = lock. Wiring only by a qualified electrician, see README.",
        "scan_interval": "Polling interval (s)",
        "pv_watchdog": "PV watchdog (s, 0 = off)",
        "pv_watchdog_desc": "Register 125 (PV power) is reset to 0 if not refreshed within this time, on HA start and on stop.",
        "pv_max_power": "Maximum PV power target (W)",
    },
    "de": {
        "user_title": "Brötje NEO-RKM",
        "user_desc": "Modbus TCP muss im Webinterface des NEO-RKM aktiviert sein (Service → Grundbedienung → Modbus).\n\nNutzung auf eigene Gefahr, ohne Gewährleistung und Haftung (siehe README). Nach der Einrichtung ist die Integration nur lesend.",
        "name": "Name",
        "host": "Host",
        "port": "Port",
        "unit_id": "Unit-ID",
        "model": "Modell",
        "cannot_connect": "Verbindung fehlgeschlagen oder Register 10 nicht lesbar.",
        "already_configured": "Gerät ist bereits eingerichtet",
        "opt_title": "Optionen",
        "heating_system": "Heizsystem",
        "heating_circuit": "Heizkreis für den Effizienz-Check",
        "heating_circuit_desc": "Automatisch erkennt einen Mischerkreis. Manuell wählen, wenn die Erkennung nicht passt.",
        "room_grouping": "Raumsensoren zusammenfassen",
        "room_grouping_desc": "Nach Stockwerk nutzt die Stockwerke der Bereiche in Home Assistant (Mittelwert pro Stockwerk).",
        "room_sensors": "Raumtemperatur-Sensoren (für den Effizienz-Check)",
        "expected_spf": "Geplante Jahresarbeitszahl (0 = unbekannt)",
        "allow_write": "Einstellungen schreiben erlauben",
        "allow_write_desc": "Betriebsart (nicht 'Aus') und Sollwerte in sicheren Grenzen. Aus = nur lesen.",
        "allow_pv": "PV-/Leistungssteuerung erlauben",
        "allow_pv_desc": "PV-Leistungsvorgabe (Reg. 125) inkl. Watchdog. Wann und wie stark die WP läuft, entscheidet das NEO-RKM selbst.",
        "allow_price_lock": "Preissperre erlauben",
        "allow_price_lock_desc": "Wärmepumpe bei hohen Strompreisen wie bei einer EVU-Sperre pausieren. Max. 2 h am Stück und 6 h pro Tag, mind. 60 min Pause, nicht unter -10 °C außen.",
        "price_lock_max_minutes": "Preissperre max. Dauer (min)",
        "price_lock_switch": "Preissperre über externen Schalter (optional, z.B. Shelly)",
        "grid_signal": "Signal des Netzbetreibers (optional, z.B. Steuerbox / SG-Ready als Binärsensor)",
        "grid_signal_desc": "An = Netzbetreiber steuert die Wärmepumpe (§14a EnWG). Der EVU-Eingang wird automatisch erkannt.",
        "price_lock_switch_desc": "Leer = Modbus-Register 149/150. Schalter an = Sperre. Anschluss nur durch eine Elektrofachkraft, siehe README.",
        "scan_interval": "Abfrageintervall (s)",
        "pv_watchdog": "PV-Watchdog (s, 0 = aus)",
        "pv_watchdog_desc": "Register 125 (PV-Leistung) wird auf 0 gesetzt, wenn es nicht innerhalb dieser Zeit erneuert wird, sowie beim Start und Stopp von HA.",
        "pv_max_power": "Maximale PV-Leistungsvorgabe (W)",
    },
}


def build(lang: str) -> dict:
    idx = 0 if lang == "en" else 1
    t = TEXT[lang]
    entity: dict[str, dict] = {}
    for platform, items in ENTITIES.items():
        entity[platform] = {}
        for key, names in items.items():
            entry: dict = {"name": names[idx]}
            if platform == "select":
                entry["state"] = {k: MODES[k][idx] for k in WRITABLE}
            if key == "operating_mode_status":
                entry["state"] = {k: v[idx] for k, v in MODES.items()}
            if key == "demand":
                entry["state"] = {k: v[idx] for k, v in DEMANDS.items()}
            if key == "efficiency_check":
                entry["state"] = {k: v[idx] for k, v in CHECK.items()}
            entity[platform][key] = entry
    return {
        "config": {
            "step": {
                "user": {
                    "title": t["user_title"],
                    "description": t["user_desc"],
                    "data": {k: t[k] for k in ("name", "host", "port", "unit_id", "model")},
                }
            },
            "error": {"cannot_connect": t["cannot_connect"]},
            "abort": {"already_configured": t["already_configured"]},
        },
        "options": {
            "step": {
                "init": {
                    "title": t["opt_title"],
                    "description": t["pv_watchdog_desc"],
                    "data": {
                        k: t[k]
                        for k in (
                            "heating_system",
                            "heating_circuit",
                            "room_sensors",
                            "room_grouping",
                            "expected_spf",
                            "grid_signal",
                            "allow_write",
                            "allow_pv",
                            "allow_price_lock",
                            "price_lock_max_minutes",
                            "price_lock_switch",
                            "scan_interval",
                            "pv_watchdog",
                            "pv_max_power",
                        )
                    },
                    "data_description": {
                        "heating_circuit": t["heating_circuit_desc"],
                        "room_grouping": t["room_grouping_desc"],
                        "allow_write": t["allow_write_desc"],
                        "allow_pv": t["allow_pv_desc"],
                        "allow_price_lock": t["allow_price_lock_desc"],
                        "price_lock_switch": t["price_lock_switch_desc"],
                        "grid_signal": t["grid_signal_desc"],
                    },
                }
            }
        },
        "entity": entity,
        "selector": {
            "heating_system": {"options": {k: v[idx] for k, v in SYSTEMS.items()}},
            "heating_circuit_option": {"options": {k: v[idx] for k, v in CIRCUITS.items()}},
            "room_grouping": {"options": {k: v[idx] for k, v in GROUPINGS.items()}},
        },
    }


def main() -> None:
    (ROOT / "translations").mkdir(exist_ok=True)
    for lang in ("en", "de"):
        data = json.dumps(build(lang), ensure_ascii=False, indent=2) + "\n"
        (ROOT / "translations" / f"{lang}.json").write_text(data, encoding="utf-8")
        if lang == "en":
            (ROOT / "strings.json").write_text(data, encoding="utf-8")


if __name__ == "__main__":
    main()
