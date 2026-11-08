# Changelog

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
