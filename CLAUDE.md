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

## What this is, and how much security it needs

MagicbHAnds is a **home** MagicBand reader for a family's front door and a few Bluetooth bridges, not an access-control
system for a bank vault. Nobody is likely to target it to get into the house: a burglar breaks a window. Weigh every
protection against what it costs in convenience, and prefer the convenient option when the risk it guards is unlikely
or only an annoyance.

- **Must hold (the device must never be a way in for malicious code, "Patient Zero"):** no unsigned firmware installs
  on official builds; the encrypted device-to-Home Assistant link; admin-only actions for anything that changes who
  gets in; no injected script in the page; uploads and inputs validated; the signing key out of reach of anything but
  `main`; nothing private in the public repo.
- **Fine to accept and document instead of engineering around:** denial-of-service or nuisance by someone standing at
  the door or already on the Wi-Fi or in Home Assistant (household members), clutter in Home Assistant, races that need
  an insider plus the owner acting against a clear prompt, and anything that needs physical access to the electronics.
- **Before adding a protection** that adds a step, a prompt, a limit a family could hit, a USB-only path or new code in
  the update path, ask whether it stops a realistic attack on a home device. If not, don't add it, or ask the owner.
  Record accepted trade-offs in `docs/security.md` "Accepted risks".

## Regression suite

`regression/` is the full regression suite, run on demand with the `/regression` skill
(`.claude/skills/regression/SKILL.md`) every few releases or after a big feature set.
Quality commands: `/regression` (all stages + three-reviewer security audit), `/walkthrough` (every screen on desktop
and phone + two reviewers), `/full-check` (both, end to end).

- **Every PR that adds or changes a feature also updates the suite:** an entry in
  `regression/catalogue/<area>.yaml` and the checks that cover it (a test in `tests/`, a page check in
  `regression/page/`, a firmware host test or config invariant in `regression/firmware/`, a CI check in
  `regression/ci/`, a read-only check in `regression/live/`, or a manual check with steps where it needs hardware).
- Checks never touch real hardware or change Home Assistant; anything that would is a manual check.
- `regression/out/` is git-ignored (results can name real devices). `regression/RUNS.md` keeps one public-safe
  line per run.
