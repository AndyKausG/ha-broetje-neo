/*
 * Brötje NEO – frontend for the broetje_neo integration (MIT).
 *
 * Shipped and registered by the integration itself, no HACS frontend
 * resource needed:
 *   - card      type: custom:broetje-neo-card        (animated plant schema)
 *   - strategy  strategy: {type: custom:broetje-neo} (complete dashboard)
 *
 * Entities are found by platform + translation_key of the integration, so
 * the device name and the HA language do not matter.
 */

const DOMAIN = "broetje_neo";
const VERSION = "0.6.0";

// ------------------------------------------------------------------ entities
/** Map "domain.translation_key" -> entity_id for one broetje_neo device. */
export function resolveEntities(hass, deviceId, overrides) {
  const all = Object.values(hass.entities || {}).filter((e) => e.platform === DOMAIN);
  const device = deviceId || (all.find((e) => e.device_id) || {}).device_id;
  const map = {};
  for (const e of all) {
    if (device && e.device_id !== device) continue;
    if (!e.translation_key) continue;
    map[`${e.entity_id.split(".")[0]}.${e.translation_key}`] = e.entity_id;
  }
  return { ...map, ...(overrides || {}), _device: device };
}

const KEYS = {
  state: "sensor.plant_state",
  outdoor: "sensor.outdoor_temperature",
  flow: "sensor.flow_temperature",
  ret: "sensor.return_temperature",
  buffer: "sensor.buffer_temperature",
  bufferSet: "sensor.return_setpoint_actual",
  dhw: "sensor.dhw_temperature",
  mkrSet: "sensor.mkr1_flow_setpoint_actual",
  mkrMode: "sensor.mkr1_operating_mode_status",
  mode: "sensor.operating_mode_status",
  speed: "sensor.compressor_speed",
  pel: "sensor.electrical_power",
  pth: "sensor.thermal_power",
  cop: "sensor.cop_calculated",
  pLow: "sensor.low_pressure",
  pHigh: "sensor.high_pressure",
  tEvap: "sensor.evaporation_temperature",
  tCond: "sensor.condensation_temperature",
  exv: "sensor.expansion_valve",
  curve18: "sensor.mkr_set_18",
  curve0: "sensor.mkr_set_0",
  curveM15: "sensor.mkr_set_m15",
  compressor: "binary_sensor.compressor",
  fan: "binary_sensor.source_fan",
  bufferPump: "binary_sensor.buffer_pump",
  heatingPump: "binary_sensor.heating_pump",
  demandHeat: "binary_sensor.demand_heating",
  demandDhw: "binary_sensor.demand_dhw",
};

// ------------------------------------------------------------------- texts
const TEXT = {
  de: {
    heating: "Die Wärmepumpe holt Wärme aus der Außenluft und lädt den Heizpuffer.",
    heating_demand: "Das Haus braucht Wärme. Der Puffer ist noch warm genug, die Wärmepumpe wartet.",
    hot_water: "Die Wärmepumpe erwärmt gerade das Warmwasser.",
    dhw_demand: "Warmwasser wird angefordert. Die Wärmepumpe wartet noch (z. B. Mindestpause).",
    defrost: "Das Außengerät taut Eis ab und nutzt dafür kurz Wärme aus dem Puffer.",
    cooling: "Kühlbetrieb.",
    compressor_running: "Die Wärmepumpe läuft ohne Heiz- oder Warmwasseranforderung (z. B. PV-Überschuss).",
    summer: "Sommerbetrieb: keine Heizung, Warmwasser nur bei Bedarf.",
    standby: "Alles warm genug. Die Wärmepumpe ruht.",
    price_lock: "Preissperre: Die Wärmepumpe pausiert wegen hoher Strompreise.",
    utility_lock: "Der Netzbetreiber hat die Wärmepumpe vorübergehend gesperrt.",
    off: "Die Wärmepumpe ist ausgeschaltet.",
    fault: "Störung. Bitte Bedienteil prüfen oder Fachbetrieb anrufen.",
    fbhOn: (v) => `Die Fußbodenheizung wird aus dem Puffer versorgt (Vorlauf Soll ${v}).`,
    fbhOff: "Die Pumpe der Fußbodenheizung steht.",
    fbhSummer: "Fußbodenheizung im Sommerbetrieb.",
    missing: "Keine Entitäten der Integration Brötje NEO gefunden.",
    hp: "Wärmepumpe", outside: "außen", fan: "Lüfter", comp: "Verdichter",
    evap: "Verdampfer", cond: "Verflüssiger", exv: "Expansionsventil",
    running: "Kältekreis: macht aus Luftwärme Heizwärme",
    standstill: "Stillstand: Drücke gleichen sich aus",
    defrostTag: "❄ Abtauen", valve: "Ventil:", valveBuf: "Puffer", valveDhw: "Warmw.",
    buffer: "Puffer", dhw: "Warmwasser", mixer: "Mischer MKR1", floor: "Fußbodenheizung",
    set: "Soll", curve: "Heizkurve MKR1 (gemessen)", curveWait: "Kurve: Effizienz-Check sammelt noch Daten",
    outsideAxis: "°C außen", power: (a, b) => `${a} Strom → ${b} Wärme`, warm: "warm", cold: "kalt",
  },
  en: {
    heating: "The heat pump takes heat from the outside air and charges the buffer.",
    heating_demand: "The house needs heat. The buffer is still warm enough, the heat pump waits.",
    hot_water: "The heat pump is heating the hot water.",
    dhw_demand: "Hot water is requested. The heat pump still waits (e.g. minimum pause).",
    defrost: "The outdoor unit is defrosting and briefly uses heat from the buffer.",
    cooling: "Cooling.",
    compressor_running: "The heat pump runs without heating or hot water demand (e.g. PV surplus).",
    summer: "Summer mode: no heating, hot water on demand only.",
    standby: "Everything warm enough. The heat pump rests.",
    price_lock: "Price lock: the heat pump pauses because of high electricity prices.",
    utility_lock: "The grid operator has locked the heat pump for now.",
    off: "The heat pump is switched off.",
    fault: "Fault. Please check the controller or call your installer.",
    fbhOn: (v) => `Underfloor heating is supplied from the buffer (flow setpoint ${v}).`,
    fbhOff: "The underfloor heating pump is off.",
    fbhSummer: "Underfloor heating in summer mode.",
    missing: "No entities of the Brötje NEO integration found.",
    hp: "Heat pump", outside: "outside", fan: "Fan", comp: "Compressor",
    evap: "Evaporator", cond: "Condenser", exv: "Expansion valve",
    running: "Refrigerant circuit: turns air heat into heating heat",
    standstill: "Standstill: pressures equalise",
    defrostTag: "❄ Defrost", valve: "Valve:", valveBuf: "Buffer", valveDhw: "DHW",
    buffer: "Buffer", dhw: "Hot water", mixer: "Mixer MKR1", floor: "Underfloor heating",
    set: "set", curve: "Heating curve MKR1 (measured)", curveWait: "Curve: efficiency check still collecting",
    outsideAxis: "°C outside", power: (a, b) => `${a} power → ${b} heat`, warm: "warm", cold: "cold",
  },
};

const COLOR = {
  fault: "#db4437", price_lock: "#9c27b0", utility_lock: "#9c27b0", off: "#757575",
  defrost: "#03a9f4", hot_water: "#ff9800", heating: "#e4572e", cooling: "#2196f3",
  compressor_running: "#e4572e", heating_demand: "#ffb300", dhw_demand: "#ffb300",
  summer: "#fbc02d",
};
const HOT = "#e4572e";
const COLD = "#3b82f6";
const WARM = "#ff9800";
const IDLE = "var(--divider-color, #bdbdbd)";

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// -------------------------------------------------------------------- render
/** Pure SVG renderer (also used by the tests with a mocked hass). */
export function renderSchema(hass, ids) {
  const T = TEXT[(hass.locale?.language || hass.language || "en").startsWith("de") ? "de" : "en"];
  const obj = (k) => (ids[KEYS[k]] ? hass.states[ids[KEYS[k]]] : undefined);
  const st = (k) => obj(k)?.state ?? "unavailable";
  const on = (k) => st(k) === "on";
  const num = (k) => {
    const v = parseFloat(st(k));
    return Number.isNaN(v) ? null : v;
  };
  const fmt = (k) => {
    const o = obj(k);
    if (!o || ["unknown", "unavailable"].includes(o.state)) return "–";
    return esc(hass.formatEntityState ? hass.formatEntityState(o) : `${o.state}`);
  };
  const tcol = (t) => {
    if (t === null) return "var(--disabled-text-color, #9e9e9e)";
    const x = Math.max(0, Math.min(1, (t - 20) / 40));
    return `hsl(${Math.round(220 - 220 * x)},75%,50%)`;
  };

  if (!obj("state")) {
    return `<div style="padding:16px">${esc(T.missing)}</div>`;
  }
  const code = st("state");
  const label = fmt("state");
  const scol = COLOR[code] || "var(--secondary-text-color)";
  const run = on("compressor");
  const fan = on("fan");
  const defrost = code === "defrost";
  const ww = run && on("demandDhw") && !defrost;
  const buf = on("bufferPump") && !ww;
  const water = buf || ww || defrost;
  const mkr = on("heatingPump");
  const speed = num("speed");
  const fanDur = speed ? Math.max(0.35, 2.2 - speed / 50) : 1.6;
  const tA = num("outdoor");
  const tP = num("buffer");
  const tW = num("dhw");
  const tM = num("mkrSet");
  const curve = [
    [18, num("curve18")],
    [0, num("curve0")],
    [-15, num("curveM15")],
  ].filter((p) => p[1] !== null);
  const fbh =
    st("mkrMode") === "summer" ? T.fbhSummer : mkr ? T.fbhOn(fmt("mkrSet")) : T.fbhOff;

  const pipe = (d, col, active, rev) =>
    `<path d="${d}" stroke="${active ? col : IDLE}" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round"${
      active ? ` class="flow${rev ? " rev" : ""}"` : ""
    }/>`;
  const pump = (x, y, active) =>
    `<circle cx="${x}" cy="${y}" r="12" fill="var(--card-background-color, #fff)" stroke="${active ? HOT : IDLE}" stroke-width="3"/>` +
    `<path d="M${x - 5} ${y - 7} L${x + 7} ${y} L${x - 5} ${y + 7} Z" fill="${active ? HOT : IDLE}"${active ? ' class="pulse"' : ""}/>`;
  const tank = (x, y, w, h, t, name, val) =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="34" fill="${tcol(t)}" fill-opacity="0.25" stroke="${tcol(t)}" stroke-width="3"/>` +
    `<text x="${x + w / 2}" y="${y + h / 2 - 6}" class="lbl" text-anchor="middle">${name}</text>` +
    `<text x="${x + w / 2}" y="${y + h / 2 + 20}" class="val" text-anchor="middle">${val}</text>`;
  const arc = (x1, y1, x2, y2, col) =>
    `<path d="M${x1} ${y1} A80 80 0 0 1 ${x2} ${y2}" stroke="${run ? col : IDLE}" stroke-width="4" fill="none"${run ? ' class="flow"' : ""}/>`;
  const X = (t) => 620 + Math.max(0, Math.min(1, (20 - t) / 35)) * 250;
  const Y = (v) => 450 - Math.max(0, Math.min(1, (v - 20) / 30)) * 130;
  const curvePath =
    curve.length >= 2
      ? `<path d="${curve.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join(" ")}" stroke="${HOT}" stroke-width="3" fill="none"/>`
      : `<text x="745" y="336" class="sml" text-anchor="middle">${T.curveWait}</text>`;
  const point =
    tA !== null && tM !== null
      ? `<circle cx="${X(tA).toFixed(1)}" cy="${Y(tM).toFixed(1)}" r="7" fill="${scol}" stroke="var(--primary-text-color)" stroke-width="2"/>`
      : "";

  return `
<svg viewBox="0 0 900 470" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${label}">
  <style>
    .lbl { fill: var(--secondary-text-color); font-size: 15px; }
    .sml { fill: var(--secondary-text-color); font-size: 12.5px; }
    .val { fill: var(--primary-text-color); font-size: 21px; font-weight: 600; }
    .vs { fill: var(--primary-text-color); font-size: 14px; font-weight: 600; }
    .txt { fill: var(--primary-text-color); font-size: 16px; }
    .big { font-size: 26px; font-weight: 700; }
    .flow { stroke-dasharray: 12 10; animation: flow 1.1s linear infinite; }
    .rev { animation-direction: reverse; }
    .spin { transform-origin: 70px 175px; animation: spin ${fanDur}s linear infinite; }
    .pulse { animation: pulse 1.4s ease-in-out infinite; }
    @keyframes flow { to { stroke-dashoffset: -22; } }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes pulse { 50% { opacity: 0.35; } }
    @media (prefers-reduced-motion: reduce) { .flow, .spin, .pulse { animation: none; } }
  </style>

  <text x="20" y="32" class="big" fill="${scol}">${label}</text>
  <text x="20" y="58" class="txt">${esc(T[code] || "")}</text>
  <text x="20" y="80" class="lbl">${fbh}</text>
  <text x="880" y="28" class="lbl" text-anchor="end">COP ${fmt("cop")}</text>
  <text x="880" y="48" class="sml" text-anchor="end">${T.power(fmt("pel"), fmt("pth"))}</text>
  <circle cx="770" cy="70" r="5" fill="${HOT}"/><text x="780" y="75" class="sml">${T.warm}</text>
  <circle cx="830" cy="70" r="5" fill="${COLD}"/><text x="840" y="75" class="sml">${T.cold}</text>

  <rect x="20" y="100" width="310" height="355" rx="14" fill="none" stroke="${run ? scol : IDLE}" stroke-width="3"/>
  <text x="34" y="124" class="lbl">${T.hp}</text>
  <text x="316" y="124" class="lbl" text-anchor="end">${T.outside} ${fmt("outdoor")}</text>
  <circle cx="70" cy="175" r="34" fill="none" stroke="${fan ? COLD : IDLE}" stroke-width="3"/>
  <g class="${fan ? "spin" : ""}" fill="${fan ? COLD : IDLE}">
    <path d="M70 175 C63 155 68 145 78 143 C80 157 76 165 70 175 Z"/>
    <path d="M70 175 C90 168 101 174 102 184 C88 186 80 181 70 175 Z"/>
    <path d="M70 175 C57 191 46 191 40 182 C51 174 61 172 70 175 Z"/>
  </g>
  <circle cx="70" cy="175" r="4" fill="var(--primary-text-color)"/>
  <text x="70" y="226" class="sml" text-anchor="middle">${T.fan}</text>

  ${arc(120, 315, 200, 235, COLD)}
  ${arc(200, 235, 280, 315, HOT)}
  ${arc(280, 315, 200, 395, WARM)}
  ${arc(200, 395, 120, 315, COLD)}
  <circle cx="200" cy="235" r="14" fill="var(--card-background-color, #fff)" stroke="${run ? scol : IDLE}" stroke-width="3" class="${run ? "pulse" : ""}"/>
  <text x="200" y="240" class="sml" text-anchor="middle">V</text>
  <text x="200" y="208" class="sml" text-anchor="middle">${T.comp} <tspan class="vs">${fmt("speed")}</tspan></text>
  <rect x="110" y="300" width="20" height="30" rx="3" fill="var(--card-background-color, #fff)" stroke="${run ? COLD : IDLE}" stroke-width="3"/>
  <rect x="270" y="300" width="20" height="30" rx="3" fill="var(--card-background-color, #fff)" stroke="${run ? HOT : IDLE}" stroke-width="3"/>
  <path d="M190 387 L210 403 L210 387 L190 403 Z" fill="var(--card-background-color, #fff)" stroke="${run ? WARM : IDLE}" stroke-width="3"/>
  <text x="200" y="425" class="sml" text-anchor="middle">${T.exv} <tspan class="vs">${fmt("exv")}</tspan></text>
  <text x="163" y="290" class="sml" text-anchor="middle">${T.evap}</text>
  <text x="163" y="310" class="vs" text-anchor="middle">${fmt("pLow")}</text>
  <text x="163" y="328" class="vs" text-anchor="middle">${fmt("tEvap")}</text>
  <text x="237" y="290" class="sml" text-anchor="middle">${T.cond}</text>
  <text x="237" y="310" class="vs" text-anchor="middle">${fmt("pHigh")}</text>
  <text x="237" y="328" class="vs" text-anchor="middle">${fmt("tCond")}</text>
  <text x="175" y="447" class="sml" text-anchor="middle">${run ? T.running : T.standstill}</text>
  ${defrost ? `<text x="70" y="250" class="sml" text-anchor="middle" fill="#03a9f4">${T.defrostTag}</text>` : ""}

  ${pipe("M290 300 H380", HOT, water, defrost)}
  ${pipe("M420 345 H280 V330", COLD, water, defrost)}
  ${pipe("M380 300 V150 H470", HOT, buf || defrost, defrost)}
  ${pipe("M470 230 H420 V345", COLD, buf || defrost, defrost)}
  ${pipe("M380 300 V330 H470", HOT, ww, false)}
  ${pipe("M470 420 H420 V345", COLD, ww, false)}
  <circle cx="380" cy="300" r="11" fill="var(--card-background-color, #fff)" stroke="${water ? HOT : IDLE}" stroke-width="3"/>
  <path d="M380 300 L380 ${ww ? 312 : 288}" stroke="${water ? HOT : IDLE}" stroke-width="4" stroke-linecap="round"/>
  <text x="388" y="190" class="sml">${T.valve}</text>
  <text x="388" y="206" class="sml">${ww ? T.valveDhw : T.valveBuf}</text>
  ${pump(445, 230, buf || defrost)}
  <text x="352" y="288" class="sml" text-anchor="middle">${fmt("flow")}</text>
  <text x="352" y="366" class="sml" text-anchor="middle">${fmt("ret")}</text>

  ${tank(470, 100, 100, 160, tP, T.buffer, fmt("buffer"))}
  ${tank(470, 285, 100, 165, tW, T.dhw, fmt("dhw"))}

  ${pipe("M570 130 H700", HOT, mkr, false)}
  ${pipe("M700 230 H570", COLD, mkr, false)}
  <path d="M600 118 L620 130 L600 142 Z M640 118 L620 130 L640 142 Z" fill="var(--card-background-color, #fff)" stroke="${mkr ? HOT : IDLE}" stroke-width="3"/>
  <path d="M620 130 V230" stroke="${mkr ? COLD : IDLE}" stroke-width="2" stroke-dasharray="4 4"/>
  ${pump(670, 130, mkr)}
  <text x="588" y="106" class="sml">${T.mixer} · ${fmt("mkrMode")}</text>
  <path d="M700 130 H870 V155 H720 V180 H870 V205 H720 V230 H700" fill="none" stroke="${mkr ? tcol(tM) : IDLE}" stroke-width="4" ${mkr ? 'class="flow"' : ""}/>
  <text x="785" y="254" class="sml" text-anchor="middle">${T.floor} · ${T.set} <tspan class="vs">${fmt("mkrSet")}</tspan></text>

  <text x="620" y="290" class="lbl">${T.curve}</text>
  <path d="M620 320 V450 H870" stroke="var(--secondary-text-color)" stroke-width="1" fill="none"/>
  <path d="M${X(0).toFixed(1)} 320 V450" stroke="${IDLE}" stroke-width="1" stroke-dasharray="3 4"/>
  ${curvePath}
  ${point}
  <text x="616" y="324" class="sml" text-anchor="end">50</text>
  <text x="616" y="452" class="sml" text-anchor="end">20</text>
  <text x="620" y="466" class="sml">+20</text>
  <text x="${X(0).toFixed(1)}" y="466" class="sml" text-anchor="middle">0</text>
  <text x="870" y="466" class="sml" text-anchor="end">−15 ${T.outsideAxis}</text>
</svg>`;
}

// ---------------------------------------------------------------------- card
const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

class BroetjeNeoCard extends Base {
  setConfig(config) {
    this._config = config || {};
    this._sig = undefined;
  }

  set hass(hass) {
    this._hass = hass;
    const ids = resolveEntities(hass, this._config.device_id, this._config.entities);
    if (this._config.heating_pump_entity) ids[KEYS.heatingPump] = this._config.heating_pump_entity;
    // re-render only when one of the used states changed
    const sig =
      Object.values(KEYS)
        .map((k) => (ids[k] ? hass.states[ids[k]]?.state : ""))
        .join("|") + (hass.locale?.language || "");
    if (sig === this._sig) return;
    this._sig = sig;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 8px; }
        svg { width: 100%; height: auto; display: block;
              font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, sans-serif)); }
      </style>
      <ha-card>${renderSchema(hass, ids)}</ha-card>`;
    const card = this.shadowRoot.querySelector("ha-card");
    card.addEventListener("click", () => {
      const entityId = ids[KEYS.state];
      if (!entityId) return;
      const ev = new Event("hass-more-info", { bubbles: true, composed: true });
      ev.detail = { entityId };
      this.dispatchEvent(ev);
    });
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { columns: "full", min_columns: 6 };
  }

  static getStubConfig() {
    return {};
  }
}

// ------------------------------------------------------------------ strategy
const S = {
  sensor: (k) => `sensor.${k}`,
  bin: (k) => `binary_sensor.${k}`,
};

/** Dashboard config for the strategy (exported for the tests). */
export function buildDashboard(hass, ids, options = {}) {
  const de = (hass.locale?.language || hass.language || "en").startsWith("de");
  const L = (d, e) => (de ? d : e);
  const id = (key) => ids[key];
  const tile = (key, name, extra = {}) =>
    id(key) ? { type: "tile", entity: id(key), ...(name ? { name } : {}), ...extra } : null;
  const clean = (cards) => cards.filter(Boolean);
  const apex = options.charts === "apexcharts";

  const heading = (text, icon) => ({ type: "heading", heading: text, icon });

  const now = clean([
    heading(L("Heizt sie schon?", "Is it heating?"), "mdi:radiator"),
    tile(S.sensor("plant_state"), L("Status", "State"), { grid_options: { columns: "full" } }),
    tile(S.bin("demand_heating"), L("Heizanforderung", "Heating demand"), { color: "amber" }),
    tile(S.bin("heating_pump"), L("Heizkreispumpe", "Heating pump"), { color: "red" }),
    tile(S.bin("buffer_pump"), L("Puffer laden", "Buffer charging"), { color: "orange" }),
    tile(S.bin("compressor_heating"), L("Verdichter heizt", "Compressor heating"), { color: "red" }),
    tile(S.sensor("heating_demand_last_start"), L("Anforderung zuletzt", "Demand last")),
    tile(S.sensor("compressor_heating_last_start"), L("Verdichter zuletzt", "Compressor last")),
    tile(S.bin("demand_dhw"), L("WW-Anforderung", "DHW demand"), { color: "orange" }),
    tile(S.bin("defrost"), L("Abtauen", "Defrost"), { color: "light-blue" }),
  ]);
  const temps = clean([
    heading(L("Temperaturen", "Temperatures"), "mdi:thermometer"),
    tile(S.sensor("outdoor_temperature"), L("Außen", "Outdoor"), { color: "blue" }),
    tile(S.sensor("mkr1_flow_setpoint_actual"), L("FBH Vorlauf Soll", "UFH flow set"), { color: "deep-orange" }),
    tile(S.sensor("flow_temperature"), L("WP Vorlauf", "HP flow"), { color: "red" }),
    tile(S.sensor("return_temperature"), L("WP Rücklauf", "HP return"), { color: "indigo" }),
    tile(S.sensor("buffer_temperature"), L("Puffer", "Buffer"), { color: "orange" }),
    tile(S.sensor("dhw_temperature"), L("Warmwasser", "Hot water"), { color: "amber" }),
    tile(S.sensor("return_setpoint_actual"), L("Puffer Soll", "Buffer set"), { color: "grey" }),
    tile(S.sensor("compressor_speed"), L("Verdichter", "Compressor"), { color: "red" }),
  ]);
  const eff = clean([
    heading(L("Effizienz", "Efficiency"), "mdi:leaf"),
    tile(S.sensor("cop_calculated"), L("COP live", "COP live"), { color: "green" }),
    tile(S.sensor("cop_today"), L("Arbeitszahl heute", "SPF today"), { color: "green" }),
    tile(S.sensor("spf_30d"), L("Arbeitszahl 30 Tage", "SPF 30 days"), { color: "green" }),
    tile(S.sensor("electrical_energy_today"), L("Strom heute", "Power today"), { color: "yellow" }),
    tile(S.sensor("thermal_energy_today"), L("Wärme heute", "Heat today"), { color: "deep-orange" }),
    tile(S.sensor("starts_24h"), L("Starts 24 h", "Starts 24 h")),
    tile(S.sensor("run_time_per_start"), L("Laufzeit/Start", "Run time/start")),
    tile(S.sensor("defrosts_24h"), L("Abtauungen 24 h", "Defrosts 24 h")),
    tile(S.sensor("efficiency_check"), L("Effizienz-Check", "Efficiency check")),
    tile(S.sensor("heating_limit_observed"), L("Heizgrenze (gelernt)", "Heating limit (learned)"), { color: "grey" }),
  ]);
  const run = clean([
    heading(L("Laufzeiten", "Run times"), "mdi:timer-outline"),
    tile(S.sensor("heating_demand_today"), L("Anforderung heute", "Demand today"), { color: "amber" }),
    tile(S.sensor("compressor_heating_runtime_today"), L("Verdichter Heizen heute", "Compressor heating today"), { color: "red" }),
    tile(S.sensor("heating_demand_yesterday"), L("Anforderung gestern", "Demand yesterday"), { color: "amber" }),
    tile(S.sensor("compressor_heating_runtime_yesterday"), L("Verdichter Heizen gestern", "Compressor heating yesterday"), { color: "red" }),
    tile(S.sensor("heating_demand_7d"), L("Anforderung 7 Tage", "Demand 7 days"), { color: "amber" }),
    tile(S.sensor("compressor_heating_runtime_7d"), L("Verdichter Heizen 7 Tage", "Compressor heating 7 days"), { color: "red" }),
    tile(S.sensor("compressor_runtime_today"), L("Verdichter gesamt heute", "Compressor total today")),
    tile(S.sensor("heating_season_start"), L("Heizperiode seit", "Heating season since")),
  ]);

  // 30 days: run time per day (bars) vs. mean outdoor temperature and heating limit
  const days30 = apex
    ? {
        type: "custom:apexcharts-card",
        grid_options: { columns: "full" },
        graph_span: "30d",
        span: { end: "day" },
        header: { show: true, title: L("Laufzeit je Tag und Außentemperatur (30 Tage)", "Run time per day and outdoor temperature (30 days)") },
        apex_config: { chart: { height: 320 }, legend: { show: true } },
        yaxis: [
          { id: "h", min: 0, decimals: 1, apex_config: { title: { text: L("h/Tag", "h/day") } } },
          { id: "t", opposite: true, decimals: 0, apex_config: { title: { text: "°C" } } },
        ],
        series: clean([
          id(S.sensor("heating_demand_today")) && { entity: id(S.sensor("heating_demand_today")), name: L("Heizanforderung", "Heating demand"), type: "column", yaxis_id: "h", color: "#ffb300", statistics: { type: "change", period: "day", align: "start" } },
          id(S.sensor("compressor_heating_runtime_today")) && { entity: id(S.sensor("compressor_heating_runtime_today")), name: L("Verdichter Heizen", "Compressor heating"), type: "column", yaxis_id: "h", color: "#e4572e", statistics: { type: "change", period: "day", align: "start" } },
          id(S.sensor("outdoor_temperature")) && { entity: id(S.sensor("outdoor_temperature")), name: L("Außen Ø", "Outdoor avg"), type: "line", yaxis_id: "t", color: "#3b82f6", stroke_width: 2, statistics: { type: "mean", period: "day", align: "start" } },
          id(S.sensor("heating_limit_observed")) && { entity: id(S.sensor("heating_limit_observed")), name: L("Heizgrenze gelernt", "Heating limit learned"), type: "line", curve: "stepline", yaxis_id: "t", color: "#616161", stroke_width: 2, stroke_dash: 6, statistics: { type: "mean", period: "day", align: "start" } },
          id(S.sensor("heating_limit_setting")) && { entity: id(S.sensor("heating_limit_setting")), name: L("Heizgrenze eingestellt", "Heating limit set"), type: "line", curve: "stepline", yaxis_id: "t", color: "#9e9e9e", stroke_width: 1, stroke_dash: 3, statistics: { type: "mean", period: "day", align: "start" } },
        ]),
      }
    : null;
  const days30Core = apex
    ? []
    : [
        {
          type: "statistics-graph",
          title: L("Laufzeit je Tag (30 Tage)", "Run time per day (30 days)"),
          entities: clean([id(S.sensor("heating_demand_today")), id(S.sensor("compressor_heating_runtime_today"))]),
          stat_types: ["change"],
          period: "day",
          days_to_show: 30,
          chart_type: "bar",
          grid_options: { columns: "full" },
        },
        {
          type: "statistics-graph",
          title: L("Außentemperatur und Heizgrenze (30 Tage)", "Outdoor temperature and heating limit (30 days)"),
          entities: clean([id(S.sensor("outdoor_temperature")), id(S.sensor("heating_limit_observed")), id(S.sensor("heating_limit_setting"))]),
          stat_types: ["mean"],
          period: "day",
          days_to_show: 30,
          chart_type: "line",
          grid_options: { columns: "full" },
        },
      ];

  const h24 = apex
    ? [
        {
          type: "custom:apexcharts-card",
          grid_options: { columns: "full" },
          graph_span: "24h",
          header: { show: true, title: L("Vorlauf, Puffer, Außen, Verdichter", "Flow, buffer, outdoor, compressor") },
          apex_config: { chart: { height: 320 }, legend: { show: true } },
          yaxis: [
            { id: "t", decimals: 0, apex_config: { title: { text: "°C" } } },
            { id: "p", opposite: true, min: 0, max: 100, decimals: 0, apex_config: { title: { text: "%" } } },
          ],
          series: clean([
            id(S.bin("demand_heating")) && { entity: id(S.bin("demand_heating")), name: L("Heizanforderung", "Heating demand"), type: "area", curve: "stepline", yaxis_id: "p", color: "#ffb300", opacity: 0.12, stroke_width: 0, transform: "return x === 'on' ? 100 : 0;" },
            id(S.sensor("compressor_speed")) && { entity: id(S.sensor("compressor_speed")), name: L("Verdichter", "Compressor"), type: "area", yaxis_id: "p", color: "#e4572e", opacity: 0.2, stroke_width: 1, group_by: { func: "avg", duration: "5min" } },
            id(S.sensor("flow_temperature")) && { entity: id(S.sensor("flow_temperature")), name: L("WP Vorlauf", "HP flow"), yaxis_id: "t", color: "#d32f2f", stroke_width: 2, group_by: { func: "avg", duration: "5min" } },
            id(S.sensor("mkr1_flow_setpoint_actual")) && { entity: id(S.sensor("mkr1_flow_setpoint_actual")), name: L("FBH Vorlauf Soll", "UFH flow set"), yaxis_id: "t", color: "#ff7043", curve: "stepline", stroke_width: 2, stroke_dash: 5 },
            id(S.sensor("buffer_temperature")) && { entity: id(S.sensor("buffer_temperature")), name: L("Puffer", "Buffer"), yaxis_id: "t", color: "#ff9800", stroke_width: 2, group_by: { func: "avg", duration: "5min" } },
            id(S.sensor("outdoor_temperature")) && { entity: id(S.sensor("outdoor_temperature")), name: L("Außen", "Outdoor"), yaxis_id: "t", color: "#3b82f6", stroke_width: 2, group_by: { func: "avg", duration: "15min" } },
          ]),
        },
      ]
    : [
        {
          type: "history-graph",
          title: L("Temperaturen 24 h", "Temperatures 24 h"),
          hours_to_show: 24,
          entities: clean([
            id(S.sensor("flow_temperature")),
            id(S.sensor("mkr1_flow_setpoint_actual")),
            id(S.sensor("buffer_temperature")),
            id(S.sensor("outdoor_temperature")),
          ]),
          grid_options: { columns: "full" },
        },
        {
          type: "history-graph",
          title: L("Verdichter und Anforderung 24 h", "Compressor and demand 24 h"),
          hours_to_show: 24,
          entities: clean([id(S.sensor("compressor_speed")), id(S.bin("demand_heating")), id(S.bin("compressor"))]),
          grid_options: { columns: "full" },
        },
      ];

  const badges = clean([
    id(S.sensor("plant_state")) && { type: "entity", entity: id(S.sensor("plant_state")), show_name: false },
    id(S.sensor("operating_mode_status")) && { type: "entity", entity: id(S.sensor("operating_mode_status")), show_name: false },
    id(S.sensor("mkr1_operating_mode_status")) && { type: "entity", entity: id(S.sensor("mkr1_operating_mode_status")), name: "FBH", show_name: true },
    id(S.bin("fault")) && { type: "entity", entity: id(S.bin("fault")), visibility: [{ condition: "state", entity: id(S.bin("fault")), state: "on" }] },
    id(S.bin("evu_release")) && { type: "entity", entity: id(S.bin("evu_release")), visibility: [{ condition: "state", entity: id(S.bin("evu_release")), state: "off" }] },
  ]);

  return {
    title: options.title || L("Wärmepumpe", "Heat pump"),
    views: [
      {
        title: options.title || L("Wärmepumpe", "Heat pump"),
        path: "waermepumpe",
        icon: "mdi:heat-pump",
        type: "sections",
        max_columns: 4,
        badges,
        sections: [
          { type: "grid", cards: now },
          { type: "grid", cards: temps },
          { type: "grid", cards: eff },
          { type: "grid", cards: run },
          {
            type: "grid",
            column_span: 2,
            cards: [
              heading(L("Anlage", "Plant"), "mdi:pipe"),
              { type: "custom:broetje-neo-card", ...(ids._device ? { device_id: ids._device } : {}) },
            ],
          },
          {
            type: "grid",
            column_span: 2,
            cards: [heading(L("Übergangszeit", "Transition period"), "mdi:chart-bar"), ...(days30 ? [days30] : days30Core)],
          },
          {
            type: "grid",
            column_span: 2,
            cards: [heading(L("Letzte 24 Stunden", "Last 24 hours"), "mdi:chart-line"), ...h24],
          },
        ],
      },
    ],
  };
}

async function apexAvailable() {
  if (customElements.get("apexcharts-card")) return true;
  // HACS resources may still be loading
  return Promise.race([
    customElements.whenDefined("apexcharts-card").then(() => true),
    new Promise((resolve) => setTimeout(() => resolve(false), 2000)),
  ]);
}

class BroetjeNeoStrategy extends Base {
  static async generate(config, hass) {
    const ids = resolveEntities(hass, config.device_id, config.entities);
    let charts = config.charts || "auto";
    if (charts === "auto") charts = (await apexAvailable()) ? "apexcharts" : "core";
    return buildDashboard(hass, ids, { charts, title: config.title });
  }
}

// Legacy element name for older frontends ("ll-strategy-<name>").
class BroetjeNeoStrategyLegacy extends BroetjeNeoStrategy {}

if (typeof customElements !== "undefined") {
  if (!customElements.get("broetje-neo-card")) {
    customElements.define("broetje-neo-card", BroetjeNeoCard);
  }
  if (!customElements.get("ll-strategy-dashboard-broetje-neo")) {
    customElements.define("ll-strategy-dashboard-broetje-neo", BroetjeNeoStrategy);
  }
  if (!customElements.get("ll-strategy-broetje-neo")) {
    customElements.define("ll-strategy-broetje-neo", BroetjeNeoStrategyLegacy);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === "broetje-neo-card")) {
    window.customCards.push({
      type: "broetje-neo-card",
      name: "Brötje NEO",
      description: "Animated plant schema of the Brötje NEO heat pump",
      documentationURL: "https://github.com/AndyKausG/ha-broetje-neo",
    });
  }
  // offered in "Add dashboard" by frontends that support it
  window.customStrategies = window.customStrategies || [];
  if (!window.customStrategies.some((c) => c.type === "broetje-neo")) {
    window.customStrategies.push({
      type: "broetje-neo",
      strategyType: "dashboard",
      name: "Brötje NEO",
      description: "Heat pump dashboard of the broetje_neo integration",
      documentationURL: "https://github.com/AndyKausG/ha-broetje-neo",
    });
  }
  console.info(`%c BROETJE-NEO %c ${VERSION} `, "background:#e4572e;color:#fff", "");
}
