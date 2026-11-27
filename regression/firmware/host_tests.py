"""Host C++ unit tests of components/magicband and the reader's lambdas.

Compiles each test in host/ with g++ (ASan + UBSan) against small mocks of
ESPHome's Color / ESPColorView (host/mock) and ESPHome's real posix_tz.cpp
from the installed ESPHome, runs it and turns its RESULT lines into results.
A crash, sanitizer report or missing RESULT line is a failure of every check
that test owns. Also compares the shows with the page's JavaScript copy, and
the time zones with aioesphomeapi's POSIX parser and Python's zoneinfo.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "host"))
import build  # noqa: E402
import prep  # noqa: E402
from lambdas import generate, load_resolved  # noqa: E402

REPO = prep.REPO

CHECKS = {
    # put_dimmed
    "FW-100": ("Ring colours when dim (put_dimmed)", "RGB ring: warm white, orange and pink keep their mix at every level x light brightness x LED brightness (top channel stays top, channels with >= 1/5 share stay on, no foreign channel, mix within rounding)"),
    "FW-101": ("Ring colours when dim (put_dimmed)", "RGB ring, colour carrying w=255: still takes the mix path (the 0.10.29 fix)"),
    "FW-102": ("Ring colours when dim (put_dimmed)", "RGBW ring with a white-LED colour: plain c*level path, white included"),
    "FW-103": ("Ring colours when dim (put_dimmed)", "RGBW ring with a colour without white: same mix as RGB, white LED (probed at 255) left off"),
    "FW-104": ("Ring colours when dim (put_dimmed)", "Level 0, or a black colour, gives an unlit LED (RGB and RGBW)"),
    "FW-105": ("Ring colours when dim (put_dimmed)", "The top channel never brightens as the level falls"),
    "FW-106": ("Ring colours when dim (put_dimmed)", "Level 255 keeps the colour's full brightness"),
    "FW-107": ("Ring colours when dim (put_dimmed)", "Documented 'a channel with a fifth or more of the share never drops out' also at the dimmest LED brightness settings"),
    # shows
    "FW-110": ("Light shows", "render_show never writes outside 3n bytes (28 shows, 1-100 LEDs, whole duration); n <= 0 writes nothing"),
    "FW-111": ("Light shows", "render_show is deterministic: same (show, t, n) gives the same frame in any order, from a dirty buffer"),
    "FW-112": ("Light shows", "render_show returns true until DURATION_MS, then false with a dark frame; unknown index is dark"),
    "FW-113": ("Light shows", "Every show ends dark (faded over its last 60 ms), as shows.h says"),
    "FW-114": ("Light shows", "NAMES unique, index_of round-trips, RANDOM_COUNT covers the everyday shows only"),
    # time zones
    "FW-120": ("Time zone setting", "set_time_zone knows every TIME_ZONES option (and nothing else is listed)"),
    "FW-121": ("Time zone setting", "Each option's parsed zone equals aioesphomeapi.parse_posix_tz of the IANA zone's POSIX rule (ESPHome's own tzdata path)"),
    "FW-122": ("Time zone setting", "Local time via ESPHome's posix_tz.cpp matches zoneinfo around US, UK and EU DST changes 2025-2030"),
    "FW-123": ("Time zone setting", "Unknown zone names return false and leave the zone in force"),
    "FW-124": ("Time zone setting", "The device files' default timezone (substitution) is the same zone as the select's initial option"),
    # reader key
    "FW-130": ("Reader pairing", "Unpaired reader: protected actions work with any key"),
    "FW-131": ("Reader pairing", "Pairing key must be 32-64 hex characters (short, long, non-hex, NUL refused)"),
    "FW-132": ("Reader pairing", "Paired reader accepts only its own key (length and every character) and never takes another"),
    "FW-133": ("Reader pairing", "First pairing waits for a tap: PAIRING_PENDING, confirmed by a tap within 2 minutes"),
    "FW-134": ("Reader pairing", "Rejection paths: expired wait, second requester, tap with nothing pending, millis() wrap"),
    "FW-135": ("Reader pairing", "Unpair needs the current key and clears it"),
    "FW-136": ("Reader pairing", "First-pairing hijack (SEC-005): asking again doesn't extend a wait, a competing key gets PAIRING_BUSY, an expired key has a 2-minute cool-down in which other keys may ask"),
    # JS copy
    "FW-140": ("Light shows on the page", "page.html SHOW_NAMES and SHOW_MS equal shows.h NAMES and DURATION_MS"),
    "FW-141": ("Light shows on the page", "page.html showHash equals shows::hash"),
    "FW-142": ("Light shows on the page", "page.html showHue equals shows::hue"),
    "FW-143": ("Light shows on the page", "page.html renderShow draws the same frames as render_show (28 shows, 12 and 24 LEDs, whole duration)"),
    # lambdas
    "FW-150": ("Idle circle", "Idle circle effect: heads 1-4, tail clamp, no division by zero at tail=1/n small, Reverse mirrors Forward, no overrun (NaN and out-of-range settings, 1-100 LEDs)"),
    "FW-151": ("Ring effects", "Chase, Pulse, Welcome, Spin, Breathe effects: no overrun or UB for any setting (zero times, NaN, huge), RGB/RGBW, millis wrap"),
    "FW-152": ("Warm glow", "Warm glow effect: warm mix on every LED, off at 0 %, night setting at night, monotonic"),
    "FW-153": ("Refused-tap lockout", "note_refusal counting: switch, N within window, defaults, 20-of-20, list cleared, millis wrap, never 0"),
    "FW-154": ("Refused-tap lockout", "Tap handler ignores taps exactly while locked; the interval ends it on time; end_lockout clears"),
    "FW-155": ("Sound at night", "apply_quiet transitions: night/morning, only on change, Same mode, NaN default"),
    "FW-156": ("Night mode", "update_night: fixed and sunset/sunrise windows, midnight wrap, fallbacks, redraw rules"),
    "FW-157": ("Night mode", "sun_time: Home Assistant ISO times to local minutes in the set zone"),
    "FW-158": ("Known bands only", "Reader's own decision: 4/7/10-byte IDs, whole-entry match, case/separators ignored"),
    "FW-159": ("Reader pairing", "Allow last band: adds once, ignores TEST, refuses on a paired reader and when full"),
    "FW-161": ("Reader pairing", "on_tag confirms a waiting first pairing (does nothing else)"),
    "FW-172": ("Sound at night", "Start-up sound after a power cut (BUG-008): with the time still unknown it plays only with 'Sound at night' Normal; with the time known, Off at night is silent"),
    "FW-174": ("Reader pairing", "Forget last band / Forget all bands do nothing on a paired reader (SEC-006) and work as before on an unpaired one"),
    "FW-175": ("Unknown-band tag scan limit", "Reader: bands not on its list go through a flood guard only, 60 new a minute / 600 an hour (SEC-008); a family enrolling, listed bands and retaps always go"),
    "FW-176": ("Light shows", "Reader's play_show action: at most 12 shows a minute, sliding, across the millis() wrap (SEC-011)"),
    "FW-179": ("Unknown-band tag scan limit", "Reader (BUG-020): bands ever on the list (set_known_bands, Allow last band; kept through restarts) always reach Home Assistant, also off the list; one flood guard (60 a minute, 600 an hour) whatever the mode or pairing"),
    # guards.h
    "FW-180": ("Automatic updates", "release_newer: automatic updates only install a strictly newer release (no rollback, SEC-002); malformed versions never install"),
    "FW-181": ("Unknown-band tag scan limit", "UnknownTagLimit (flood guard): 60 new IDs a minute, 600 an hour, a family of 20 enrolling all pass, a reported ID tapped again passes, refused IDs aren't recorded, wrap-safe"),
    "FW-182": ("Light shows", "RateLimit: at most N events in any window, sliding"),
    "FW-183": ("Unknown-band tag scan limit", "ListedBands remembers the last 128 listed IDs (re-adding writes nothing, restorable bytes)"),
    # ring_colour
    "FW-228": ("Ring type (RGBW)", "RGBW ring: the light call from ring_on, through ESPHome's own LightColorValues, gives the LEDs exactly set_ring_colour's mix; Warm white on a warm-white ring lights only the white LED (the old call also lit full RGB white)"),
    "FW-229": ("Ring type (RGBW)", "RGB ring: ring_on's colours are unchanged by ring_colour; NaN, out-of-range and black input handled"),
    # mocks
    "FW-170": ("Host test harness", "The host mocks still match ESPHome's real color.h / esp_color_correction.cpp formulas"),
}
TESTS = {
    "test_put_dimmed": ["FW-100", "FW-101", "FW-102", "FW-103", "FW-104", "FW-105", "FW-106", "FW-107"],
    "test_shows": ["FW-110", "FW-111", "FW-112", "FW-113", "FW-114"],
    "test_reader_key": ["FW-130", "FW-131", "FW-132", "FW-133", "FW-134", "FW-135", "FW-136"],
    "test_lambdas": ["FW-150", "FW-151", "FW-152", "FW-153", "FW-154", "FW-155", "FW-156", "FW-157", "FW-158", "FW-159", "FW-161",
                     "FW-172", "FW-174", "FW-175", "FW-176", "FW-179"],
    "test_guards": ["FW-180", "FW-181", "FW-182", "FW-183"],
    "test_ring_colour": ["FW-228", "FW-229"],
}
ZONE_IANA = {"Eastern (New York)": "America/New_York", "Central (Chicago)": "America/Chicago", "Mountain (Denver)": "America/Denver",
             "Arizona (Phoenix)": "America/Phoenix", "Pacific (Los Angeles)": "America/Los_Angeles", "Alaska (Anchorage)": "America/Anchorage",
             "Hawaii (Honolulu)": "Pacific/Honolulu", "UK (London)": "Europe/London", "Central Europe (Paris)": "Europe/Paris", "UTC": "UTC"}


def res(id_, ok, detail, status=None, evidence=None):
    feat, check = CHECKS[id_]
    d = dict(id=id_, feature=feat, check=check, status=status or ("pass" if ok else "fail"), detail=detail)
    if evidence:
        d["evidence"] = evidence
    return d


def parse(out: str) -> dict:
    found = {}
    for line in out.splitlines():
        if line.startswith("RESULT|"):
            _, i, st, detail = line.split("|", 3)
            found[i] = (st == "pass", detail)
    return found


def run_cpp(name: str, extra: list[Path] = ()) -> list[dict]:
    ids = TESTS[name]
    exe, log = build.compile_test([HERE / "host" / f"{name}.cpp", *extra], name)
    logdir = prep.OUT / "firmware-logs"
    logdir.mkdir(parents=True, exist_ok=True)
    if exe is None:
        (logdir / f"{name}.build.log").write_text(log)
        return [res(i, False, "host test didn't compile: " + log[-1200:], evidence=f"firmware-logs/{name}.build.log") for i in ids]
    try:
        rc, out, err = build.run_test(exe, timeout=1800)
    except subprocess.TimeoutExpired:
        return [res(i, False, "host test timed out") for i in ids]
    (logdir / f"{name}.log").write_text(out + "\n--- stderr ---\n" + err)
    found = parse(out)
    results = []
    crash = ""
    if rc != 0:
        oob = [l for l in out.splitlines() if l.startswith("OOB|")]
        crash = f"exit {rc}: " + (oob[0] if oob else "") + " " + err.strip()[-800:]
    for i in ids:
        if i in found:
            ok, detail = found[i]
            results.append(res(i, ok, detail, evidence=f"firmware-logs/{name}.log"))
        else:
            results.append(res(i, False, "no result: the test stopped before this check. " + crash, evidence=f"firmware-logs/{name}.log"))
    return results


def mock_drift() -> dict:
    sp = build.site_packages()
    real_color = (sp / "esphome/core/color.h").read_text()
    real_cc = (sp / "esphome/components/light/esp_color_correction.cpp").read_text()
    real_cch = (sp / "esphome/components/light/esp_color_correction.h").read_text()
    real_view = (sp / "esphome/components/light/esp_color_view.h").read_text()
    want = {
        "esp_scale8": "(uint16_t(i) * (1 + uint16_t(scale))) / 256" in real_color,
        "esp_scale8_twice": "(uint32_t(i) * (1 + uint32_t(scale1)) * (1 + uint32_t(scale2))) >> 16" in real_color,
        "gamma rounding (+128)/257": "uint8_t result = (table_value + 128) / 257;" in real_cc,
        "min one step": "if (result == 0 && table_value != 0)" in real_cc,
        "correct = gamma(scale8_twice(v, max, local))": "esp_scale8_twice(red, this->max_brightness_.red, this->local_brightness_)" in real_cch,
        "white skipped when absent": "if (this->white_ == nullptr)\n      return;" in real_view,
        "set = set_rgbw(r,g,b,w)": "this->set_rgbw(color.r, color.g, color.b, color.w)" in real_view,
    }
    bad = [k for k, v in want.items() if not v]
    return res("FW-170", not bad, "real headers still use: " + ", ".join(want) if not bad else f"ESPHome changed: {bad}; update host/mock")


def time_zone_checks() -> list[dict]:
    sp = build.site_packages()
    exe, log = build.compile_test([HERE / "host/test_time_zone.cpp", sp / "esphome/components/time/posix_tz.cpp"], "test_time_zone")
    ids = ["FW-120", "FW-121", "FW-122", "FW-123", "FW-124"]
    if exe is None:
        return [res(i, False, "didn't compile: " + log[-1200:]) for i in ids]
    # instants every 15 min over each Sunday in March, October and November 2025-2030 (every US/UK/EU change), plus ordinary dates
    epochs = set()
    for year in range(2025, 2031):
        for m in (3, 10, 11):
            for d in range(1, 32):
                try:
                    base = int(datetime(year, m, d, tzinfo=timezone.utc).timestamp())
                except ValueError:
                    continue
                if datetime(year, m, d).weekday() == 6:
                    for k in range(-6 * 3600, 18 * 3600, 900):
                        epochs.add(base + k)
    epochs |= {1767225600, 1782864000, 1798761600, 2000000000}  # 2026-01-01, 2026-07-01, 2027-01-01, 2033-05-18
    epochs = sorted(epochs)
    rc, out, err = build.run_test(exe, stdin=" ".join(map(str, epochs)))
    zones, local, unknown = {}, [], []
    for line in out.splitlines():
        p = line.split("|")
        if p[0] == "ZONE":
            zones[p[1]] = p[2:]
        elif p[0] == "LOCAL":
            local.append(p[1:])
        elif p[0] == "UNKNOWN":
            unknown.append(p[1:])
    results = []
    tz_h = (REPO / "components/magicband/time_zone.h").read_text()
    listed = re.findall(r'"([^"]*)"', re.search(r"TIME_ZONES\[\]\s*=\s*\{(.*?)\};", tz_h, re.S).group(1))
    zone_names = re.findall(r'\{"([^"]+)",\s*-?\d+,\s*DstRule::', tz_h)
    bad = [n for n, v in zones.items() if v[0] != "1"]
    if sorted(zone_names) != sorted(listed):
        bad.append(f"ZONES {zone_names} vs TIME_ZONES {listed}")
    if set(ZONE_IANA) != set(listed):
        bad.append(f"options without an IANA mapping in this test: {set(listed) ^ set(ZONE_IANA)}")
    results.append(res("FW-120", not bad and rc == 0, f"{len(zones)} options apply" if not bad else str(bad)))
    # FW-121 vs aioesphomeapi
    from aioesphomeapi.posix_tz import parse_posix_tz
    from esphome.components.time import _extract_tz_string, _load_tzdata
    diffs, posix = [], {}
    for name, iana in ZONE_IANA.items():
        if name not in zones:
            diffs.append(f"{name}: not applied")
            continue
        raw = _load_tzdata(iana)
        ps = _extract_tz_string(raw) if raw else ("UTC0" if iana == "UTC" else None)
        posix[name] = ps
        p = parse_posix_tz(ps)
        exp = [str(p.std_offset_seconds), str(p.dst_offset_seconds)]
        for rl in (p.dst_start, p.dst_end):
            exp.append(f"{int(rl.type)},{rl.month},{rl.week},{rl.day_of_week},{rl.day},{rl.time_seconds}")
        if zones[name][1:] != exp:
            diffs.append(f"{name}: C++ {zones[name][1:]} vs {ps} -> {exp}")
    results.append(res("FW-121", not diffs, "; ".join(diffs) or "all 10 equal: " + ", ".join(f"{k}={v}" for k, v in posix.items())))
    # FW-122 vs zoneinfo
    wrong = []
    for name, ep, txt, isdst in local:
        iana = ZONE_IANA.get(name)
        if not iana:
            continue
        dt = datetime.fromtimestamp(int(ep), ZoneInfo(iana))
        want = dt.strftime("%Y-%m-%d %H:%M:%S")
        wdst = 1 if dt.dst() and dt.dst().total_seconds() else 0
        if txt != want or int(isdst) != wdst:
            wrong.append(f"{name} @{ep}: {txt} dst={isdst}, zoneinfo {want} dst={wdst}")
    results.append(res("FW-122", not wrong and local != [], f"{len(local)} conversions ({len(epochs)} instants x {len(zones)} zones) match zoneinfo" if not wrong
                       else f"{len(wrong)} of {len(local)} differ: " + "; ".join(wrong[:8])))
    # FW-123 unknown names
    badu = [u for u in unknown if u[1] != "0" or u[2] != "1"]
    results.append(res("FW-123", unknown != [] and not badu, f"{len(unknown)} unknown names refused, zone unchanged" if not badu else str(badu)))
    # FW-124 default substitution vs initial option
    mism = []
    for f in prep.DEVICES.values():
        text = (REPO / "esphome" / f).read_text()
        m = re.search(r"^\s+timezone:\s*(\S+)", text, re.M)
        sub = m.group(1).strip('"') if m else None
        if sub and sub.startswith("$"):
            add = (REPO / "esphome/magicband-addon.yaml").read_text()
            m2 = re.search(r"^\s+timezone:\s*(\S+)", add, re.M)
            sub = m2.group(1) if m2 else sub
        if sub != ZONE_IANA["Eastern (New York)"]:
            mism.append(f"{f}: default timezone {sub}")
    results.append(res("FW-124", not mism, "; ".join(mism) or "every device file defaults to America/New_York = the initial 'Eastern (New York)' option"))
    return results


JS_DRIVER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const a = src.indexOf('const SHOW_NAMES='), b = src.indexOf('return out; }', a);
if (a < 0 || b < 0) { console.log(JSON.stringify({error: 'SHOW_NAMES/renderShow not found'})); process.exit(0); }
eval(src.slice(a, b + 'return out; }'.length) + '\nglobalThis.SN=SHOW_NAMES; globalThis.SM=SHOW_MS; globalThis.H=showHash; globalThis.HU=showHue; globalThis.R=renderShow;');
const q = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = {names: SN, ms: SM, hash: q.hash.map(([x, y]) => H(x, y)), hue: q.hue.map(h => HU(h)), frames: []};
for (const [s, t, n] of q.frames) {
  const f = R(s, t, n);
  out.frames.push(f ? f.map(([c, v]) => c.map(k => Math.floor(k * v * 255))) : null);
}
console.log(JSON.stringify(out));
"""

HASH_HUE_CPP = r"""
#include <cstdio>
#include "test_common.h"
#include "esphome/components/magicband/shows.h"
using namespace esphome::magicband;
int main() {
  unsigned a, b; float h; char k;
  while (scanf(" %c", &k) == 1) {
    if (k == 'H' && scanf("%u %u", &a, &b) == 2) printf("%u\n", shows::hash(a, b));
    else if (k == 'U' && scanf("%f", &h) == 1) { auto c = shows::hue(h); printf("%.6f %.6f %.6f\n", c.r, c.g, c.b); }
  }
}
"""


def js_checks() -> list[dict]:
    ids = ["FW-140", "FW-141", "FW-142", "FW-143"]
    node = shutil.which("node")
    if not node:
        return [res(i, False, "node not installed", status="skip") for i in ids]
    page = REPO / "custom_components/magicband/frontend/page.html"
    shows_h = (REPO / "components/magicband/shows.h").read_text()
    names = re.findall(r'"([^"]+)"', re.search(r"NAMES\[COUNT\]\s*=\s*\{(.*?)\};", shows_h, re.S).group(1))
    durs = [int(x) for x in re.findall(r"\d+", re.search(r"DURATION_MS\[COUNT\]\s*=\s*\{(.*?)\};", shows_h, re.S).group(1))]
    hashes = [[a, b] for a in (0, 1, 2, 7, 31, 99, 1000, 65535) for b in (0, 1, 5, 12, 99, 4000, 123456, 4294967295)]
    hues = [i / 97.0 for i in range(-50, 250)]
    frames = [[s, t, n] for s in range(len(names)) for n in (12, 24) for t in range(0, durs[s] if s < len(durs) else 3000, 53)]
    q = json.dumps({"hash": hashes, "hue": hues, "frames": frames})
    drv = build.BUILD / "shows_js_driver.js"
    build.BUILD.mkdir(parents=True, exist_ok=True)
    drv.write_text(JS_DRIVER)
    p = subprocess.run([node, str(drv), str(page)], input=q, capture_output=True, text=True, timeout=600)
    try:
        js = json.loads(p.stdout)
    except json.JSONDecodeError:
        return [res(i, False, "JS driver failed: " + (p.stdout + p.stderr)[-800:]) for i in ids]
    if "error" in js:
        return [res(i, False, js["error"]) for i in ids]
    out = []
    ok = js["names"] == names and js["ms"] == durs
    out.append(res("FW-140", ok, "28 names and durations equal" if ok else f"names diff {set(names) ^ set(js['names'])}, order equal {js['names'] == names}; durations equal {js['ms'] == durs}"))
    # C++ hash and hue
    src = build.BUILD / "hash_hue.cpp"
    src.write_text(HASH_HUE_CPP)
    exe, log = build.compile_test([src], "hash_hue", sanitize=False)
    if exe is None:
        out += [res("FW-141", False, log[-600:]), res("FW-142", False, log[-600:])]
    else:
        inp = " ".join(f"H {a} {b}" for a, b in hashes) + " " + " ".join(f"U {h:.9f}" for h in hues)
        _, o, _ = build.run_test(exe, stdin=inp)
        lines = o.splitlines()
        ch = [int(x) for x in lines[:len(hashes)]]
        bad = [(hashes[i], ch[i], js["hash"][i]) for i in range(len(hashes)) if ch[i] != js["hash"][i]]
        out.append(res("FW-141", not bad, f"{len(hashes)} pairs equal" if not bad else f"{len(bad)} differ, e.g. {bad[:4]}"))
        hb = []
        for i, l in enumerate(lines[len(hashes):]):
            c = [float(v) for v in l.split()]
            if max(abs(c[k] - js["hue"][i][k]) for k in range(3)) > 1e-4:
                hb.append((round(hues[i], 4), c, js["hue"][i]))
        out.append(res("FW-142", not hb, f"{len(hues)} hues equal within 1e-4" if not hb else f"{len(hb)} differ, e.g. {hb[:3]}"))
    # frames
    exe, log = build.compile_test([HERE / "host/test_shows.cpp"], "test_shows_dump", sanitize=False)
    if exe is None:
        out.append(res("FW-143", False, log[-600:]))
        return out
    _, o, _ = build.run_test(exe, ["dump"], stdin="\n".join(f"{s} {t} {n}" for s, t, n in frames))
    per_show = {}
    for (s, t, n), line, jf in zip(frames, o.splitlines(), js["frames"]):
        parts = line.split()
        on, hexs = parts[3] == "1", parts[4] if len(parts) > 4 else ""
        c = bytes.fromhex(hexs)
        st = per_show.setdefault(s, {"leds": 0, "bad": 0, "worst": 0, "at": None})
        if (jf is None) != (not on):
            st["bad"] += n
            st["at"] = st["at"] or (t, n, "running state differs")
            continue
        if jf is None:
            continue
        for i in range(n):
            st["leds"] += 1
            d = max(abs(c[3 * i + k] - jf[i][k]) for k in range(3))
            if d > 2:
                st["bad"] += 1
                if d > st["worst"]:
                    st["worst"], st["at"] = d, (t, n, i, list(c[3 * i:3 * i + 3]), jf[i])
    issues = []
    for s, st in sorted(per_show.items()):
        frac = st["bad"] / max(1, st["leds"])
        if frac > 0.005:
            issues.append(f"{names[s]}: {st['bad']} of {st['leds']} LEDs differ by >2 (worst {st['worst']} at t,n,i,C++,JS={st['at']})")
    tot = sum(v["leds"] for v in per_show.values())
    out.append(res("FW-143", not issues, f"{len(frames)} frames, {tot} LEDs: every show within 2 steps on >= 99.5 % of LEDs" if not issues
                   else "The page's copy has drifted from shows.h: " + "; ".join(issues)))
    return out


def run() -> list[dict]:
    build.prepare()
    results = [mock_drift()]
    results += run_cpp("test_put_dimmed")
    results += run_cpp("test_shows")
    results += run_cpp("test_reader_key")
    results += run_cpp("test_guards")
    results += run_cpp("test_ring_colour")
    results += time_zone_checks()
    results += js_checks()
    # lambdas: from the resolved reader config written by config_checks (or resolve it now)
    out = prep.OUT / "firmware-config" / "esphome" / "reader-plain.out"
    if not out.exists():
        files = prep.prepare(prep.OUT / "firmware-config")
        p = subprocess.run(prep.esphome_cmd("config", files["reader"]["plain"].name), cwd=prep.OUT / "firmware-config" / "esphome", capture_output=True, text=True)
        out.write_text(p.stdout + p.stderr)
    try:
        generate(load_resolved(out.read_text()), build.BUILD / "inc" / "lambdas_gen.h")
        results += run_cpp("test_lambdas", [build.site_packages() / "esphome/components/time/posix_tz.cpp"])
    except (SystemExit, StopIteration, KeyError) as e:
        results += [res(i, False, f"couldn't extract the reader's lambdas: {e!r}") for i in TESTS["test_lambdas"]]
    return results


if __name__ == "__main__":
    for r in run():
        print(r["id"], r["status"], "|", r["detail"][:300])
