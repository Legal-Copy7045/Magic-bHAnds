#!/usr/bin/env python3
"""Build the walkthrough report from regression/walkthrough/out/.

  python3 regression/walkthrough/report.py

Inputs (all in regression/walkthrough/out/):
  walkthrough.json   the stage results (UX checks WALK-..., manual checks)
  inventory.json     menus, screens, fields and screenshots per surface, persona and width (run.py)
  findings.json      the two reviewers' findings, merged:
                     {"findings": [{id, group, title, now, proposal, who, effort, risk, width, evidence: [shot paths]}],
                      "menus": [{role, menu: [labels], why}]}
                     group: merge | rename | move | remove | flow | mobile | keep-separate; effort: S | M | L
  notes.json         optional {"summary": "...", "observations": ["..."]}
Writes out/report.html (self-contained: the evidence screenshots are embedded as small JPEGs, so it can be
published as a private artifact as it is) and out/report.md. Prints a one-line log entry for WALKTHROUGHS.md.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import io
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from report import CSS, bar, counts, pill, result_table  # noqa: E402 - the regression report's look

GROUPS = ["merge", "rename", "move", "remove", "flow", "mobile", "keep-separate"]
GROUP_TITLES = {"merge": "Merge", "rename": "Rename", "move": "Move", "remove": "Remove", "flow": "Flow",
                "mobile": "Mobile", "keep-separate": "Keep separate"}
e = html.escape
MAX_IMAGES = 40


def load(out: Path = OUT):
    def read(name, default):
        p = out / name
        try:
            return json.loads(p.read_text()) if p.is_file() else default
        except json.JSONDecodeError:
            return default
    stage = read("walkthrough.json", {"results": []})
    ids = read("ids.json", {"results": []})
    stage = {**stage, "results": stage.get("results", []) + ids.get("results", [])}
    inv = read("inventory.json", {"surfaces": []})
    found = read("findings.json", {})
    if isinstance(found, list):
        found = {"findings": found}
    notes = read("notes.json", {})
    findings = sorted(found.get("findings", []), key=lambda f: (GROUPS.index(f["group"]) if f.get("group") in GROUPS else 99,
                                                                  f.get("id", "")))
    return stage, inv, findings, found.get("menus", []), notes


def thumb(path: Path, width: int = 420) -> str | None:
    """A small embedded JPEG of a screenshot (the top 1400 px at most), or None without Pillow or the file."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return None
    if not path.is_file():
        return None
    im = Image.open(path).convert("RGB")
    im = im.crop((0, 0, im.width, min(im.height, int(im.width * 3.5))))
    im.thumbnail((width, 10_000))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=68, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def markdown(stage, inv, findings, menus, notes, when) -> str:
    res = stage.get("results", [])
    c = counts(res)
    out = ["# MagicbHAnds walkthrough", "", f"Run {when}.", ""]
    if notes.get("summary"):
        out += [notes["summary"], ""]
    out += [f"Checks: {c['pass']} pass, {c['fail']} fail, {c['manual']} manual, {c['skip']} skip.", ""]
    fails = [r for r in res if r.get("status") == "fail"]
    if fails:
        out += ["## Failing checks", ""] + [f"- **{r['id']}** {r['check']}: {r.get('detail', '')}" for r in fails] + [""]
    for g in GROUPS:
        items = [f for f in findings if f.get("group") == g]
        if not items:
            continue
        out += [f"## {GROUP_TITLES[g]}", ""]
        for f in items:
            out += [f"- **{f.get('id', '')}** {f.get('title', '')} ({f.get('width', 'both')}; effort {f.get('effort', '?')}, "
                    f"risk {f.get('risk', '?')})",
                    f"  - Now: {f.get('now', '')}", f"  - Proposal: {f.get('proposal', '')}", f"  - Affects: {f.get('who', '')}"]
        out.append("")
    if menus:
        out += ["## Proposed menus", ""] + [f"- **{m.get('role', '')}**: {' · '.join(m.get('menu', []))}" for m in menus] + [""]
    if notes.get("observations"):
        out += ["## Observations", ""] + [f"- {o}" for o in notes["observations"]] + [""]
    out += ["## Surfaces crawled", ""] + [f"- {s.get('surface')} — {s.get('persona')}, {s.get('width')}: "
                                         f"{len(s.get('screens', []))} screens, menu {len(s.get('menu', []))} entries"
                                         for s in inv.get("surfaces", [])]
    return "\n".join(out) + "\n"


def page(stage, inv, findings, menus, notes, when, out: Path = OUT) -> str:
    res = stage.get("results", [])
    c = counts(res)
    images = {"n": 0}

    def img(rel: str, alt: str) -> str:
        if images["n"] >= MAX_IMAGES:
            return ""
        src = thumb(out / rel)
        if not src:
            return ""
        images["n"] += 1
        return f'<figure style="margin:0"><img src="{src}" alt="{e(alt)}" loading="lazy" ' \
               f'style="max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px"></figure>'

    h = ["<title>MagicbHAnds Walkthrough</title>", '<meta name="claude:viewport-fit-sides" content="cover">',
         '<link rel="preconnect" href="https://fonts.googleapis.com">',
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700'
         '&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">',
         f"<style>{CSS}</style>", '<main class="wrap">']
    h.append('<header style="display:flex;flex-direction:column;gap:6px"><span class="eyebrow">Walkthrough · desktop and phone · '
             'page, installer, Home Assistant screens</span><h1>MagicbHAnds walkthrough</h1>'
             f'<span class="meta">Run {e(when)}</span>'
             + (f'<p class="lede">{e(notes["summary"])}</p>' if notes.get("summary") else "") + "</header>")
    groups = {g: sum(f.get("group") == g for f in findings) for g in GROUPS}
    h.append('<section aria-label="Totals"><div class="tally">'
             + "".join(f'<div class="tile {s}"><b>{c[s]}</b><span>{lab}</span></div>'
                       for s, lab in (("fail", "UX checks failing"), ("pass", "passing"), ("manual", "manual"), ("skip", "skipped")))
             + f'<div class="tile"><b>{len(findings)}</b><span>reviewer findings</span></div></div>{bar(c)}</section>')
    fails = [r for r in res if r.get("status") == "fail"]
    h.append("<section><h2>Automated UX checks that failed</h2>"
             + (result_table(fails) if fails else '<p class="empty">None.</p>') + "</section>")
    if findings:
        h.append("<section><h2>Findings</h2><p class=\"meta\">" + " · ".join(f"{GROUP_TITLES[g]} {n}" for g, n in groups.items() if n)
                 + "</p>")
        for g in GROUPS:
            items = [f for f in findings if f.get("group") == g]
            if not items:
                continue
            h.append(f"<h3>{e(GROUP_TITLES[g])}</h3>")
            for f in items:
                ev = "".join(img(p, f.get("title", "")) for p in (f.get("evidence") or [])[:2])
                h.append(f'<div class="finding low"><div class="head">{pill(f.get("effort", "?"))}'
                         f'<b>{e(f.get("id", ""))}</b><span>{e(f.get("title", ""))}</span>'
                         f'<span class="meta">{e(f.get("width", "both"))} · risk {e(str(f.get("risk", "?")))}</span></div>'
                         f'<p><span class="k">Now:</span> {e(f.get("now", ""))}</p>'
                         f'<p><span class="k">Proposal:</span> {e(f.get("proposal", ""))}</p>'
                         f'<p><span class="k">Affects:</span> {e(f.get("who", ""))}</p>{ev}</div>')
        h.append("</section>")
    else:
        h.append('<section><h2>Findings</h2><p class="empty">No reviewer findings yet (findings.json).</p></section>')
    if menus:
        rows = "".join(f"<tr><td>{e(m.get('role', ''))}</td><td>{e(' · '.join(m.get('menu', [])))}</td>"
                       f"<td class='d'>{e(m.get('why', ''))}</td></tr>" for m in menus)
        h.append(f'<section><h2>Proposed menus</h2><div class="tbl"><table><tr><th>Who</th><th>Menu</th><th>Why</th></tr>'
                 f"{rows}</table></div></section>")
    if notes.get("observations"):
        h.append('<section><h2>Observations</h2><ul class="plain">' + "".join(f"<li>{e(o)}</li>" for o in notes["observations"])
                 + "</ul></section>")
    # inventory: what was crawled
    inv_rows = "".join(
        f"<tr><td>{e(s.get('surface', ''))}</td><td>{e(s.get('persona', ''))}</td><td>{e(s.get('width', ''))}</td>"
        f"<td class='d'>{e(' · '.join(m.get('label', '') for m in s.get('menu', [])) or '—')}</td>"
        f"<td class='d'>{e(' · '.join(x.get('heading', '') for x in s.get('screens', [])))}</td></tr>"
        for s in inv.get("surfaces", []))
    ha = (inv.get("home_assistant") or {}).get("flows") or {}
    ha_rows = "".join(
        f"<tr><td>{e(str(x.get('opened_from') or x.get('note') or ''))}</td><td>{e(str(x.get('step_id') or x.get('reason') or ''))}</td>"
        f"<td>{e(str(x.get('title') or x.get('reason_text') or ''))}</td>"
        f"<td class='d'>{e(', '.join((f.get('label') or f['name']) for f in x.get('fields', [])) or ' · '.join((m.get('label') or m['option']) for m in x.get('menu', [])))}</td></tr>"
        for x in ha.get("screens", []))
    h.append('<section><h2>What was crawled</h2><details><summary>Menus and screens per surface, persona and width</summary>'
             f'<div class="tbl"><table><tr><th>Surface</th><th>Who</th><th>Width</th><th>Menu</th><th>Screens</th></tr>{inv_rows}'
             "</table></div></details>"
             + (f'<details><summary>Home Assistant screens (adding the integration, Configure)</summary><div class="tbl"><table>'
                f"<tr><th>Opened from</th><th>Step</th><th>Title</th><th>Fields or menu</th></tr>{ha_rows}</table></div></details>"
                if ha_rows else "")
             + "".join(f'<p class="meta">Not crawled: {e(n.get("surface", ""))} — {e(n.get("why", ""))}</p>'
                       for n in inv.get("not_crawled", []))
             + "</section>")
    allrows = sorted(res, key=lambda r: r.get("id", ""))
    h.append(f'<section><h2>Every check</h2><details><summary>All {len(allrows)} checks</summary>{result_table(allrows)}'
             "</details></section>")
    h.append("</main>")
    return "\n".join(h) + "\n"


def log_line(stage, findings, when, link: str = "") -> str:
    c = counts(stage.get("results", []))
    fails = [r["id"] for r in stage.get("results", []) if r.get("status") == "fail"]
    groups = {g: sum(f.get("group") == g for f in findings) for g in GROUPS}
    return (f"- {when}: {c['pass']} pass, {c['fail']} fail, {c['manual']} manual, {c['skip']} skip; failing "
            f"{', '.join(fails) or 'none'}; findings " + (", ".join(f"{g} {n}" for g, n in groups.items() if n) or "none")
            + (f"; report {link}" if link else ""))


def main() -> None:
    stage, inv, findings, menus, notes = load()
    tz = os.environ.get("REPORT_TZ")
    now = dt.datetime.now(ZoneInfo(tz)) if tz else dt.datetime.now().astimezone()
    when = now.strftime("%Y-%m-%d %H:%M %Z")
    (OUT / "report.md").write_text(markdown(stage, inv, findings, menus, notes, when))
    (OUT / "report.html").write_text(page(stage, inv, findings, menus, notes, when))
    size = (OUT / "report.html").stat().st_size
    print(f"walkthrough report: {counts(stage.get('results', []))}, {len(findings)} findings, {size // 1024} KB -> "
          f"{OUT / 'report.html'}")
    print("log line:", log_line(stage, findings, now.strftime("%Y-%m-%d")))


if __name__ == "__main__":
    main()
