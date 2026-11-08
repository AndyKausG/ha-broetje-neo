# AGENTS.md

Notes for AI agents and other contributors working on broetje_neo
(Home Assistant custom integration for Brötje BLW NEO heat pumps with NEO-RKM,
Modbus TCP, installed via HACS). Read this first.

## Repository layout

| Path | Content |
|---|---|
| `custom_components/broetje_neo/registers.py` | Register map, data types, scaling, "no data" values. **Pure, no Home Assistant imports** |
| `custom_components/broetje_neo/advisor.py` | Efficiency check: data collection and rules. **Pure** |
| `custom_components/broetje_neo/safety.py` | Write whitelist and limits. **The only place that decides what may be written** |
| `custom_components/broetje_neo/coordinator.py` | All Modbus I/O, guards (PV watchdog, price lock, grid operator priority), advisor feed |
| `custom_components/broetje_neo/{sensor,binary_sensor,number,select,switch}.py` | Entities, read from the coordinator only |
| `custom_components/broetje_neo/manifest.json` | **Version source of truth** |
| `custom_components/broetje_neo/brand/` | Logo / icon (sources in `docs/brand/`) |
| `scripts/gen_translations.py` | Generates `strings.json` and `translations/{de,en}.json`. Never edit those by hand |
| `extras/` | HA package, analysis script, dashboard cards |
| `docs/TECHNIK.md` | Technical documentation (German) |
| `tests/` | pytest (pure tests + Home Assistant harness tests) |
| `.github/workflows/` | `validation.yml` (HACS + Hassfest), `tests.yml` (pytest, pure pytest, ruff, translations), `release.yml` (automatic releases) |

Code, comments, commit messages and CHANGELOG are in **English**. README, docs,
entity names (de/en) and the efficiency check hints are user-facing and **German**.

## Safety rules (do not relax without an explicit request)

- New installations are **read-only**. Every write feature is behind an option that is
  **off by default**.
- Every Modbus write goes through `coordinator._write_raw` → `safety.check_write`.
  New writable registers need an entry in `safety.py` with a limit and a source
  (manual chapter).
- Never make writable: sensor value overrides (129–134), compressor speed (117/126),
  flow/return overrides (102/103, 109/110, 114/115), 2nd stage (147/148), fault reset
  (128), forcing the EVU release (149 = 1).
- The grid operator always has priority (EVU lock, §14a).
- The efficiency check never writes.

## Tests

The HA harness needs a virtualenv (the system Python's setuptools breaks some builds):

```bash
python -m venv ~/venv
~/venv/bin/pip install -r requirements_test.txt
~/venv/bin/python -m pytest -q
```

CI (`.github/workflows/tests.yml`) runs on every pull request and push to `main`:
pytest with the harness, pytest without the harness (pure tests only), `ruff check`,
`ruff format --check` and a check that the translations are generated.
Keep the pinned `pytest-homeassistant-custom-component` version in
`requirements_test.txt` current when Home Assistant moves on.

- All tests must pass before a push. New features get tests.
- Pure modules (`registers.py`, `advisor.py`) are loaded with `importlib` straight from
  the file (see `tests/test_registers.py`), so they must not use relative imports.
- Without the harness only the pure tests run: `tests/conftest.py` skips every test file
  that mentions `homeassistant` or `custom_components.broetje_neo` (no list to maintain).
- Modbus is simulated by `FakeModbusClient` in `tests/conftest.py`. Never add tests that
  need a real heat pump.
- Package, cards and analysis script are tested against the real German entity IDs
  (`tests/test_package.py`). Renaming an entity means updating `extras/` too.
- After changing entity names run `python scripts/gen_translations.py`.

## Versioning and releases

The version lives in `custom_components/broetje_neo/manifest.json` (semver).
Releases are **automatic** (`.github/workflows/release.yml`):

1. Raise `"version"` in `manifest.json` (feature = minor, fix = patch).
2. Add `## [X.Y.Z] - YYYY-MM-DD` at the top of `CHANGELOG.md`.
3. Merge to `main`.

Changes without a user-visible effect (docs for contributors, CI) need no version bump.

On the push to `main` the workflow creates the GitHub release `vX.Y.Z` with that
CHANGELOG section as text. HACS shows the version number and offers the update.
An existing release is never changed; never create or move tags by hand.

## Git and pull requests

- Work on a feature branch, never commit directly to `main`.
- Merge `main` into the branch rather than rebasing pushed branches.
- PRs are merged with a merge commit after the HACS, Hassfest and Tests checks are green.
- A merged branch is finished; follow-up work starts from the current `main` in a new PR.
