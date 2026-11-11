"""Bundled frontend: registration, and card/strategy against the real entities."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.broetje_neo import frontend
from custom_components.broetje_neo.binary_sensor import BINARY_SENSORS
from custom_components.broetje_neo.sensor import ADVISOR_SENSORS, OPERATION_SENSORS, SENSORS

JS = Path(frontend.__file__).parent / frontend.JS_FILE


async def test_register_frontend(hass: HomeAssistant) -> None:
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components.add("frontend")
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_js:
        await frontend.async_register_frontend(hass)
        await frontend.async_register_frontend(hass)  # only once
    hass.http.async_register_static_paths.assert_awaited_once()
    cfg = hass.http.async_register_static_paths.call_args.args[0][0]
    assert cfg.url_path == "/broetje_neo_frontend/broetje-neo.js"
    assert Path(cfg.path) == JS and JS.is_file()
    add_js.assert_called_once()
    assert add_js.call_args.args[1].startswith("/broetje_neo_frontend/broetje-neo.js?v=")


async def test_register_frontend_skipped_without_http(hass: HomeAssistant) -> None:
    hass.http = None
    await frontend.async_register_frontend(hass)  # no error


def test_js_keys_exist_in_integration() -> None:
    """Every translation key the JS looks up is provided by the integration."""
    import re

    text = JS.read_text(encoding="utf-8")
    sensors = {d.key for d in SENSORS + OPERATION_SENSORS + ADVISOR_SENSORS}
    binaries = {d.key for d in BINARY_SENSORS}
    used = set(re.findall(r'"(sensor|binary_sensor)\.([a-z0-9_]+)"', text))
    used |= {("sensor", k) for k in re.findall(r'S\.sensor\("([a-z0-9_]+)"\)', text)}
    used |= {("binary_sensor", k) for k in re.findall(r'S\.bin\("([a-z0-9_]+)"\)', text)}
    assert len(used) > 40
    missing = [
        f"{d}.{k}" for d, k in sorted(used) if k not in (sensors if d == "sensor" else binaries)
    ]
    assert not missing, missing


NODE = shutil.which("node")

RUNNER = """
const [jsPath, dataPath] = process.argv.slice(2);
const data = JSON.parse(require("fs").readFileSync(dataPath, "utf8"));
import(require("url").pathToFileURL(jsPath).href).then(async (m) => {
  const hass = {
    entities: data.entities, states: data.states, locale: { language: data.lang },
    formatEntityState: (s) => s.state,
  };
  const ids = m.resolveEntities(hass);
  const out = {};
  for (const charts of ["apexcharts", "core"]) {
    out[charts] = m.buildDashboard(hass, ids, { charts });
  }
  out.svg = m.renderSchema(hass, ids);
  out.ids = ids;
  out.keys = m.KEYS;
  console.log(JSON.stringify(out));
});
"""


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("lang", ["de", "en"])
async def test_strategy_and_card_with_real_entities(
    hass: HomeAssistant, fake_client, config_entry, tmp_path, lang
) -> None:
    hass.config.language = lang
    entry = MockConfigEntry(
        domain=config_entry.domain, data={**config_entry.data, "name": "Brötje NEO"}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    entities = {
        e.entity_id: {
            "entity_id": e.entity_id,
            "platform": e.platform,
            "translation_key": e.translation_key,
            "device_id": e.device_id,
        }
        for e in er.async_entries_for_config_entry(reg, entry.entry_id)
    }
    states = {s.entity_id: {"state": s.state} for s in hass.states.async_all()}
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"entities": entities, "states": states, "lang": lang}))
    runner = tmp_path / "run.cjs"
    runner.write_text(RUNNER)
    module = tmp_path / "broetje-neo.mjs"  # ES module regardless of the node version
    shutil.copy(JS, module)
    proc = subprocess.run(
        [NODE, str(runner), str(module), str(data)], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    # the card's state entity is found without any name assumption
    assert out["ids"]["sensor.plant_state"] in states
    svg = out["svg"]
    assert "<svg" in svg and "undefined" not in svg and "NaN" not in svg
    assert ("Puffer" if lang == "de" else "Buffer") in svg
    # clickable elements: every data-k maps to an existing entity
    assert 'data-k="buffer"' in svg and 'data-k="outdoor"' in svg
    found = set(__import__("re").findall(r'data-k="([A-Za-z0-9]+)"', svg))
    assert found
    for k in found:
        assert out["ids"].get(out["keys"][k]) in states, k

    for charts in ("apexcharts", "core"):
        dash = out[charts]
        view = dash["views"][0]
        assert view["type"] == "sections"
        text = json.dumps(dash)
        used = set(__import__("re").findall(r'"((?:sensor|binary_sensor)\.[a-z0-9_]+)"', text))
        assert len(used) > 30
        missing = [i for i in sorted(used) if i not in states]
        assert not missing, missing
        cards = [c for s in view["sections"] for c in s["cards"]]
        assert any(c["type"] == "custom:broetje-neo-card" for c in cards)
        if charts == "core":
            assert not any(c["type"].startswith("custom:apexcharts") for c in cards)


def test_js_version_matches_manifest() -> None:
    import re

    manifest = json.loads((JS.parent.parent / "manifest.json").read_text(encoding="utf-8"))
    version = re.search(r'const VERSION = "([^"]+)"', JS.read_text(encoding="utf-8")).group(1)
    assert version == manifest["version"]
