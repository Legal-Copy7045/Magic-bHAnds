---
name: walkthrough
description: Independent walkthrough of every MagicbHAnds screen on desktop and phone (the MagicbHAnds page as an administrator and a household member, the web installer, the integration's Home Assistant setup and Configure screens, entity names), with automated UX checks and two fresh reviewers (desktop and phone), then a findings report. Use for "/walkthrough", a usability review, or "is this easy to use on a phone". Fixes nothing in product code. /full-check runs it together with /regression.
---

# Walkthrough of every screen, desktop and phone

The walkthrough is `regression/walkthrough/` (see `regression/README.md`). It
**fixes nothing in product code**: findings go in the report and the owner
decides. It writes only to `regression/walkthrough/out/` (git-ignored: it can
hold real entity names) and uses its own mock hosts and browser, so it can run
alongside the regression stages.

## What it covers, and what it can't

| Surface | Who | How |
|---|---|---|
| The MagicbHAnds page (Home Assistant sidebar panel) | an administrator (Morgan) and a household member (Jordan: Home Assistant refuses the admin-only services and the tap history) | the real panel in Chromium with the mock `hass` from `regression/page/`; every section reached from the jump menu (on a phone the same menu is a sideways-scrolling chip row: there's no separate phone menu), closed and with every fold-out open |
| The web installer (GitHub Pages) | anyone flashing a board | assembled here by the real `make_site.py` from made-up firmware files |
| Adding the integration, and Configure (options menu and every step) | an administrator | crawled in a throwaway test Home Assistant (`flows_crawl.py`, needs `HA_PYTHON`) |
| Entity and Repairs names | everyone | `strings.json`, and the running Home Assistant's MagicbHAnds entity names, read-only, when `HA_URL` is reachable |
| Not crawled: the devices | | no screen or web page of their own in official builds (the ring is output only); the setup hotspot is ESPHome's stock captive portal: manual check FW-319 |
| Not crawled: the real Home Assistant frontend and companion app | | needs a signed-in browser or phone: manual checks WALK-901/902 in `regression/manual.yaml` |

Widths: desktop 1280×900, phone 390×844 with touch emulation. Screenshots go
through a tall viewport, never Playwright's full-page capture (that drops the
touch emulation, and the phone styles with it).

## 1. Run the crawl

```
HA_PYTHON=... HA_URL=... python3 regression/run.py --stage walkthrough
```

About 30 seconds. It writes `out/walkthrough.json` (checks, IDs in
`regression/ids/walkthrough.yaml`), `out/inventory.json` (every surface,
persona and width: menu, screens with headings, buttons, fields and fold-outs,
the Home Assistant screens, entity names) and `out/shots/*.png`.

Automated UX checks (block per surface and width: 1xx admin desktop, 2xx admin
phone, 3xx member desktop, 4xx member phone, 5xx/6xx installer desktop/phone,
7xx Home Assistant screens): menu label matches the screen's heading (a chip may
be the heading's first words); no horizontal scroll; nothing off screen or
wider than its container; phone tap targets at least 40×40 px (hit-tested, so a
transparent touch area counts); no duplicate menu labels; no menu entry that
only redirects; no console or CSP errors; Configure menu labels match their
screens' titles; every field labelled; every abort and error has text; every
screen titled; every entity translation named; no two entities on a device
share a name; every Repairs notice titled. A failing check is data for the
reviewers, not something to "fix" in the harness unless the harness is wrong.

## 2. Two reviewers, in parallel

Launch two fresh subagents at once, in the background. Brief them with the code
and the evidence, **not** your conclusions: the inventory
(`regression/walkthrough/out/inventory.json`), the check results
(`out/walkthrough.json`), the screenshots (`out/shots/`; they can view images),
and the code (`custom_components/magicband/frontend/page.html`, `common.js`,
`style.css`, `config_flow.py`, `strings.json`, `web/index.html`). Each is told:
read-only; made-up names only in what they write (the inventory may hold real
entity names: never copy them into findings); every finding needs screenshot
evidence or a code reference; say who it affects and what it would cost; this is
a family's home tool, so prefer fewer, clearer screens over completeness.

- **Desktop reviewer**: duplicated or overlapping functions (the same action in
  the page and in Configure, or in two sections), confusing names, things in
  the wrong place, dead ends, long flows, and what must **stay separate and
  why** (e.g. admin-only actions, destructive ones).
- **Phone reviewer**: everything that's worse on a phone: layout, tap targets,
  the chip menu, long pages, forms, tables, fold-outs, what a household member
  sees that they can't use.

Each writes a JSON list of findings: `{id (D-n or P-n), group (merge | rename |
move | remove | flow | mobile | keep-separate), title, now, proposal, who,
effort (S|M|L), risk, width (desktop|phone|both), evidence: [paths under
out/, e.g. "shots/admin-phone-s-s-readers.png"]}` plus `menus: [{role, menu:
[labels], why}]`: the menu they'd propose for each role (administrator,
household member).

## 3. Report

- Merge both reviewers' output into `regression/walkthrough/out/findings.json`
  (`{"findings": [...], "menus": [...]}`; drop duplicates, keep the better
  evidence). Write `out/notes.json` (`summary`: three or four plain sentences;
  `observations`).
- `REPORT_TZ=America/New_York python3 regression/walkthrough/report.py` builds
  `out/report.html` (self-contained: evidence screenshots embedded small) and
  `out/report.md`, and prints the log line.
- Publish `out/report.html` as a private artifact **to the same URL every run**
  (the newest `regression/WALKTHROUGHS.md` entry has it: read it first, then
  publish with that `url`). Times in Eastern.
- Append the log line, with the link, to `regression/WALKTHROUGHS.md` (newest
  first). Public repository: no real names or IDs.
- Commit any harness changes and the log entry; PR as usual.
