# CLAUDE.md

## Privacy (this repository is public)

Never commit anything that identifies the owner, his family or his home, in files, commit messages, PR text or comments:
real names (use made-up ones: Morgan, Casey, Alex, Jordan, Sam), real towns, streets or addresses (use Lakeview, Hillcrest),
real coordinates (use made-up ones far from home), real NFC or Bluetooth band IDs, MAC addresses, VINs, entity or device IDs and
hostnames from the real Home Assistant, email addresses, Wi-Fi names, or credentials of any kind.

- Commit as `Legal-Copy7045 <323378128+Legal-Copy7045@users.noreply.github.com>`.
- The **privacy guard** (`.github/scripts/privacy_guard.py`, loaded from `main`) checks every pull request and push to
  `main`: no-reply commit addresses, no credentials, and (on `main` only) nothing matching the private terms in the
  `PRIVACY_DENYLIST` secret of the `privacy` environment. Run it locally with the terms before pushing. If it fails,
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

## CI and releases (this project's differences from the owner's defaults)

- Standard 1.1.0 (`.github/standard.yaml`: what's `beyond:` and the `exceptions:`). One workflow, `ci.yml`;
  `ci-result` is the required check. A push to `main` runs the private-terms check and, when `VERSION` has no tag
  yet, the release: build, sign (the key is only reachable from `main`), attest, installer site, GitHub Release.
- `VERSION` changes only for a release (every bump ships firmware to the devices), so merges that change only
  CI, docs or the regression suite don't bump it.

## Regression suite

`regression/` is the full suite (`regression/README.md`, `profile.yaml`), run on demand with the global
`/regression`, `/walkthrough` and `/full-check` skills every few releases or after a big feature set.
`python3 regression/run.py check` (ci, unit, quality) must pass before a PR is marked ready.

- **Every PR that adds or changes a feature also updates the suite:** an entry in
  `regression/catalogue/<area>.yaml` and the checks that cover it (a test in `tests/`, a page check in
  `regression/page/`, a firmware host test or config invariant in `regression/firmware/` (device stage), a CI check in
  `regression/ci/`, a read-only check in `regression/live/`, or a manual check with steps where it needs hardware).
- Checks never touch real hardware or change Home Assistant; anything that would is a manual check.
- `regression/out/` is git-ignored (results can name real devices). `regression/RUNS.md` keeps one public-safe
  line per run.
