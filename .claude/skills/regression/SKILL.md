---
name: regression
description: Run the MagicbHAnds full regression suite (every stage in regression/), a fresh bug and security review, and publish the report. Use when asked to "run the full regression", "/regression", or for a release-health check after a big feature set. Not for ordinary changes (CI covers those).
---

# Full regression run

The suite lives in `regression/` (read `regression/README.md` first). A run has
five steps. Work through them in order; the owner usually reads the report the
next morning, so finish every step and leave nothing waiting on them.

## 1. Bring the suite up to date

Before running, check that every feature is catalogued:

- Read `CHANGELOG.md` from the version of the last report onward (the last
  report's version is in the newest "Regression" note in `regression/RUNS.md`).
- Every new feature, setting, service or page section needs an entry in
  `regression/catalogue/<area>.yaml` with at least one check that runs
  automatically where that is possible (a pytest in `tests/`, a page check in
  `regression/page/`, a host test or config invariant in `regression/firmware/`,
  a CI check in `regression/ci/`, a read-only live check in `regression/live/`)
  and a manual check (status `manual`, with steps) where it needs hardware.
- Add the missing entries and checks first, in their own commit.

## 2. Run the stages

Tools that the stages need (install what's missing; nothing global beyond pip):

- `HA_PYTHON`: a venv with `pytest-homeassistant-custom-component` and `fonttools`
  at the versions in `.github/workflows/firmware.yml` (test-integration job).
- `ESPHOME_PYTHON`: a venv with `esphome` at `ESPHOME_VERSION` from the same
  workflow (brings `esptool`/`espsecure`).
- Node and Playwright with Chromium (preinstalled in cloud sessions).
- `HA_URL`: the owner's Home Assistant, only if this session can reach it (a
  connected service listed for the session). Never ask for or store a token in
  the repo. Without it the live stage runs only its release-signature checks.

```
HA_PYTHON=... ESPHOME_PYTHON=... HA_URL=... python3 regression/run.py --compile
```

`--compile` builds every firmware (about 20 minutes). Run it unless the owner
said not to. Each stage writes `regression/out/<stage>.json`; a broken stage
shows as a failure, so read `out/<stage>.log` and fix the harness when the
fault is the harness's, never by weakening a check.

**Safety:** nothing in the suite touches real hardware or changes Home
Assistant. Don't add steps that do (taps, unlocks, sounds, lights, restarts,
installs): those are `manual` checks for the owner.

## 3. Review for bugs and vulnerabilities

Run two independent reviews of the whole repository in parallel (subagents),
each told: read-only, use made-up names only, never read the privacy denylist,
verify every finding by tracing the code end to end, drop what can't be
substantiated. Give them the areas below and point them at the previous run's
findings (`regression/RUNS.md`) so they check whether those were fixed.

- **Bugs** (`regression/out/findings-bugs.json`, IDs `BUG-`): firmware lambdas
  and scripts (state machines, timers and `millis()` wraparound, script modes,
  night/lockout/pairing/offline interplay, effect maths), the integration
  (registry edge cases, schedules across midnight and DST, sync failure paths,
  listeners and reloads, blocking I/O), the page (entity matching, redraw guard,
  arming timers, formatting).
- **Security** (`regression/out/findings-security.json`, IDs `SEC-`): service
  auth and input validation, HTTP views and uploads, signed URLs, event and
  notification injection, what a nearby attacker can do over NFC and Bluetooth,
  pairing keys and reader API actions, page XSS and the shim allowlist, firmware
  buffers and parsing, OTA and signed updates, the release pipeline (workflow
  injection, the signing secret and environment, pinned actions), and every
  claim in `docs/security.md` (held or not held).

Finding format: `{id, severity (critical|high|medium|low|info), area, title,
file, line, description, scenario, recommendation, verified}`.

## 4. Write the report

- Write `regression/out/notes.json`: `{"summary": "...", "observations": [...]}`.
  The summary is three or four plain sentences: overall health, what failed
  and matters most, what to do first. Observations are things worth knowing that
  aren't failures (coverage gaps, flaky areas, things only a person can check,
  changes since the last run).
- `REPORT_TZ=America/New_York python3 regression/report.py` builds
  `out/report.html` and `out/report.md`.
- Publish `out/report.html` as a private artifact (load the `artifact-design`
  skill first; the page already follows its contract) with a one-sentence
  description, and give the owner the link. Times in Eastern.
- Append a dated entry to `regression/RUNS.md`: version, totals, the IDs of
  failures and findings, and the report link. No real names, hosts or IDs: the
  repository is public.

## 5. Commit the suite changes

Commit any new checks and the `RUNS.md` entry on the working branch and open a
PR (normal rules: CI green, then merge). Fix nothing in product code as part of
the run; list fixes as recommendations, and do them only when the owner asks.

## Keeping the suite current between runs

CLAUDE.md requires every feature change to add its catalogue entry and checks
in the same PR, so a run should find few gaps. When a run does find a feature
without coverage, add it (step 1) and mention it under Observations.
