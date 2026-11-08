# Changelog

## [0.4.0] - 2026-11-08

- New wall tablet dashboard `extras/dashboard/broetje-neo-dashboard.yaml` (sections view) for plants with a buffer and mixing circuit 1: status, separate view of heating demand, heating circuit pump, buffer charging and compressor, efficiency tiles, run times, 30-day transition-period chart (daily run times vs. mean outdoor temperature and heating limit), 24 h chart and an animated plant schema that only moves while pumps, fan or compressor run. Needs `apexcharts-card` and `button-card` from HACS.
- New package `extras/packages/broetje_neo_dashboard.yaml`: prioritised status sensor, "compressor heating" binary sensor, last heating start, start of heating season, run times today / yesterday / 7 days, heating limit input.
- Plant schema shows the refrigerant circuit (low/high pressure, evaporation/condensation temperature, expansion valve, "pressure equalisation" at standstill), the buffer/DHW diverter valve, a mini heating curve of mixing circuit 1 (measured curve points plus current operating point) and plain-language sentences explaining the current state.
- New documentation `docs/DASHBOARD.md`.
- New read-only sensors "MKR1 operating mode status" and "MKR2 operating mode status" (registers 107 / 112, all mode values). They exist without write access; MKR2 is disabled by default.
- Operating hours DHW / heating treat a raw 0 as invalid (like the energy counters), so a transient read glitch no longer looks like a counter reset in the long-term statistics. A brand-new plant shows "unknown" until the first full hour.
- "Grid operator control today" now has `state_class: total_increasing` and is kept in the long-term statistics.

## [0.3.1] - 2026-11-08

- The "MKR1 flow setpoint" sensor is now enabled by default. It is unknown while mixing circuit 1 is not active (mode register 107 off or flow setpoint register 35 at 0); "MKR2 flow setpoint" follows the same rule but stays disabled by default.
- Second dashboard card template `heat-pump-card-mischer.yaml` for plants with a buffer and a mixing circuit (shows the mixer flow setpoint, no heating return).
- README: new section on choosing the right dashboard card, what the interface provides and sensors a plant does not have.

## [0.3.0] - 2026-11-08

- **New option "Heating circuit for the efficiency check"** (`heating_circuit`: automatic, HKR, mixing circuit 1, mixing circuit 2). Automatic detects mixing circuit 1, then mixing circuit 2 (flow setpoint register 35 / 36 above 0 and mode register 107 / 112 not off), else the direct circuit. Mixing circuit 2 uses its room setpoint (register 113), the "Mischer 2" menu path and the "MKR2 Raumsoll" entity in the hints. The `mkr_set_*` sensors show the flow setpoint of the selected mixing circuit.
- **New option "Group room sensors"** (`room_grouping`: by floor, each sensor). By floor (default) averages the room sensors per floor of their area in Home Assistant; sensors without a floor stay individual. The check still follows the coldest group.
- The efficiency check sensor has new attributes `circuit_setting` and `coldest_room`; the entries of `rooms` carry `name`, `level` and `sensors`. With floor levels they are sorted top floor first, else coldest first.
- Dashboard card shows floors, marks the coldest one and the number of sensors.

## [0.2.0] - 2026-11-08

- **Efficiency check supports a mixing circuit 1 (MKR1):** if the flow setpoint (register 35) is above 0 and the MKR1 mode (register 107) is not off, the check uses the MKR1 room setpoint (register 108) and reports the measured MKR1 heating curve (new sensors "Mixer 1 curve flow setpoint at 18 / 0 / minus 15 degrees"). Hints then name the Mischer 1 menu path and the "MKR1 Raumsoll" entity; the factory-curve comparison is skipped.
- New hint "Puffer wird höher geladen als nötig" when the buffer charging setpoint (HKR) is more than 3 K above the Mischer 1 flow setpoint at 0 °C outdoor.
- The efficiency check sensor has a new attribute `circuit` (`hkr` / `mkr1`).

## [0.1.0] - 2026-11-08

First release.

- **Read-only by default:** all values of the NEO-RKM register map (manual 7734937-01) as sensors with long-term statistics: temperatures, pressures, flow, compressor, energy counters, operating hours, demand, operating mode, derived values (spread, superheat, lift, SPF).
- **Write access is opt-in** and limited by a central whitelist (`safety.py`) within the customer level of the operating manual: operating mode (without "off"), room setpoint HKR (= parallel shift of the heating curve) 15–25 °C, DHW 40–50 °C, DHW frost protection 10–45 °C, cooling return min 18–25 °C. Everything that bypasses the heat pump's own control (sensor overrides, compressor speed, flow/return overrides, 2nd stage, fault reset, forcing the utility release) is not writable.
- **PV surplus** (option): power target register 125 with watchdog, reset on start/stop.
- **Price lock** (option): utility lock via registers 149/150 or an external switch (e.g. Shelly with NC relay, effect check via EVU release). Max. 2 h per lock, 6 h per day, 60 min pause, not below −10 °C.
- **Grid operator has priority** (EVU lock / §14a EnWG): no PV target and no own lock while the grid operator controls the heat pump; its lock time counts towards the daily limit.
- **Efficiency check:** 14 days of operating data, measured heating curve (return setpoint at 18 / 0 / −15 °C), room temperature per sensor (coldest room decides, multi-family houses), cycling, spread, DHW, defrost, SPF 30 days; plain-language hints with menu paths from the operating manual.
- Extras: analytics package (SPF, PV share, cycling, PV and price lock automations), offline database analysis script, dashboard cards, technical documentation (`docs/TECHNIK.md`), own logo.
