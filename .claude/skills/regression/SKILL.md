---
name: regression
description: Run the MagicbHAnds full regression (every stage in regression/: integration, CI tooling, firmware, page, live, code quality and supply chain), a security audit by three independent reviewers, and publish the report. Use when asked to "run the full regression", "/regression", or for a release-health check after a big feature set. Not for ordinary changes (CI covers those). /full-check runs this together with /walkthrough.
---

# Full regression run

The suite lives in `regression/` (read `regression/README.md` first). A run has
five steps; the owner usually reads the report the next morning, so finish
every step and leave nothing waiting on them. **A regression run fixes nothing
in product code**: failures and findings go in the report, and the owner
decides (see "Fixing findings" at the end).

**Keep it quick.** The reviews (step 3) don't depend on the stages (step 2):
start the three reviewers in the background as soon as step 1 is committed,
and run the stages while they work. Install missing tool venvs in the
background at the very start. The stages run side by side (`run.py`), so the
checks take as long as the slowest one: 2-3 minutes with a warm firmware build,
about 20 minutes on a fresh machine (the first ESP-IDF compile).

Arguments: `/regression` is a normal run (bug review scoped to what changed);
`/regression full` reviews the whole repository. `/full-check` always uses the
full review.

## 1. Bring the suite up to date

- Read `CHANGELOG.md` from the version of the newest `regression/RUNS.md` entry
  onward. Every new feature, setting, service or page section needs an entry in
  `regression/catalogue/<area>.yaml` (`checks:` lists IDs; `match:` lists
  regexes over `<stage>:<ID>`) with at least one automatic check where one is
  possible (a pytest in `tests/`, a page check in `regression/page/`, a host
  test or config invariant in `regression/firmware/`, a CI check in
  `regression/ci/`, a read-only check in `regression/live/`, a quality check in
  `regression/quality/`) and a manual check in `regression/manual.yaml` where it
  needs hardware or the real Home Assistant frontend.
- Add the missing entries and checks first, in their own commit.

## 2. Run the stages

Tools (install what's missing; nothing global beyond pip):

- `HA_PYTHON`: a venv with `pytest-homeassistant-custom-component` and
  `fonttools` at the versions in `.github/workflows/firmware.yml`.
- `ESPHOME_PYTHON`: a venv with `esphome` at `ESPHOME_VERSION` from the same
  workflow (brings `esptool`/`espsecure`).
- `QUALITY_PYTHON` (optional): ruff, bandit, pip-audit, pytest at the pins in
  `regression/quality/run.py`; the stage installs them into
  `regression/out/.venv-quality` itself otherwise.
- Node and Playwright with Chromium (preinstalled in cloud sessions).
- `HA_URL`: the owner's Home Assistant, only if this session can reach it (a
  connected service listed for the session). Never ask for or store a token in
  the repo. Without it the live stage runs only its release-file checks.

```
HA_PYTHON=... ESPHOME_PYTHON=... HA_URL=... python3 regression/run.py --compile
python3 regression/run.py --stage quality      # one stage (repeat --stage for more)
```

The stages: **integration** (pytest), **ci** (release tooling with a throwaway
key), **firmware** (config, host tests, compiles with `--compile`, manual list),
**page** (the page in Chromium with mock data), **live** (read-only against
`HA_URL` and the published release), **quality** (lint, static security scan,
dependency audit, JavaScript syntax, the harness's own tests). Each writes
`regression/out/<stage>.json`; afterwards `out/ids.json` says whether every
check ID is in the committed registry (`regression/ids/`, see `ids.py`). A new
check gets a new ID: run `python3 regression/ids.py sync <stage>` and commit the
registry; a removed check is marked `RETIRED`, never deleted or reused.

A broken stage shows as a failure: read `out/<stage>.log` and fix the harness
when the fault is the harness's, never by weakening a check. **Safety:** nothing
in the suite touches real hardware or changes Home Assistant; anything that
would (taps, unlocks, sounds, lights, restarts, installs) is a manual check.

## 3. Security audit and bug review (three reviewers, in parallel)

Launch three fresh subagents at once, in the background, while the stages run.
Brief each like a peer who knows nothing: the goal, the files to read, the
output file and format. Give them the code to read, **not** your conclusions.
Each is told: read-only; made-up names only (Morgan, Casey, Alex, Jordan, Sam;
Lakeview, Hillcrest); never read the privacy denylist or any secret; verify
every finding by tracing the code end to end and mark `verified`; drop what
can't be substantiated; first read the **Accepted risks** in
`docs/security.md` and don't report one again unless its description is wrong
or its limits no longer hold; check whether the previous run's findings
(newest `regression/RUNS.md` entry) are fixed.

**Calibrate to a home hobby project** (CLAUDE.md, "What this is, and how much
security it needs"): rate severity by what a realistic attacker could do to a
family home, not by theoretical reach. A way to put code on a device, read
private data or let someone in is serious; nuisance, clutter, a denial of
service by someone at the door or by household members, or a race that needs an
insider and the owner ignoring a prompt is low or info, and the recommendation
is usually "document it". Every recommendation says what it would cost in
convenience; none recommends a protection whose cost outweighs a home-scale
risk.

- **(a) Bugs** → `regression/out/findings-bugs.json`, IDs `BUG-`. Scope: what
  changed since the last run (`git diff v<last>..HEAD`, plus the code it calls
  into) **and** the risky paths every time: firmware state machines, timers and
  `millis()` wraparound, night/lockout/pairing/offline interplay; the
  integration's registry edge cases, schedules across midnight and DST, sync
  failure paths, listeners and reloads, blocking I/O; the page's entity
  matching, redraw guard and arming timers. A full review (`/regression full`,
  `/full-check`, no full review in the last three runs, or a first run) covers
  the whole repository.
- **(b) Security claims** → `regression/out/findings-security.json`, IDs `SEC-`,
  plus `claims: [{claim, holds, note}]`: every claim `docs/security.md` (and the
  security notes in README and docs/) makes, each checked against the code and
  the workflow, held or not held.
- **(c) Outsider attack** → `regression/out/findings-attack.json`, IDs `ATK-`:
  the new code and the build/deployment surface attacked as an outsider would:
  someone at the door with NFC tags, someone in Bluetooth range, someone on the
  Wi-Fi or joining the setup hotspot, a malicious pull request or fork, a
  tampered download or update site, a poisoned dependency or cache, the HTTP
  views and uploads, page XSS through names or band data, workflow injection,
  and the signing secret's reach. Each with the concrete steps it would take.

Finding format (all three): `{id, severity (critical|high|medium|low|info),
area, title, file, line, description, scenario, recommendation, verified}`.

## 4. Write the report

- `regression/out/notes.json`: `{"summary": "...", "observations": [...]}`. The
  summary is three or four plain sentences: overall health, what failed and
  matters most, what to do first. Observations: coverage gaps, flaky areas,
  things only a person can check, changes since the last run, how long the run
  took.
- `REPORT_TZ=America/New_York python3 regression/report.py` builds
  `out/report.html` and `out/report.md`.
- Publish `out/report.html` as a private artifact (load the `artifact-design`
  skill first; the page already follows its contract) **to the same URL every
  run**: the URL is in the newest `RUNS.md` entry; read it first, then publish
  with that `url`. Give the owner the link. Times in Eastern.
- Append a dated entry to `regression/RUNS.md` (newest first): date, version and
  commit, review scope, totals, failing IDs, finding IDs by severity, duration,
  report link. No real names, hosts or IDs: the repository is public.

## 5. Commit the suite changes

Commit new checks, registry entries and the `RUNS.md` entry on the working
branch and open a PR (normal rules: CI green, then merge).

## Fixing findings (only when the owner asks)

Fix, release and install as usual, then re-run only the stages the fixes touch
(`python3 regression/run.py --stage integration --stage page`, `--stage live`
after the install) and have one reviewer confirm each fixed finding is gone,
rather than repeating the whole audit. Do a final full set of stages before a
clean report.

## Keeping the suite current between runs

CLAUDE.md requires every feature change to add its catalogue entry and checks
in the same PR, so a run should find few gaps. When a run does find a feature
without coverage, add it (step 1) and mention it under Observations.
