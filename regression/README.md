# Full regression suite

An on-demand test of the whole system: run every few releases or after a big
feature set, not on every push (CI already runs the integration tests and the
firmware builds on every push). Start it with the `/regression` skill
(`.claude/skills/regression/SKILL.md`), which runs everything below, adds a
bug and vulnerability review, and writes the report.

**Every new feature adds to this suite** (see CLAUDE.md): a catalogue entry in
`catalogue/<area>.yaml` and, where it can be automated, a check in the matching
stage. A feature without an entry is a gap the report lists.

## Layout

| Path | Stage | What it checks |
|---|---|---|
| `catalogue/*.yaml` | — | Every feature and the checks that cover it (the source of truth for coverage) |
| `integration` (runner) | integration | `pytest` over `tests/` (Home Assistant integration), as JUnit |
| `page/` | page | The MagicbHAnds page in headless Chromium with mock Home Assistant data, across feature combinations, desktop/phone/dark |
| `firmware/` | firmware | Config validation of every device file (plain and signed), host C++ unit tests of `components/magicband` (ring dimming, shows, time zones, reader key), optional full compiles |
| `ci/` | ci | The release tooling: signing and verification with a throwaway key, `signed_build.py`, `check_versions.py`, the privacy guard's own rules, the BP2 consistency check |
| `live/` | live | Read-only checks against a running Home Assistant (versions, entities, published firmware signatures). Never changes anything. Needs `HA_URL` and a token or an authenticating proxy; skipped otherwise |
| `run.py` | — | Runs the stages and writes `out/<stage>.json` |
| `report.py` | — | Combines `out/*.json`, the catalogue and `out/findings.json` (the review) into `out/report.md` and `out/report.html` |

`out/` is git-ignored: results can name real devices.

## Result format (every stage)

Each stage writes `out/<stage>.json`:

```json
{
  "stage": "page",
  "started": "2026-11-24T03:00:00Z",
  "finished": "2026-11-24T03:04:10Z",
  "environment": {"note": "anything that affects the results"},
  "results": [
    {
      "id": "PAGE-012",
      "feature": "Refused-tap lockout",
      "check": "Locked-out reader shows the Locked out tag and End lockout now",
      "status": "pass",
      "detail": "optional: what was seen, why it failed or was skipped",
      "evidence": "optional: path under out/ (screenshot, log)"
    }
  ]
}
```

`status` is `pass`, `fail`, `skip` (could not run here, with the reason in
`detail`) or `manual` (needs a person and real hardware; the check says what to
do). IDs are stable: `INT-`, `PAGE-`, `FW-`, `CI-`, `LIVE-`, `MAN-` plus a
number. Never reuse an ID for a different check.

## Catalogue format (`catalogue/<area>.yaml`)

```yaml
- feature: Refused-tap lockout
  since: 0.10.26
  docs: docs/reader.md#refused-tap-lockout
  checks: [FW-031, INT-044, PAGE-012, MAN-007]
```

The report marks a feature **uncovered** if none of its checks ran and passed,
and lists any check ID with no result.

## Rules for checks

- Only made-up names and IDs in mock data and fixtures (Morgan, Casey, Alex,
  Jordan, Sam; Lakeview, Hillcrest). The repository is public.
- Live checks only read. Anything that would tap, unlock, sound, light or
  restart a device is a `manual` check with steps for a person.
