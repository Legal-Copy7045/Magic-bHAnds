# CLAUDE.md

## Privacy (this repository is public)

Never commit anything that identifies the owner, his family or his home, in files, commit messages, PR text or comments:
real names (use made-up ones: Morgan, Casey, Alex, Jordan, Sam), real towns, streets or addresses (use Lakeview, Hillcrest),
real coordinates (use made-up ones far from home), real NFC or Bluetooth band IDs, MAC addresses, VINs, entity or device IDs and
hostnames from the real Home Assistant, email addresses, Wi-Fi names, or credentials of any kind.

- Commit as `Legal-Copy7045 <323378128+Legal-Copy7045@users.noreply.github.com>`.
- The **Privacy guard** workflow (`.github/scripts/privacy_guard.py`) checks every push and pull request: no-reply commit
  addresses, no credentials, and nothing matching the private terms in the `PRIVACY_DENYLIST` Actions secret. If it fails,
  replace the value with a made-up one. Never put the real value back to make a test pass, and never print or copy the secret.

## Regression suite

`regression/` is the full regression suite, run on demand with the `/regression` skill
(`.claude/skills/regression/SKILL.md`) every few releases or after a big feature set.

- **Every PR that adds or changes a feature also updates the suite:** an entry in
  `regression/catalogue/<area>.yaml` and the checks that cover it (a test in `tests/`, a page check in
  `regression/page/`, a firmware host test or config invariant in `regression/firmware/`, a CI check in
  `regression/ci/`, a read-only check in `regression/live/`, or a manual check with steps where it needs hardware).
- Checks never touch real hardware or change Home Assistant; anything that would is a manual check.
- `regression/out/` is git-ignored (results can name real devices). `regression/RUNS.md` keeps one public-safe
  line per run.
