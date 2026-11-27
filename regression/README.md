# Full regression suite and walkthrough

This project follows the owner's standard (project standard 1.1.0, section 3). The global skills run it and read
`profile.yaml` and this file:

| Command | What it does |
|---|---|
| `/regression` | Every stage below, a security audit by three fresh reviewers (bugs, claims, exposure), a private report, a `RUNS.md` line |
| `/walkthrough` | Every screen on desktop and phone (the page as an administrator and a household member, the web installer, the integration's Home Assistant screens), automated UX checks, a desktop and a phone reviewer, a report, a `WALKTHROUGHS.md` line |
| `/full-check` | Both, end to end (firmware compiles, full review, five reviewers at once), one summary |

None of them fixes product code: findings go in the reports and the owner decides. An on-demand check, every few
releases or after a big feature set (CI already covers ordinary changes). **Every new feature adds to this suite**
(CLAUDE.md): a catalogue entry in `catalogue/<area>.yaml` and, where it can be automated, a check in its stage.

## Commands

```
python3 regression/run.py check                 # quick: ci, unit, quality (quiet; exit 1 on failures) - before marking a PR ready
python3 regression/run.py --compile             # every regression stage, firmware compiles included
python3 regression/run.py --stage page          # one stage (repeatable); --with-walkthrough adds the walkthrough
python3 regression/run.py report [--walkthrough]   # out/report.html (and the walkthrough's report)
python3 regression/run.py brief|log|summary|manual|schema|walkthrough-due   # the standard's commands (standard.py)
python3 regression/ids.py sync <stage>          # register new check IDs
python3 -m pytest regression/tests              # the harness's own tests
```

Tools (install what's missing into venvs, nothing global beyond pip):

- `HA_PYTHON`: `pytest-homeassistant-custom-component` and `fonttools` at the versions in `.github/workflows/ci.yml`.
- `ESPHOME_PYTHON`: `esphome` at `ESPHOME_VERSION` from the same workflow (brings `esptool`/`espsecure`).
- `QUALITY_PYTHON` (optional): ruff, bandit, pip-audit, pytest at the pins in `quality/run.py`; otherwise the stage
  installs them into `out/.venv-quality`.
- Node and Playwright with Chromium (preinstalled in cloud sessions).
- `HA_URL`: the owner's Home Assistant, only when this session can reach it. Never store a token in the repo. Without
  it the live stage runs only its release-file checks.

The stages run side by side: 2-3 minutes with a warm firmware build, about 20 minutes on a fresh machine (the first
ESP-IDF compile). A broken stage shows as `<PREFIX>-RUN`: read `out/<stage>.log` and fix the harness when the fault is
the harness's, never by weakening a check.

## Stages

| Stage (prefix) | Runner | What it checks |
|---|---|---|
| `ci` (CI) | `ci/run.py` | The release tooling: signing and verification with a throwaway key, `signed_build.py`, `check_versions.py`, the privacy guard's own rules, the site, the workflow invariants (`ci.yml`, CodeQL, Dependabot) |
| `unit` (INT) | `integration/run.py` | `pytest` over `tests/` (the Home Assistant integration), one ID per test (`ids/unit.yaml`) |
| `device` (FW) | `firmware/run.py` | Config validation of every device file (plain and signed), host C++ tests of `components/magicband`, compiles with `--compile` |
| `page` (PAGE) | `page/run.js` | The MagicbHAnds page in Chromium with mock Home Assistant data: feature combinations, desktop/phone/dark, administrator and household member |
| `live` (LIVE) | `live/run.py` | Read-only checks of a running Home Assistant (versions, entities) and the published firmware signatures |
| `quality` (QUAL) | `quality/run.py` | An extra stage: lint (ruff), static security scan (bandit; hand-checked results in `quality/accepted.yaml`), dependency audit (pip-audit, npm advisories), JavaScript syntax, the harness's own tests |
| `manual` (FW-3xx, WALK-90x) | `manual.yaml` | What only a person with the hardware or the real Home Assistant frontend can check; keeps the IDs it had before the standard (new ones take MAN-) |
| `walkthrough` (WALK) | `walkthrough/run.py` | Every screen at desktop and phone, below |

Each writes `out/<stage>.json` (`{stage, prefix, results: [{id, key, feature, check, status, detail, evidence}]}`,
`key` = `"<ID> <check>"`); `out/ids.json` (IDS-0xx) says whether every ID is in the committed registry `ids/<stage>.yaml`.
IDs are append-only: a removed check is marked `RETIRED`, never deleted or reused. Reviewer findings go in
`out/findings/<reviewer>.json`. `out/` is git-ignored: results can name real devices.

**Safety:** nothing in the suite touches real hardware or changes Home Assistant; anything that would (taps, unlocks,
sounds, lights, restarts, installs) is a manual check with steps.

## Walkthrough

| Surface | Who | How |
|---|---|---|
| The MagicbHAnds page | an administrator (Morgan) and a household member (Jordan) | the real panel in Chromium with the mock `hass` from `page/`; every section from the jump menu (a chip row on a phone), closed and with every fold-out open |
| The web installer | anyone flashing a board | assembled by the real `make_site.py` from made-up firmware |
| Adding the integration, Configure | an administrator | crawled in a throwaway test Home Assistant (`flows_crawl.py`, needs `HA_PYTHON`) |
| Entity and Repairs names | everyone | `strings.json`, and the running Home Assistant's entity names (read-only) when `HA_URL` is reachable |
| Not crawled | | the devices (no screen; the setup hotspot is manual check FW-319); the real frontend and companion app (WALK-901/902) |

Widths: desktop 1280×900, phone 390×844 with touch emulation. Screenshots use a tall viewport, never Playwright's
full-page capture (it drops the touch emulation). UX check blocks: 1xx admin desktop, 2xx admin phone, 3xx member
desktop, 4xx member phone, 5xx/6xx installer desktop/phone, 7xx Home Assistant screens. The crawl writes
`walkthrough/out/` (inventory, shots); `run.py` publishes `out/walkthrough-checks.json`, `out/walkthrough.json` and
`out/walkthrough/` for the standard's skill.

## Catalogue (`catalogue/<area>.yaml`)

```yaml
- feature: Refused-tap lockout
  since: 0.10.26
  docs: docs/reader.md#refused-tap-lockout
  match: ['^[a-z]+:(FW-031|INT-044|PAGE-012) ']   # regexes searched over "<stage>:<key>"
  manual: [FW-302]
```

The report marks a feature **uncovered** if none of its checks ran and passed, and lists results no feature claims.
`claims.yaml` lists every security and privacy claim for the claims reviewer.

## Rules for checks

- Only made-up names and IDs in mock data and fixtures (Morgan, Casey, Alex, Jordan, Sam; Lakeview, Hillcrest).
- Live checks only read. Calibrate reviews to a home hobby project (CLAUDE.md, "What this is").
