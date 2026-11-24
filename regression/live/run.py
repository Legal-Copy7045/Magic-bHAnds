#!/usr/bin/env python3
"""Live stage: read-only checks against a running Home Assistant and the published firmware.

Usage: HA_URL=https://homeassistant.local:8123 [HA_TOKEN=...] python3 regression/live/run.py

Reads only: GET requests and Home Assistant's template API, which evaluates a
template and changes nothing. It never calls a service, presses a button or
installs anything. Without HA_URL the Home Assistant checks are skipped; the
release signature checks still run. HA_TOKEN is a long-lived token for a
non-admin user, or leave it unset where a proxy adds the credentials.

Writes regression/out/live.json (IDs LIVE-...). The results name real devices,
so they stay in out/ (git-ignored).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "regression" / "out"
VERSION = (ROOT / "VERSION").read_text().strip()
PUB = ROOT / "esphome" / "firmware-signing-key.pub.pem"
RELEASES = "https://github.com/Legal-Copy7045/Magic-bHAnds/releases/download"
SITE = "https://legal-copy7045.github.io/Magic-bHAnds"
PRODUCTS = {  # release file prefix, site sub-path, Home Assistant device model
    "magicband-bridge": ("", "magicband-bridge"),
    "magicband-reader": ("reader/", "magicband-reader"),
    "screek-bp2-poe": ("bp2/", "magicband-bp2-poe"),
}
# Entities each device's firmware should have from the version they arrived in (original names).
EXPECTED = {
    "magicband-reader": ["Firmware", "Automatic updates", "Time zone", "Idle style", "Idle style at night",
                         "Idle circle time", "Idle circle tail", "Idle circle heads", "Idle tail fade",
                         "Idle circle direction", "Sound at night", "Night volume", "Refused-tap lockout",
                         "Lockout after", "Lockout window", "Lockout time", "Tap lockout",
                         "Paired with MagicbHAnds", "Band light-up power"],
    "magicband-bridge": ["Firmware", "Automatic updates", "Time zone", "Fast mode"],
    "magicband-bp2-poe": ["Firmware", "Automatic updates", "Time zone"],
}
TIME_ZONES = ["Eastern (New York)", "Central (Chicago)", "Mountain (Denver)", "Arizona (Phoenix)",
              "Pacific (Los Angeles)", "Alaska (Anchorage)", "Hawaii (Honolulu)", "UK (London)",
              "Central Europe (Paris)", "UTC"]

results: list[dict] = []


def add(rid: str, feature: str, check: str, status: str, detail: str = "") -> None:
    results.append({"id": rid, "feature": feature, "check": check, "status": status, "detail": detail})


def curl(url: str, *, data: str | None = None, out: Path | None = None, auth: bool = False) -> tuple[int, str]:
    cmd = ["curl", "-sS", "-L", "-m", "120", "-w", "\n%{http_code}"]
    if auth and os.environ.get("HA_TOKEN"):
        cmd += ["-H", f"Authorization: Bearer {os.environ['HA_TOKEN']}"]
    if data is not None:
        cmd += ["-X", "POST", "-H", "Content-Type: application/json", "--data-binary", data]
    if out is not None:
        cmd += ["-o", str(out)]
    p = subprocess.run(cmd + [url], capture_output=True, text=True, check=False)
    body, _, code = p.stdout.rpartition("\n")
    try:
        return int(code), body
    except ValueError:
        return 0, p.stderr.strip()


DEVICES_TEMPLATE = """
{%- set ns = namespace(out=[], seen=[]) -%}
{%- for e in integration_entities('esphome') -%}
  {%- set d = device_id(e) -%}
  {%- if d and d not in ns.seen and (device_attr(d, 'model') or '') in MODELS -%}
    {%- set ns.seen = ns.seen + [d] -%}
    {%- set dn = device_attr(d, 'name_by_user') or device_attr(d, 'name') -%}
    {%- set ents = namespace(x=[]) -%}
    {%- for x in device_entities(d) -%}
      {%- set s = states[x] -%}
      {%- if s -%}
        {%- set ents.x = ents.x + [[s.name | replace(dn, '') | trim, s.state, s.attributes.get('options'),
              s.attributes.get('installed_version'), s.attributes.get('latest_version')]] -%}
      {%- endif -%}
    {%- endfor -%}
    {%- set ns.out = ns.out + [{'name': dn, 'model': device_attr(d, 'model'), 'sw': device_attr(d, 'sw_version'),
          'entities': ents.x}] -%}
  {%- endif -%}
{%- endfor -%}
{{ ns.out | tojson }}
"""


def ha_checks(ha: str) -> None:
    code, _ = curl(f"{ha}/api/", auth=True)
    if code != 200:
        add("LIVE-001", "Home Assistant", "API reachable (read-only)", "fail", f"HTTP {code}")
        return
    add("LIVE-001", "Home Assistant", "API reachable (read-only)", "pass")

    code, body = curl(f"{ha}/api/states/update.magicband", auth=True)
    if code == 200:
        a = json.loads(body)["attributes"]
        ok = a.get("installed_version") == f"v{VERSION}"
        add("LIVE-002", "Integration", f"HACS integration installed at v{VERSION}",
            "pass" if ok else "fail", f"installed {a.get('installed_version')}, latest {a.get('latest_version')}")
    else:
        add("LIVE-002", "Integration", "HACS integration update entity found", "skip",
            "no update.magicband (not installed through HACS?)")

    tpl = DEVICES_TEMPLATE.replace("MODELS", json.dumps(sorted(m for _, m in PRODUCTS.values())))
    code, body = curl(f"{ha}/api/template", data=json.dumps({"template": tpl}), auth=True)
    try:
        devices = json.loads(body) if code == 200 else []
    except json.JSONDecodeError:
        devices = []
    if not devices:
        add("LIVE-003", "Devices", "MagicbHAnds devices found in Home Assistant", "fail", f"HTTP {code}")
        return
    add("LIVE-003", "Devices", "MagicbHAnds devices found in Home Assistant", "pass",
        ", ".join(f"{d['model']}" for d in devices))
    n = 10
    for d in devices:
        ents, builder = {}, []
        for e in d["entities"]:
            item = {"state": e[1], "attributes": {"options": e[2], "installed_version": e[3], "latest_version": e[4]}}
            # Two update entities can share the name "Firmware": the firmware's own (project versions,
            # 0.x.y) and the ESPHome Device Builder's (ESPHome versions, 20xx.y.z) when the device is
            # also adopted there. Keep ours as "Firmware" and note the other.
            if e[0] == "Firmware" and str(e[3] or "").startswith("20"):
                builder.append(item)
                continue
            ents[e[0]] = item
        # Results name the device by model and index, not by its name in this home.
        tag, model = f"{d['model']} #{sum(x['model'] == d['model'] for x in devices[:devices.index(d) + 1])}", d["model"]
        sw = (d.get("sw") or "").split(" ")[0]
        add(f"LIVE-{n:03d}", "Signed updates", f"{tag}: running {VERSION}", "pass" if sw == VERSION else "fail",
            f"device reports {d.get('sw')}")
        online = [k for k, v in ents.items() if v["state"] not in ("unavailable", "unknown")]
        add(f"LIVE-{n + 1:03d}", "Devices", f"{tag}: online (entities reporting)", "pass" if online else "fail",
            f"{len(online)} of {len(ents)} entities have a state")
        missing = [e for e in EXPECTED.get(model, []) if e not in ents]
        add(f"LIVE-{n + 2:03d}", "Firmware entities", f"{tag}: has every entity its firmware should",
            "pass" if not missing else "fail", "missing: " + ", ".join(missing) if missing else f"{len(ents)} entities")
        tz = ents.get("Time zone")
        if tz:
            opts = tz["attributes"].get("options") or []
            ok = opts == TIME_ZONES and tz["state"] in TIME_ZONES
            add(f"LIVE-{n + 3:03d}", "Time zone", f"{tag}: Time zone options match the firmware's table",
                "pass" if ok else "fail", f"state {tz['state']}")
        au = ents.get("Automatic updates")
        if au:
            add(f"LIVE-{n + 4:03d}", "Automatic updates", f"{tag}: Automatic updates switch reports a state",
                "pass" if au["state"] in ("on", "off") else "fail", f"state {au['state']}")
        fw = ents.get("Firmware")
        if fw:
            a = fw["attributes"]
            add(f"LIVE-{n + 5:03d}", "Signed updates", f"{tag}: update entity sees the published release",
                "pass" if a.get("latest_version") == VERSION else "fail",
                f"installed {a.get('installed_version')}, latest {a.get('latest_version')}")
        if builder:
            b = builder[0]["attributes"]
            add(f"LIVE-{n + 8:03d}", "Signed updates",
                f"{tag}: no ESPHome Device Builder update competing with the signed releases",
                "fail" if b.get("latest_version") != b.get("installed_version") else "pass",
                f"the Device Builder also offers ESPHome {b.get('latest_version')} (installed "
                f"{b.get('installed_version')}). Its builds are unsigned, so the device refuses them over the "
                "air; update through the Firmware entity, or remove the device from the Device Builder")
        if model == "magicband-reader":
            paired = ents.get("Paired with MagicbHAnds", {}).get("state")
            add(f"LIVE-{n + 6:03d}", "Reader pairing", f"{tag}: paired with MagicbHAnds",
                "pass" if paired == "on" else "fail", f"state {paired}")
            lock = ents.get("Tap lockout", {}).get("state")
            add(f"LIVE-{n + 7:03d}", "Refused-tap lockout", f"{tag}: not locked out now",
                "pass" if lock == "off" else "fail", f"state {lock}")
        n += 10

    code, page = curl(f"{ha}/api/magicband/page", auth=True)
    markers = ["Needs attention", "Automatic updates", "'Time zone'", "Idle circle heads"]
    missing = [m for m in markers if m not in page]
    add("LIVE-004", "MagicbHAnds page", "Integration serves the current page (/api/magicband/page)",
        "pass" if code == 200 and not missing else "fail", f"HTTP {code}" + (f", missing {missing}" if missing else ""))
    extra = os.environ.get("HA_EXTRA_PAGE")  # e.g. a dashboards add-on's copy of the page
    if extra:
        code, page2 = curl(f"{ha}{extra}", auth=True)
        missing = [m for m in markers if m not in page2]
        add("LIVE-005", "MagicbHAnds page", "Embedded copy of the page is current", "pass" if not missing else "fail",
            f"HTTP {code}" + (f", missing {missing}" if missing else ""))

    code, log = curl(f"{ha}/api/error_log", auth=True)
    if code == 200:
        lines = [ln for ln in log.splitlines() if "magicband" in ln.lower() and (" ERROR " in ln or " WARNING " in ln)]
        add("LIVE-006", "Integration", "No MagicbHAnds errors or warnings in Home Assistant's log",
            "pass" if not lines else "fail", f"{len(lines)} lines" + (f"; first: {lines[0][:200]}" if lines else ""))
    else:
        add("LIVE-006", "Integration", "Home Assistant log readable", "skip", f"HTTP {code} (needs an admin token)")


def signature_checks() -> None:
    espsecure = shutil.which("espsecure") or "/tmp/claude-0/esphvenv/bin/espsecure"
    if not Path(espsecure).exists():
        add("LIVE-100", "Signed updates", "Release files verify against the public key", "skip", "espsecure not installed")
        return
    with tempfile.TemporaryDirectory() as tmp:
        n = 100
        for prod, (sub, _) in PRODUCTS.items():
            for kind in ("ota", "factory"):
                name = f"{prod}.{kind}-{VERSION}.bin"
                f = Path(tmp) / name
                code, _ = curl(f"{RELEASES}/v{VERSION}/{name}", out=f)
                if code != 200:
                    add(f"LIVE-{n:03d}", "Signed updates", f"Release v{VERSION}: {name} is signed", "fail", f"download HTTP {code}")
                    n += 1
                    continue
                data = f.read_bytes()
                app = Path(tmp) / (name + ".app")
                app.write_bytes(data[0x10000:] if kind == "factory" else data)
                p = subprocess.run([espsecure, "verify-signature", "--version", "2", "--keyfile", str(PUB), str(app)],
                                   capture_output=True, text=True, check=False)
                add(f"LIVE-{n:03d}", "Signed updates", f"Release v{VERSION}: {name} is signed with the project key",
                    "pass" if p.returncode == 0 else "fail", f"{len(data)} bytes")
                n += 1
            # The site serves what devices download: same bytes as the release, if the site is reachable.
            code, body = curl(f"{SITE}/{sub}manifest.json")
            if code == 200:
                m = json.loads(body)
                ok = m.get("version") == VERSION
                add(f"LIVE-{n:03d}", "Signed updates", f"Site manifest for {prod} offers {VERSION}",
                    "pass" if ok else "fail", f"manifest version {m.get('version')}")
            else:
                add(f"LIVE-{n:03d}", "Signed updates", f"Site manifest for {prod} reachable", "skip",
                    f"HTTP {code} (the site may be blocked from here; the release files are checked instead)")
            n += 1


def main() -> None:
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    ha = os.environ.get("HA_URL", "").rstrip("/")
    if ha:
        ha_checks(ha)
    else:
        add("LIVE-001", "Home Assistant", "API reachable (read-only)", "skip", "HA_URL not set")
    signature_checks()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "live.json").write_text(json.dumps({
        "stage": "live", "started": started,
        "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "environment": {"version": VERSION, "home_assistant": bool(ha)}, "results": results}, indent=2) + "\n")
    counts = {s: sum(r["status"] == s for r in results) for s in ("pass", "fail", "skip")}
    print(f"live: {counts}")


if __name__ == "__main__":
    sys.exit(main())
