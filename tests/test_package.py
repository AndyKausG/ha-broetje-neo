"""Check the analytics package against real entity IDs (German HA)."""

from __future__ import annotations

from pathlib import Path
import re

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import parse_yaml
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Recorder (for history_stats) must start before hass."""
    return


EXTRAS = Path(__file__).parent.parent / "extras"
PACKAGE = EXTRAS / "packages" / "broetje_neo_analytics.yaml"
CARD = EXTRAS / "lovelace" / "heat-pump-card.yaml"
TOOL = EXTRAS / "tools" / "analyze_heatpump.py"
DASH_PACKAGE = EXTRAS / "packages" / "broetje_neo_dashboard.yaml"
DASHBOARD = EXTRAS / "dashboard" / "broetje-neo-dashboard.yaml"


async def _setup_de(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    hass.config.language = "de"
    entry = MockConfigEntry(
        domain=entry.domain, data={**entry.data, "name": "Brötje NEO"}, options=entry.options
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _settle(hass: HomeAssistant) -> None:
    # chained template sensors need one loop iteration per level
    for _ in range(4):
        await hass.async_block_till_done()


async def test_package_entity_ids_exist(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup_de(hass, config_entry)
    files = [PACKAGE, DASH_PACKAGE, *(EXTRAS / "lovelace").glob("*.yaml")]
    files += (EXTRAS / "dashboard").glob("*.yaml")
    text = "".join(f.read_text(encoding="utf-8") for f in files)
    ids = set(
        re.findall(r"\b((?:sensor|binary_sensor|number|switch|select)\.brotje_neo_\w+)", text)
    )
    assert ids
    missing = [i for i in sorted(ids) if hass.states.get(i) is None]
    assert not missing, missing


async def test_analyze_profile_entity_ids_exist(
    hass: HomeAssistant, fake_client, config_entry
) -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("analyze_heatpump", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["analyze_heatpump"] = mod
    spec.loader.exec_module(mod)
    await _setup_de(hass, config_entry)
    ids = [v.format(p="brotje_neo") for v in mod.PROFILES["broetje_neo"].values()]
    missing = [i for i in ids if hass.states.get(i) is None]
    assert not missing, missing


async def test_package_pv_surplus(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup_de(hass, config_entry)
    hass.states.async_set("sensor.anpassen_pv_leistung", "5000")
    hass.states.async_set("sensor.anpassen_netzbezug", "0")
    hass.states.async_set("sensor.anpassen_einspeisung", "2500")
    conf = parse_yaml(PACKAGE.read_text(encoding="utf-8"))
    assert await async_setup_component(hass, "template", {"template": conf["template"]})
    await hass.async_block_till_done()

    # house w/o heat pump = 5000 + 0 - 2500 - 1800 = 700 -> surplus 4300
    def val(eid: str) -> float:
        return float(hass.states.get(eid).state)

    assert val("sensor.wpa_pv_uberschuss_fur_wp") == 4300
    assert val("sensor.wpa_pv_leistung_in_wp") == 1800
    assert val("sensor.wpa_leistung_elektrisch_heizen") == 1800
    assert val("sensor.wpa_leistung_elektrisch_warmwasser") == 0

    # grid draw case: PV 1000, import 1500, house w/o WP = 700 -> surplus 300
    hass.states.async_set("sensor.anpassen_pv_leistung", "1000")
    hass.states.async_set("sensor.anpassen_netzbezug", "1500")
    hass.states.async_set("sensor.anpassen_einspeisung", "0")
    await _settle(hass)
    assert val("sensor.wpa_pv_uberschuss_fur_wp") == 300
    assert val("sensor.wpa_pv_leistung_in_wp") == 300

    # sensor failure -> unavailable
    hass.states.async_set("sensor.anpassen_pv_leistung", "unavailable")
    await _settle(hass)
    assert hass.states.get("sensor.wpa_pv_uberschuss_fur_wp").state == "unavailable"


async def test_package_full_config(hass: HomeAssistant, fake_client, config_entry) -> None:
    """Load all package domains to catch schema/runtime errors."""
    hass.config.language = "de"
    conf = parse_yaml(PACKAGE.read_text(encoding="utf-8"))
    # sensor platforms first: once the sensor domain is loaded by the config
    # entry, async_setup_component would ignore further YAML platforms
    assert await async_setup_component(hass, "sensor", {"sensor": conf["sensor"]})
    await _setup_de(hass, config_entry)
    for domain in ("input_boolean", "input_number", "template", "utility_meter", "automation"):
        assert await async_setup_component(hass, domain, {domain: conf[domain]}), domain
    await _settle(hass)
    for eid in (
        "sensor.wpa_strom",
        "sensor.wpa_warme",
        "sensor.wpa_pv_strom",
        "sensor.wpa_waerme_monat",
        "sensor.wpa_verdichterstarts_heute",
        "sensor.wpa_evu_sperrzeit_heute",
        "automation.wp_pv_uberschuss_an_neo_rkm_melden",
        "automation.wp_preissperre_bei_hohem_strompreis",
        "automation.wp_preissperre_beenden_bei_abschalten_der_automatik",
    ):
        assert hass.states.get(eid) is not None, eid
    # utility meter sources must exist
    for meter in conf["utility_meter"].values():
        assert hass.states.get(meter["source"]) is not None, meter["source"]


async def test_package_price_lock_automation(
    hass: HomeAssistant, fake_client, config_entry
) -> None:
    hass.config.language = "de"
    conf = parse_yaml(PACKAGE.read_text(encoding="utf-8"))
    await _setup_de(hass, config_entry)
    hass.states.async_set("sensor.anpassen_strompreis", "0.45")
    for domain in ("input_boolean", "input_number", "automation"):
        assert await async_setup_component(hass, domain, {domain: conf[domain]}), domain
    await _settle(hass)
    await hass.services.async_call(
        "input_number",
        "set_value",
        {"entity_id": "input_number.wpa_preis_grenze", "value": 0.35},
        blocking=True,
    )
    await hass.services.async_call(
        "input_boolean",
        "turn_on",
        {"entity_id": "input_boolean.wpa_preissperre_freigabe"},
        blocking=True,
    )
    auto = "automation.wp_preissperre_bei_hohem_strompreis"
    await hass.services.async_call("automation", "trigger", {"entity_id": auto}, blocking=True)
    await _settle(hass)
    assert fake_client.holding[150] == 1
    assert hass.states.get("switch.brotje_neo_preissperre").state == "on"

    hass.states.async_set("sensor.anpassen_strompreis", "0.20")
    await _settle(hass)
    assert fake_client.holding[150] == 0


async def test_efficiency_card_renders(hass: HomeAssistant, fake_client, config_entry) -> None:
    from homeassistant.helpers.template import Template

    fake_client.input[26] = 1  # fault -> at least one hint
    hass.states.async_set("sensor.eg", "22.0", {"friendly_name": "Erdgeschoss"})
    hass.states.async_set("sensor.dg", "20.5", {"friendly_name": "Dachgeschoss"})
    config_entry = MockConfigEntry(
        domain=config_entry.domain,
        data=config_entry.data,
        options={**config_entry.options, "room_sensors": ["sensor.eg", "sensor.dg"]},
    )
    await _setup_de(hass, config_entry)
    card = parse_yaml((EXTRAS / "lovelace" / "effizienz-check.yaml").read_text(encoding="utf-8"))
    out = Template(card["cards"][0]["content"], hass).async_render(parse_result=False)
    assert "Sammle Daten" in out
    assert "Störung aktiv" in out
    assert "Vorschlag:" in out
    assert "Räume / Stockwerke (7 Tage)" in out
    assert "- Dachgeschoss: 20.5 °C" in out
    assert out.index("Dachgeschoss") < out.index("Erdgeschoss")
    # no setext headings: a separator must never directly follow a text line
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line.strip() in ("***", "---") and i > 0:
            assert lines[i - 1].strip() == "", f"separator after text in line {i}"
    print(out)


async def _setup_dashboard_packages(hass: HomeAssistant, config_entry) -> MockConfigEntry:
    """Load the analytics and the dashboard package together (as in HA)."""
    hass.config.language = "de"
    ana = parse_yaml(PACKAGE.read_text(encoding="utf-8"))
    dash = parse_yaml(DASH_PACKAGE.read_text(encoding="utf-8"))
    assert await async_setup_component(hass, "sensor", {"sensor": ana["sensor"] + dash["sensor"]})
    entry = await _setup_de(hass, config_entry)
    conf = {
        "template": ana["template"] + dash["template"],
        "input_number": ana["input_number"] | dash["input_number"],
        "utility_meter": ana["utility_meter"],
    }
    for domain, value in conf.items():
        assert await async_setup_component(hass, domain, {domain: value}), domain
    await _settle(hass)
    return entry


async def test_dashboard_entity_ids_exist(hass: HomeAssistant, fake_client, config_entry) -> None:
    await _setup_dashboard_packages(hass, config_entry)
    text = DASHBOARD.read_text(encoding="utf-8")
    # commented-out optional cards are not checked
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    ids = set(
        re.findall(r"\b((?:sensor|binary_sensor|input_number)\.(?:wpd|wpa|brotje_neo)_\w+)", text)
    )
    assert "sensor.wpd_status" in ids
    missing = [i for i in sorted(ids) if hass.states.get(i) is None]
    assert not missing, missing


def test_dashboard_yaml_structure() -> None:
    conf = parse_yaml(DASHBOARD.read_text(encoding="utf-8"))
    view = conf["views"][0]
    assert view["type"] == "sections"
    cards = [c for s in view["sections"] for c in s["cards"]]
    types = {c["type"] for c in cards}
    assert {"custom:apexcharts-card", "custom:button-card"} <= types
    schema = next(c for c in cards if c["type"] == "custom:button-card")
    js = schema["custom_fields"]["schema"]
    assert js.strip().startswith("[[[") and js.strip().endswith("]]]")
    assert js.count("]]]") == 1
    # every entity the schema reads must trigger a redraw
    used = set(re.findall(r"'((?:sensor|binary_sensor)\.\w+)'", js))
    assert used <= set(schema["triggers_update"]), used - set(schema["triggers_update"])


async def test_dashboard_status(hass: HomeAssistant, fake_client, config_entry) -> None:
    entry = await _setup_dashboard_packages(hass, config_entry)
    coordinator = entry.runtime_data

    async def status(**regs: int) -> str:
        for addr, value in regs.items():
            fake_client.input[int(addr[1:])] = value
        await coordinator.async_refresh()
        await _settle(hass)
        code = hass.states.get("sensor.wpd_status_code").state
        assert hass.states.get("sensor.wpd_status").attributes["code"] == code
        return code

    # defaults: compressor on, demand heating
    assert await status() == "heizen"
    assert hass.states.get("sensor.wpd_status").state == "Heizen"
    assert hass.states.get("binary_sensor.wpd_verdichter_heizen").state == "on"
    # demand but buffer is warm enough: compressor off
    assert await status(r25=0) == "heizanforderung"
    assert hass.states.get("sensor.wpd_status").state == "Heizanforderung"
    assert hass.states.get("binary_sensor.wpd_verdichter_heizen").state == "off"
    assert await status(r41=30, r25=1) == "warmwasser"
    assert await status(r27=1) == "abtauen"
    # four-way valve during cooling is not a defrost
    assert await status(r41=10) == "kuehlen"
    assert await status(r27=0, r41=0, r25=0) == "standby"
    assert await status(r32=0) == "evu_sperre"
    assert await status(r32=1, r26=1) == "stoerung"
    assert hass.states.get("sensor.wpd_status").state == "Störung"
    fake_client.holding[100] = 3
    assert await status(r26=0) == "sommer"
