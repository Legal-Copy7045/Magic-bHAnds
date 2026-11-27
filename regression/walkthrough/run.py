#!/usr/bin/env python3
"""Walkthrough stage: every user-facing screen, on desktop and phone -> regression/walkthrough/out/.

  python3 regression/walkthrough/run.py          (or: python3 regression/run.py --stage walkthrough)

What it covers (each surface the product has; the ones it doesn't have are listed in the inventory as such):
  * the MagicbHAnds page (the Home Assistant sidebar panel), as an administrator and as a household member, at
    desktop 1280×900 and phone 390×844 with touch: crawl.js (real panel, mock Home Assistant, Chromium);
  * the web installer (the GitHub Pages site), assembled here from made-up firmware files: crawl.js;
  * the integration's own Home Assistant screens: adding it (config flow) and Configure (the options menu and
    every step it opens), crawled in a throwaway test Home Assistant (flows_crawl.py, with HA_PYTHON), and the
    names of its entities and Repairs notices from strings.json;
  * read-only: the entity names of the running Home Assistant at HA_URL, if reachable (nothing is changed).
  * Not crawled, with the reason in the inventory: the devices (no screen or web page of their own in official
    builds; the setup hotspot is ESPHome's stock page, a manual check), and the real Home Assistant frontend and
    companion app (manual checks WALK-9xx in regression/manual.yaml).

Writes out/walkthrough.json (stage results, IDs WALK-...), out/inventory.json (menus, screens, fields,
screenshots) and out/shots/*.png. Its own output directory, mock hosts and browser, so it can run alongside the
regression stages. Changes nothing anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "out"
MB = REPO / "custom_components" / "magicband"
F_HA = "Walkthrough: Home Assistant screens (adding the integration, Configure, entities, Repairs)"


def log(msg: str) -> None:
    print(msg, flush=True)


def build_site() -> Path | None:
    """The web installer, assembled by the real make_site.py from made-up firmware files (no real firmware)."""
    site, builds = OUT / "site", OUT / ".site-builds"
    shutil.rmtree(site, ignore_errors=True)
    specs = []
    for product, slug, yaml_name in (("bridge", "magicband-bridge", "magicband-bridge.yaml"),
                                     ("reader", "magicband-reader", "magicband-reader.yaml"),
                                     ("bp2", "screek-bp2-poe", "screek-bp2-poe.yaml")):
        d = builds / slug
        d.mkdir(parents=True, exist_ok=True)
        rnd = hashlib.sha256(slug.encode()).digest()
        app = b"\xe9" + (rnd * 4096)[: 0x30000 - 1]
        (d / "firmware.ota.bin").write_bytes(app)
        (d / "firmware.factory.bin").write_bytes(b"\xe9".ljust(0x10000, b"\xff") + app)
        specs.append(f"{product}={d}={REPO / 'esphome' / yaml_name}")
    proc = subprocess.run([sys.executable, str(REPO / ".github" / "scripts" / "make_site.py"), str(site), *specs],
                          capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0 or not (site / "index.html").is_file():
        log(f"installer site not assembled: {(proc.stderr or proc.stdout)[-600:]}")
        return None
    return site


def crawl_browser(site: Path | None) -> dict:
    cmd = ["node", str(HERE / "crawl.js"), str(OUT)] + ([str(site)] if site else [])
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=1800, check=False)
    log(proc.stdout[-1500:] + proc.stderr[-1500:])
    p = OUT / "crawl.json"
    if proc.returncode != 0 or not p.is_file():
        raise RuntimeError(f"crawl.js failed (exit {proc.returncode}): {proc.stderr[-800:]}")
    return json.loads(p.read_text())


def crawl_flows() -> dict | None:
    py = os.environ.get("HA_PYTHON") or sys.executable
    if subprocess.run([py, "-c", "import pytest_homeassistant_custom_component"], capture_output=True,
                      check=False).returncode != 0:
        log(f"no pytest-homeassistant-custom-component in {py}: Home Assistant screens not crawled (set HA_PYTHON)")
        return None
    dest = OUT / "flows.json"
    dest.unlink(missing_ok=True)
    proc = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(HERE / "flows_crawl.py")],
                          cwd=REPO, capture_output=True, text=True, timeout=600, check=False,
                          env={**os.environ, "WALK_FLOWS_OUT": str(dest)})
    log(proc.stdout[-1200:])
    if proc.returncode != 0 or not dest.is_file():
        raise RuntimeError(f"flows_crawl.py failed: {(proc.stdout + proc.stderr)[-1500:]}")
    return json.loads(dest.read_text())


def live_entities() -> list[dict] | None:
    """Read-only: MagicbHAnds' entities and their names on the running Home Assistant (HA_URL)."""
    url = os.environ.get("HA_URL")
    if not url:
        return None
    tpl = ("[{% for e in integration_entities('magicband') %}{\"entity_id\": {{ e | to_json }}, \"name\": "
           "{{ (state_attr(e, 'friendly_name') or '') | to_json }}, \"device\": {{ (device_attr(device_id(e), "
           "'name_by_user') or device_attr(device_id(e), 'name') or '') | to_json }}}{{ ',' if not loop.last }}"
           "{% endfor %}]")
    headers = {"Content-Type": "application/json"}
    if os.environ.get("HA_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["HA_TOKEN"]
    req = urllib.request.Request(url.rstrip("/") + "/api/template", data=json.dumps({"template": tpl}).encode(),
                                 headers=headers, method="POST")  # a template render: reads, changes nothing
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - the owner's HA_URL
            return json.loads(resp.read())
    except Exception as err:  # noqa: BLE001
        log(f"live entities not read: {err}")
        return None


def translation_keys() -> dict[str, set[str]]:
    """Entity translation keys the integration's code uses, per platform file."""
    keys: dict[str, set[str]] = {}
    for py in MB.glob("*.py"):
        for m in re.finditer(r"translation_key\s*=\s*\"([a-z0-9_]+)\"", py.read_text()):
            keys.setdefault(py.stem, set()).add(m.group(1))
    return keys


def ha_checks(flows: dict | None, live: list[dict] | None) -> list[dict]:
    res: list[dict] = []

    def add(n: int, check: str, ok: bool | None, detail: str = "") -> None:
        res.append({"id": f"WALK-{700 + n}", "feature": F_HA, "check": check,
                    "status": "skip" if ok is None else "pass" if ok else "fail", "detail": detail})

    screens = (flows or {}).get("screens", [])
    none = "the Home Assistant screens weren't crawled (no HA_PYTHON with pytest-homeassistant-custom-component)"
    menu = next((s for s in screens if s.get("type", "").endswith("MENU") or s.get("menu")), None)
    if flows is None:
        for n, c in ((1, "Configure: every menu label matches the title of the screen it opens"),
                     (2, "Every field on every screen has a label in strings.json"),
                     (3, "Every abort and error the screens produced has text in strings.json"),
                     (4, "Configure: no two menu entries have the same label"),
                     (5, "Every form and menu screen has a title")):
            add(n, c, None, none)
    else:
        opened = {s.get("opened_from"): s for s in screens if s.get("opened_from") and "→" not in s["opened_from"]}
        mism = []
        for m in (menu or {}).get("menu", []):
            s = opened.get(m["option"])
            if s and s.get("title") and s["title"].strip().lower() != (m.get("label") or "").strip().lower():
                mism.append(f"\"{m.get('label')}\" opens \"{s['title']}\"")
        add(1, "Configure: every menu label matches the title of the screen it opens", not mism,
            "; ".join(mism) or f"{len((menu or {}).get('menu', []))} entries")
        unlabelled = [f"{s['flow']}/{s['step_id']}: {f['name']}" for s in screens for f in s.get("fields", [])
                      if not f.get("label")]
        add(2, "Every field on every screen has a label in strings.json", not unlabelled, "; ".join(unlabelled))
        mute = [f"{s['flow']} abort {s['reason']}" for s in screens if s.get("reason") and not s.get("reason_text")]
        mute += [f"{s['flow']}/{s['step_id']} error {k}" for s in screens for k, v in (s.get("error_texts") or {}).items()
                 if not v]
        add(3, "Every abort and error the screens produced has text in strings.json", not mute, "; ".join(mute))
        labels = [(m.get("label") or "").strip().lower() for m in (menu or {}).get("menu", [])]
        dup = sorted({x for x in labels if labels.count(x) > 1})
        add(4, "Configure: no two menu entries have the same label", not dup, ", ".join(dup))
        untitled = [f"{s['flow']}/{s['step_id']}" for s in screens
                    if s.get("step_id") and s.get("type", "").split(".")[-1].lower() in ("form", "menu") and not s.get("title")]
        add(5, "Every form and menu screen has a title", not untitled, ", ".join(untitled))
    tr = json.loads((MB / "strings.json").read_text())
    named = {(p, k) for p, d in tr.get("entity", {}).items() for k, v in d.items() if (v or {}).get("name")}
    issue_keys = set(tr.get("issues", {}))  # Repairs notices use translation_key too (checked by WALK-708)
    missing = sorted(f"{plat}.{k}" for plat, ks in translation_keys().items() for k in ks
                     if k not in issue_keys and not any((p, k) in named for p in (plat, "sensor", "binary_sensor", "select")))
    add(6, "Every entity translation key the code uses has a name in strings.json", not missing, ", ".join(missing))
    if live is None:
        add(7, "On the running Home Assistant, no two MagicbHAnds entities on the same device share a name", None,
            "HA_URL not set or not reachable (read-only check)")
    else:
        seen: dict[tuple, int] = {}
        for e in live:
            k = (e.get("device") or "", (e.get("name") or "").strip().lower())
            seen[k] = seen.get(k, 0) + 1
        dups = sorted(f"{d or '(no device)'}: {n}" for (d, n), c in seen.items() if c > 1 and n)
        add(7, "On the running Home Assistant, no two MagicbHAnds entities on the same device share a name", not dups,
            "; ".join(dups) or f"{len(live)} entities")
    issues = [k for k, v in tr.get("issues", {}).items() if not (v or {}).get("title")]
    add(8, "Every Repairs notice the integration can raise has a title", not issues, ", ".join(issues))
    return res


def main() -> int:
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(OUT / "shots", ignore_errors=True)
    site = build_site()
    crawl = crawl_browser(site)
    flows_err = None
    try:
        flows = crawl_flows()
    except Exception as err:  # noqa: BLE001 - reported as the HA checks' failure
        flows, flows_err = None, str(err)
    live = live_entities()
    results = crawl["results"] + ha_checks(flows, live)  # its manual checks are the manual stage's
    if flows_err:
        results.append({"id": "WALK-RUN", "feature": "Regression harness", "check": "The Home Assistant screens crawl runs",
                        "status": "fail", "detail": flows_err[-1500:]})
    inventory = crawl["inventory"]
    inventory["home_assistant"] = {
        "flows": flows, "live_entities": live,
        "note": "Adding the integration and its Configure screens, crawled in a throwaway test Home Assistant; "
                "entity names from the running Home Assistant (read-only) when HA_URL is set.",
    }
    inventory["not_crawled"] = [
        {"surface": "Bridges, readers and the BP2-POE", "why": "No screen or web page of their own in official builds; "
         "the ring is output only. The Wi-Fi setup hotspot is ESPHome's stock captive portal (manual check FW-319)."},
        {"surface": "The real Home Assistant frontend and companion app",
         "why": "Needs a signed-in browser or phone: manual checks WALK-9xx in regression/manual.yaml."},
    ]
    (OUT / "inventory.json").write_text(json.dumps(inventory, indent=1, default=str) + "\n")
    counts = {s: sum(r["status"] == s for r in results) for s in ("pass", "fail", "skip", "manual")}
    stage = {"stage": "walkthrough", "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "environment": {"note": "Chromium via Playwright; mock Home Assistant for the page; installer site from "
                                     "made-up firmware; Home Assistant screens in a test instance; live entity names "
                                     "read-only", "counts": counts, "installer_site": bool(site),
                             "ha_screens": flows is not None, "live": live is not None},
             "results": results}
    (OUT / "walkthrough.json").write_text(json.dumps(stage, indent=2) + "\n")
    log(f"walkthrough: {counts} -> {OUT / 'walkthrough.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
