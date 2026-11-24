"""Config validation of every device file, plain and signed, and the
invariants the docs and the release process rely on.

Each device file is copied to out/firmware-config/ the way CI builds it
(prep.py), resolved with `esphome config` and checked as data.
"""
from __future__ import annotations

import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import prep
from lambdas import as_list, lam, load_resolved, walk

REPO = prep.REPO
WORK = prep.OUT / "firmware-config"
DEVICES = ["bridge", "reader", "bp2", "standalone"]
LABEL = {"bridge": "MagicBand Bridge", "reader": "MagicBand Reader", "bp2": "SCREEK BP2-POE",
         "standalone": "SCREEK BP2-POE standalone"}
VALID_IDS = {("bridge", "plain"): "FW-001", ("bridge", "signed"): "FW-002", ("reader", "plain"): "FW-003",
             ("reader", "signed"): "FW-004", ("bp2", "plain"): "FW-005", ("bp2", "signed"): "FW-006",
             ("standalone", "plain"): "FW-007", ("standalone", "signed"): "FW-008"}
BASE = {"bridge": 20, "reader": 40, "bp2": 60, "standalone": 80}
SECURE = {"CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT": "y", "CONFIG_SECURE_SIGNED_APPS_RSA_SCHEME": "y",
          "CONFIG_SECURE_SIGNED_ON_UPDATE_NO_SECURE_BOOT": "y", "CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES": "n"}
LOG_ORDER = ["NONE", "ERROR", "WARN", "INFO", "CONFIG", "DEBUG", "VERBOSE", "VERY_VERBOSE"]


def time_zones() -> list[str]:
    text = (REPO / "components/magicband/time_zone.h").read_text()
    block = re.search(r"TIME_ZONES\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1)
    return re.findall(r'"([^"]*)"', block)


def r(id_, feature, check, ok, detail="", evidence=None):
    d = dict(id=id_, feature=feature, check=check, status="pass" if ok else "fail", detail=detail)
    if evidence:
        d["evidence"] = evidence
    return d


def resolve_all() -> tuple[dict, dict, list]:
    files = prep.prepare(WORK)
    edir = WORK / "esphome"
    jobs = {(d, v): files[d][v] for d in DEVICES for v in ("plain", "signed") if files[d][v]}

    def one(item):
        (d, v), path = item
        p = subprocess.run(prep.esphome_cmd("config", path.name), cwd=edir, capture_output=True, text=True)
        out = edir / f"{d}-{v}.out"
        out.write_text(p.stdout + p.stderr)
        return (d, v), p.returncode, p.stdout, p.stderr

    with ThreadPoolExecutor(4) as ex:
        done = list(ex.map(one, jobs.items()))
    cfgs, errs = {}, {}
    for key, rc, out, err in done:
        if rc == 0:
            cfgs[key] = load_resolved(out)
        else:
            errs[key] = (out + err)[-3000:]
    return files, cfgs, errs


def run() -> list[dict]:
    res = []
    files, cfgs, errs = resolve_all()
    tz = time_zones()
    for (d, v), rid in VALID_IDS.items():
        ok = (d, v) in cfgs
        res.append(r(rid, f"Device file: {LABEL[d]}", f"{prep.DEVICES[d]} ({v}{', via signed_build.py' if v == 'signed' else ''}) passes `esphome config`",
                     ok, "valid" if ok else (files[d].get("signed_error") or errs.get((d, v), "not resolved")),
                     evidence=f"firmware-config/esphome/{d}-{v}.out"))
    bad = {d: files[d]["signed_error"] for d in DEVICES if files[d]["signed_error"]}
    res.append(r("FW-009", "Signed official builds", "signed_build.py finds exactly one esp-idf framework block (and no sdkconfig_options) in every device file",
                 not bad, "applies to all four device files" if not bad else str(bad)))
    # check_bp2_standalone.py, run as CI does (from esphome/, in a scratch copy)
    sdir = WORK / "standalone-check" / "esphome"
    sdir.mkdir(parents=True, exist_ok=True)
    for f in ("screek-bp2-poe.yaml", "screek-bp2-poe-standalone.yaml", "magicband-addon.yaml"):
        (sdir / f).write_text((prep.ESPHOME_DIR / f).read_text())
    comp = sdir.parent / "components"
    if not comp.exists():
        comp.symlink_to(REPO / "components")
    env_path = str(Path(prep.ESPHOME).parent)
    import os
    p = subprocess.run([prep.PYTHON, str(REPO / ".github/scripts/check_bp2_standalone.py")], cwd=sdir, capture_output=True, text=True,
                       env=dict(os.environ, PATH=env_path + os.pathsep + os.environ.get("PATH", "")))
    res.append(r("FW-010", "BP2-POE standalone file", "check_bp2_standalone.py: the standalone file resolves to the same device as screek-bp2-poe.yaml + the add-on",
                 p.returncode == 0, (p.stdout + p.stderr).strip()[-1500:]))

    for d in DEVICES:
        res += device_invariants(d, cfgs.get((d, "plain")), cfgs.get((d, "signed")), tz)
    if ("reader", "plain") in cfgs:
        res += reader_checks(cfgs[("reader", "plain")])
    return res


def _find(items, **kw):
    return [i for i in as_list(items) if isinstance(i, dict) and all(i.get(k) == v for k, v in kw.items())]


def device_invariants(d: str, plain: dict | None, signed: dict | None, tz: list[str]) -> list[dict]:
    feat = f"Device file: {LABEL[d]}"
    b = BASE[d]
    ids = [f"FW-{b + k:03d}" for k in range(15)]
    if plain is None or signed is None:
        return [dict(id=i, feature=feat, check="invariants", status="skip", detail="config did not resolve (see FW-001..008)") for i in ids]
    out = []
    both = (("plain", plain), ("signed", signed))

    def each(fn):
        fails = []
        for name, c in both:
            msg = fn(c)
            if msg:
                fails.append(f"{name}: {msg}")
        return fails

    # a update entity
    def upd(c):
        u = _find(c.get("update"), id="firmware_update")
        if not u:
            return "no update entity with id firmware_update"
        u = u[0]
        if u.get("platform") != "http_request" or not str(u.get("source", "")).startswith("https://legal-copy7045.github.io/"):
            return f"platform {u.get('platform')}, source {u.get('source')}"
    f = each(upd)
    out.append(r(ids[0], "Firmware updates", f"{LABEL[d]}: update entity firmware_update (http_request, HTTPS manifest on the project's Pages site)", not f, "; ".join(f) or "present in both variants"))

    # b automatic updates switch
    def sw(c):
        s = _find(c.get("switch"), id="auto_update")
        if not s:
            return "no switch auto_update"
        s = s[0]
        if s.get("name") != "Automatic updates" or s.get("restore_mode") != "RESTORE_DEFAULT_OFF":
            return f"name {s.get('name')!r}, restore_mode {s.get('restore_mode')}"
    f = each(sw)
    out.append(r(ids[1], "Automatic updates", f"{LABEL[d]}: 'Automatic updates' switch (id auto_update), off by default", not f, "; ".join(f) or "present, RESTORE_DEFAULT_OFF"))

    # c time zone select
    def sel(c):
        s = _find(c.get("select"), id="time_zone")
        if not s:
            return "no select time_zone"
        s = s[0]
        msgs = []
        if s.get("name") != "Time zone":
            msgs.append(f"name {s.get('name')!r}")
        if list(s.get("options", [])) != tz:
            msgs.append(f"options {s.get('options')} != time_zone.h {tz}")
        if s.get("initial_option") != "Eastern (New York)" or not s.get("restore_value"):
            msgs.append(f"initial {s.get('initial_option')!r}, restore_value {s.get('restore_value')}")
        if not any("apply_time_zone" in str(x) for x in as_list(s.get("on_value"))):
            msgs.append("on_value doesn't run apply_time_zone")
        return ", ".join(msgs)
    f = each(sel)
    out.append(r(ids[2], "Time zone setting", f"{LABEL[d]}: 'Time zone' select options equal TIME_ZONES in time_zone.h, in order; applied on change and kept", not f,
                 "; ".join(f) or f"{len(tz)} options match"))

    # d sntp jobs
    def jobs(c):
        s = _find(c.get("time"), platform="sntp")
        if not s:
            return "no sntp clock"
        ot = s[0].get("on_time", [])
        check = [j for j in ot if j.get("hours") == [2] and j.get("minutes") == [55] and j.get("seconds") == [0]]
        inst = [j for j in ot if j.get("hours") == [3] and j.get("minutes") == [0, 10, 20, 30, 40, 50] and j.get("seconds") == [0]]
        msgs = []
        if not check or "'component.update': {'id': 'firmware_update'}" not in str(check[0]) or "auto_update" not in str(check[0]):
            msgs.append("02:55 check missing or not guarded by auto_update")
        if not inst or "update.perform" not in str(inst[0]) or "auto_update" not in str(inst[0]) or "update.is_available" not in str(inst[0]):
            msgs.append("03:00-03:50 install missing or not guarded by auto_update + update.is_available")
        elif not re.search(r"release_newer\(id\(firmware_update\)\.update_info\.latest_version, id\(firmware_update\)\.update_info\.current_version\)|"
                           r"release_newer\(info\.latest_version, info\.current_version\)", str(inst[0]["then"][0]["if"]["condition"])):
            msgs.append("03:00-03:50 install doesn't check the release is newer (release_newer): the job could go back to an older signed release")
        others = [j for j in ot if j not in check + inst and "update" in str(j.get("then"))]
        if others:
            msgs.append(f"other update jobs: {others}")
        return ", ".join(msgs)
    f = each(jobs)
    out.append(r(ids[3], "Automatic updates", f"{LABEL[d]}: sntp clock checks at 02:55 and installs every 10 min 03:00-03:50, only with the switch on, an update available and the release newer (no rollback)", not f,
                 "; ".join(f) or "02:55 component.update + 03:00..03:50 update.perform, guarded by release_newer"))

    # e both clocks have a zone
    def clocks(c):
        t = as_list(c.get("time"))
        plats = {x.get("platform"): x for x in t}
        msgs = []
        for p in ("homeassistant", "sntp"):
            if p not in plats:
                msgs.append(f"no {p} clock")
            elif not plats[p].get("timezone"):
                msgs.append(f"{p} clock has no timezone")
            elif not any("apply_time_zone" in str(x) for x in as_list(plats[p].get("on_time_sync"))):
                msgs.append(f"{p} clock doesn't apply the Time zone setting on sync")
        if len({x.get("timezone") for x in t}) > 1:
            msgs.append("clocks disagree on timezone")
        return ", ".join(msgs)
    f = each(clocks)
    tzs = {x.get("timezone") for x in as_list(plain.get("time"))}
    out.append(r(ids[4], "Time zone setting", f"{LABEL[d]}: Home Assistant and SNTP clocks both have a timezone and apply the setting on sync", not f, "; ".join(f) or f"timezone {tzs}"))

    # f sdkconfig options
    sp = (plain.get("esp32", {}).get("framework", {}) or {}).get("sdkconfig_options") or {}
    ss = (signed.get("esp32", {}).get("framework", {}) or {}).get("sdkconfig_options") or {}
    sec_plain = {k: v for k, v in sp.items() if k.startswith("CONFIG_SECURE")}
    ok = sec_plain == {} and {k: str(v) for k, v in ss.items() if k.startswith("CONFIG_SECURE")} == SECURE
    out.append(r(ids[5], "Signed official builds", f"{LABEL[d]}: signed variant has the four CONFIG_SECURE_* options, the device file itself none", ok,
                 f"plain {sec_plain or 'none'}; signed {ss}"))

    # g no fallback AP / captive portal
    def ap(c):
        msgs = []
        if "captive_portal" in c:
            msgs.append("captive_portal present")
        if isinstance(c.get("wifi"), dict) and c["wifi"].get("ap"):
            msgs.append("wifi.ap present")
        return ", ".join(msgs)
    f = each(ap)
    out.append(r(ids[6], "No setup hotspot", f"{LABEL[d]}: no fallback Wi-Fi hotspot and no captive portal", not f, "; ".join(f) or ("Wi-Fi without ap" if "wifi" in plain else "Ethernet device, no Wi-Fi")))

    # h ota http_request only
    def ota(c):
        plats = [o.get("platform") for o in as_list(c.get("ota"))]
        return "" if plats == ["http_request"] else f"ota platforms {plats}"
    f = each(ota)
    out.append(r(ids[7], "Signed official builds", f"{LABEL[d]}: the only OTA platform is http_request (no ESPHome upload port in the official file)", not f, "; ".join(f) or "http_request only"))

    # i api encryption, no fixed key
    def api(c):
        a = c.get("api") or {}
        if "encryption" not in a:
            return "no encryption"
        if (a.get("encryption") or {}).get("key"):
            return "a fixed key in the device file (every board would share it)"
    f = each(api)
    out.append(r(ids[8], "Encrypted API", f"{LABEL[d]}: API encryption on, key provisioned per device by Home Assistant (none in the file)", not f, "; ".join(f) or "encryption: {}"))

    # j logger
    def logger(c):
        lv = (c.get("logger") or {}).get("level", "DEBUG")
        has_nfc = "pn532_i2c" in c or "pn532_spi" in c or "rc522" in str(c.keys())
        msgs = []
        if has_nfc and LOG_ORDER.index(lv) > LOG_ORDER.index("INFO"):
            msgs.append(f"NFC device logs at {lv} (tag reads print band IDs)")
        for tag, tl in ((c.get("logger") or {}).get("logs") or {}).items():
            if has_nfc and LOG_ORDER.index(str(tl)) > LOG_ORDER.index("INFO"):
                msgs.append(f"logs.{tag} at {tl}")
        return ", ".join(msgs)
    f = each(logger)
    lv = (plain.get("logger") or {}).get("level")
    out.append(r(ids[9], "Band IDs not logged", f"{LABEL[d]}: a device with an NFC reader logs at INFO or less (no tag IDs); others may log at DEBUG", not f,
                 "; ".join(f) or f"logger level {lv}{' (no NFC reader)' if 'pn532_i2c' not in plain else ''}"))

    # k no factory reset
    def fr(c):
        bad = [b.get("name") for b in as_list(c.get("button")) if b.get("platform") == "factory_reset"]
        bad += [s.get("name") for s in as_list(c.get("switch")) if s.get("platform") == "factory_reset"]
        return f"factory reset entities {bad}" if bad else ""
    f = each(fr)
    sm = [b.get("name") for b in as_list(plain.get("button")) if b.get("platform") == "safe_mode"]
    out.append(r(ids[10], "No factory-reset button", f"{LABEL[d]}: no Factory Reset button or switch any Home Assistant user could press", not f,
                 "; ".join(f) or ("none" + (f" (note: has a safe-mode button {sm}, which any user can press; safe mode keeps the API key)" if sm else ""))))

    # l Wi-Fi set over USB (Improv) where there's Wi-Fi
    if "wifi" in plain:
        f = each(lambda c: "" if "improv_serial" in c and not (c.get("wifi") or {}).get("networks") else "improv_serial missing or Wi-Fi networks baked in")
        out.append(r(ids[11], "Wi-Fi setup over USB", f"{LABEL[d]}: no Wi-Fi credentials in the file; set over USB with Improv", not f, "; ".join(f) or "improv_serial, no networks"))
    else:
        f = each(lambda c: "" if "ethernet" in c else "neither Wi-Fi nor Ethernet")
        out.append(r(ids[11], "Wi-Fi setup over USB", f"{LABEL[d]}: Ethernet device (no Wi-Fi to set up)", not f, "; ".join(f) or "ethernet"))

    # m dashboard import / project name and version
    def proj(c):
        e = c.get("esphome") or {}
        pr = e.get("project") or {}
        msgs = []
        if not str(pr.get("name", "")).startswith("legal-copy7045."):
            msgs.append(f"project name {pr.get('name')}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(pr.get("version", ""))):
            msgs.append(f"project version {pr.get('version')}")
        if "dashboard_import" not in c:
            msgs.append("no dashboard_import (Take control)")
        return ", ".join(msgs)
    f = each(proj)
    pv = (plain.get("esphome") or {}).get("project", {})
    out.append(r(ids[12], "Firmware updates", f"{LABEL[d]}: project name/version set (the update entity compares them) and Take control offered", not f, "; ".join(f) or f"{pv.get('name')} {pv.get('version')}"))

    # n every logger.log is visible at the device's logger level (not compiled out)
    def visible(c):
        lv = (c.get("logger") or {}).get("level", "DEBUG")
        hidden = []

        def scan(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k == "logger.log" and isinstance(v, dict) and LOG_ORDER.index(str(v.get("level", "DEBUG"))) > LOG_ORDER.index(lv):
                        hidden.append(f"{v.get('format')!r} at {v.get('level')} under {lv}")
                    else:
                        scan(v)
            elif isinstance(x, list):
                for i in x:
                    scan(i)
        scan(c)
        return "; ".join(hidden)
    f = each(visible)
    out.append(r(ids[13], "Automatic updates", f"{LABEL[d]}: every logger.log is at or above the logger level, so none is compiled out", not f, "; ".join(f) or "all visible"))

    # o no safe-mode button open to every Home Assistant user
    def safe_btn(c):
        bad = [b.get("name") for b in as_list(c.get("button")) if b.get("platform") == "safe_mode" and not b.get("disabled_by_default")]
        return f"safe-mode button(s) {bad} any Home Assistant user can press (the board then drops its API and proxy until safe mode times out)" if bad else ""
    f = each(safe_btn)
    out.append(r(ids[14], "No factory-reset button", f"{LABEL[d]}: no Safe Mode Boot button open to every Home Assistant user", not f, "; ".join(f) or "none"))
    return out


LOG_ARG_SECRETS = re.compile(r"\b(uid|key|last_band|known_list|band_colours|band_sounds|pair_key|pending_key|colours|sounds)\b")


def reader_checks(c: dict) -> list[dict]:
    out = []
    feat = "Band IDs not logged"
    # FW-095 no log line prints a band ID or key
    bad = []
    n_esp = n_log = 0
    for body in walk(c):
        for m in re.finditer(r"ESP_LOG\w\((.*?)\);", body, re.S):
            n_esp += 1
            args = m.group(1).split(",", 2)[2:] if m.group(1).count(",") >= 2 else []
            if args and LOG_ARG_SECRETS.search(args[0]):
                bad.append(m.group(0)[:160])

    def scan_logger(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "logger.log" and isinstance(v, dict):
                    nonlocal n_log
                    n_log += 1
                    a = " ".join(str(i) for i in as_list(v.get("args")))
                    fmt = str(v.get("format"))
                    if LOG_ARG_SECRETS.search(a):
                        bad.append(f"logger.log {fmt!r} args {a}")
                else:
                    scan_logger(v)
        elif isinstance(x, list):
            for i in x:
                scan_logger(i)
    scan_logger(c)
    # in the tag handler, `x` is the tag's ID: nothing there may log it
    for v in re.findall(r"'logger.log': \{[^}]*'args': \[([^\]]*)\]", str(as_list(c.get("pn532_i2c"))[0].get("on_tag"))):
        if v.strip():
            bad.append(f"on_tag logger.log with args {v}")
    out.append(r("FW-095", feat, "Reader: no ESP_LOG or logger.log prints a band ID, the allowed list, colours or a key", not bad, "; ".join(bad) or f"{n_esp} ESP_LOG calls and {n_log} logger.log actions checked"))

    # FW-096 protected actions
    acts = {a.get("action"): a for a in as_list((c.get("api") or {}).get("actions"))}
    need = {"accept": "reader_key_ok", "deny": "reader_key_ok", "set_known_bands": "reader_key_ok", "set_band_colours": "reader_key_ok",
            "set_band_sounds": "reader_key_ok", "pair": "reader_request_pair", "unpair": "reader_unpair"}
    msgs = []
    for a, fn in need.items():
        if a not in acts:
            msgs.append(f"action {a} missing")
        elif fn not in str(acts[a]) or "key" not in (acts[a].get("variables") or {}):
            msgs.append(f"{a} doesn't take a key and check it with {fn}")
    out.append(r("FW-096", "Reader pairing", "Reader: accept, deny, set_known_bands, set_band_colours, set_band_sounds check the pairing key; pair/unpair go through reader_key.h", not msgs,
                 "; ".join(msgs) or f"{len(need)} actions checked; open actions: {sorted(set(acts) - set(need))}"))

    # FW-097 Test welcome: no tag scan to HA, no refusal counted
    scripts = {s["id"]: s for s in as_list(c.get("script"))}
    bt = str(scripts.get("band_tapped", {}).get("then"))
    msgs = []
    tw = [b for b in as_list(c.get("button")) if b.get("name") == "Test welcome"]
    if not tw or "'uid': 'TEST'" not in str(tw[0]):
        msgs.append("Test welcome doesn't run band_tapped with uid TEST")
    ts_ok = False
    for step in scripts.get("band_tapped", {}).get("then", []):
        if "homeassistant.tag_scanned" in str(step):
            cond = str(step.get("if", {}).get("condition"))
            ts_ok = 'uid != "TEST"' in cond and "homeassistant.tag_scanned" in str(step.get("if", {}).get("then"))
    if not ts_ok:
        msgs.append("homeassistant.tag_scanned isn't guarded by uid != \"TEST\"")
    m = re.search(r"\{'if': \{'condition': \{'lambda': \{'!lambda': 'return uid != \"TEST\";'\}\}, 'then': \[\{'script.execute': \{'id': 'note_refusal'\}\}\]", bt)
    if not m:
        msgs.append("note_refusal isn't guarded by uid != \"TEST\"")
    out.append(r("FW-097", "Test welcome", "Reader: Test welcome plays the welcome without a tag scan to Home Assistant and without counting a refusal", not msgs, "; ".join(msgs) or "guarded"))

    # FW-098 on_tag: lockout branch never reaches band_tapped
    tag = as_list(c.get("pn532_i2c"))[0].get("on_tag")
    msgs = []
    try:
        top = as_list(tag)[0]["then"][0]["if"]
        pair_then = str(top["then"])
        inner = top["else"][0]["if"]
        if "reader_confirm_pair" not in str(top["condition"]):
            msgs.append("first check isn't the pairing confirmation")
        if "band_tapped" in pair_then:
            msgs.append("the pairing tap also runs band_tapped")
        if not re.search(r"lockout_until\)? != 0", str(inner["condition"])):
            msgs.append("second check isn't the lockout")
        if "band_tapped" in str(inner["then"]) or "homeassistant" in str(inner["then"]):
            msgs.append("a locked-out tap still reaches band_tapped / Home Assistant")
        if "band_tapped" not in str(inner.get("else")):
            msgs.append("taps outside a lockout don't run band_tapped")
    except (KeyError, IndexError, TypeError) as e:
        msgs.append(f"unexpected on_tag shape: {e}")
    if (scripts.get("band_tapped") or {}).get("mode") != "single":
        msgs.append("band_tapped isn't mode single (taps during a sequence would queue)")
    out.append(r("FW-098", "Refused-tap lockout", "Reader: on_tag ignores taps during a lockout (no band_tapped, no tag scan), confirms a waiting pairing first, and band_tapped is mode single", not msgs,
                 "; ".join(msgs) or "structure as expected"))

    # FW-160 show effects match shows.h
    shows_h = (REPO / "components/magicband/shows.h").read_text()
    names = re.findall(r'"([^"]+)"', re.search(r"NAMES\[COUNT\]\s*=\s*\{(.*?)\};", shows_h, re.S).group(1))
    ring = _find(c.get("light"), id="ring")[0]
    effs = {e["addressable_lambda"]["name"]: lam(e["addressable_lambda"]["lambda"]) for e in ring.get("effects", []) if "addressable_lambda" in e}
    msgs = []
    for i, n in enumerate(names):
        body = effs.get(n)
        if body is None:
            msgs.append(f"no effect for show {n}")
        elif f"render_show({i}," not in body:
            msgs.append(f"effect {n} doesn't render show {i}")
    for n, body in effs.items():
        mm = re.search(r"render_show\((\d+),", body or "")
        if mm and (int(mm.group(1)) >= len(names) or names[int(mm.group(1))] != n):
            msgs.append(f"effect {n} renders show {mm.group(1)}")
        if mm and "std::min<int>(it.size(), 100)" not in body.replace(" ", " ") and "buf[3 * 100]" not in body:
            msgs.append(f"effect {n}: buffer not sized to ring_max_leds")
    sels = {s.get("id"): s for s in as_list(c.get("select"))}
    for sid in ("startup_show", "show_choice"):
        if sid in sels:
            opts = [o for o in sels[sid]["options"] if o not in ("Off", "Random")]
            if sid == "startup_show" and opts != names[:len(opts)]:
                msgs.append(f"{sid} options {opts} aren't the shows in order")
            extra = set(opts) - set(names)
            if extra:
                msgs.append(f"{sid} has unknown shows {extra}")
        else:
            msgs.append(f"no select {sid}")
    out.append(r("FW-160", "Light shows", "Reader: every show in shows.h has a ring effect that renders that index (buffer sized to ring_max_leds); show selects list only real shows",
                 not msgs, "; ".join(msgs) or f"{len(names)} shows mapped"))

    # FW-162 lockout wiring
    sw = _find(c.get("switch"), id="tap_lockout")
    msgs = []
    if not sw or sw[0].get("restore_mode") != "RESTORE_DEFAULT_OFF" or "end_lockout" not in str(sw[0].get("on_turn_off")):
        msgs.append("Refused-tap lockout switch not default-off or doesn't end a lockout when turned off")
    iv = as_list(c.get("interval"))
    if not any("end_lockout" in str(i) and "lockout_until" in str(i) for i in iv):
        msgs.append("no interval ending the lockout")
    if not _find(c.get("binary_sensor"), id="tap_lockout_active"):
        msgs.append("no Tap lockout binary sensor")
    if "lockout_until" not in str(scripts.get("reader_idle", {}).get("then")):
        msgs.append("reader_idle doesn't show the lockout")
    out.append(r("FW-162", "Refused-tap lockout", "Reader: lockout switch off by default and ends a lockout when turned off; a 5 s interval ends it on time; Tap lockout sensor; the ring shows it",
                 not msgs, "; ".join(msgs) or "wired"))

    # FW-163 list sizes vs settings
    g = {x["id"]: x for x in as_list(c.get("globals"))}
    nums = {x.get("id"): x for x in as_list(c.get("number"))}
    msgs = []
    rt = re.search(r"std::array<uint32_t,\s*(\d+)>", g.get("refusal_times", {}).get("type", ""))
    mx = nums.get("lockout_refusals", {}).get("max_value")
    if not rt or mx is None or float(mx) > int(rt.group(1)):
        msgs.append(f"Lockout after max {mx} exceeds the refusal list ({rt.group(1) if rt else '?'} slots)")
    kl = re.search(r"std::array<char,\s*(\d+)>", g.get("known_list", {}).get("type", ""))
    if not kl or (int(kl.group(1)) - 1) // 15 < 213:
        msgs.append(f"known_list holds {(int(kl.group(1)) - 1) // 15 if kl else '?'} 7-byte bands, docs say 213")
    rc = nums.get("ring_count", {})
    if float(rc.get("min_value", 0)) < 1:
        msgs.append("LED count can be 0 (Spin divides by the LED count)")
    out.append(r("FW-163", "Reader settings", "Reader: setting limits fit the stores (Lockout after <= refusal slots, allowed list holds 213 7-byte bands, LED count >= 1)",
                 not msgs, "; ".join(msgs) or f"refusal slots {rt.group(1)}, Lockout after max {mx}; known_list {kl.group(1)} bytes; LED count min {rc.get('min_value')}"))

    # FW-164 quiet persistence
    msgs = []
    for gid in ("day_volume", "quiet_applied"):
        if not g.get(gid, {}).get("restore_value"):
            msgs.append(f"{gid} not kept through restarts")
    if "apply_quiet" not in str(scripts.get("update_night", {}).get("then")):
        msgs.append("update_night doesn't run apply_quiet")
    out.append(r("FW-164", "Sound at night", "Reader: the day volume and whether 'quieter' is applied survive restarts; update_night applies it", not msgs, "; ".join(msgs) or "restore_value on both"))

    # FW-166 every logger.log in the reader is visible at the logger level
    lv = (c.get("logger") or {}).get("level", "DEBUG")
    hidden = []

    def scan(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "logger.log" and isinstance(v, dict) and LOG_ORDER.index(str(v.get("level", "DEBUG"))) > LOG_ORDER.index(lv):
                    hidden.append(f"{v.get('format')!r} at {v.get('level')}")
                else:
                    scan(v)
        elif isinstance(x, list):
            for i in x:
                scan(i)
    scan(c)
    out.append(r("FW-166", "Automatic updates", f"Reader: every logger.log is at or above the logger level ({lv}), so it isn't compiled out",
                 not hidden, ("Messages that never appear in the reader's logs: " + "; ".join(hidden)) if hidden else "all visible"))

    # FW-167 BUG-002: Tap lockout has a real state from boot (not unknown in Home Assistant)
    boot = as_list((c.get("esphome") or {}).get("on_boot"))
    pubs = [a for b in boot for a in as_list(b.get("then")) if isinstance(a, dict) and (a.get("binary_sensor.template.publish") or {}).get("id") == "tap_lockout_active"]
    ok = bool(pubs) and "lockout_until" in str(pubs[0])
    out.append(r("FW-167", "Refused-tap lockout", "Reader: on_boot publishes 'Tap lockout' (off unless a lockout is active), so Home Assistant never shows it unknown after a restart",
                 ok, "published at boot from lockout_until" if ok else "on_boot doesn't publish tap_lockout_active: it stays unknown until the first lockout ends"))

    # FW-168 BUG-005: a band with its own sound skips the reader's chime only while Home Assistant is connected
    msgs = []
    steps = [st for st in as_list(scripts.get("reader_welcome", {}).get("then")) if "snd_tap_in" in str(st)]
    if not steps:
        msgs.append("reader_welcome doesn't play snd_tap_in")
    else:
        cond = steps[0]["if"]["condition"]
        cs = str(cond)
        if "own_sound" in cs and not re.search(r"'or': \[[^\]]*own_sound[^\]]*'not': \{'api.connected'", cs):
            msgs.append(f"own_sound skips the chime without checking api.connected: {cs[:300]}")
    out.append(r("FW-168", "Welcome sounds", "Reader: a band with its own welcome sound skips the tap-in chime only while Home Assistant is connected (it plays the person's sound)",
                 not msgs, "; ".join(msgs) or "or(!own_sound, not api.connected)"))

    # FW-169 BUG-006: settings that redraw the idle glow don't cut off a tap sequence
    msgs = []
    for kind in ("number", "select", "switch"):
        for e in as_list(c.get(kind)):
            for trig in ("on_value", "on_turn_on", "on_turn_off"):
                for step in as_list(e.get(trig)):
                    if "'reader_idle'" in str(step) and "band_tapped" not in str(step):
                        msgs.append(f"{kind} {e.get('id')} {trig} redraws the idle glow during a tap")
    out.append(r("FW-169", "Ring effects", "Reader: every setting that redraws the idle glow (LED count, LED brightness, Idle glow, ...) waits for a tap's sequence (band_tapped not running)",
                 not msgs, "; ".join(msgs) or "all guarded"))

    # FW-171 BUG-007: a Time zone change recomputes sunset and sunrise from Home Assistant's sun times
    tzs = str(scripts.get("apply_time_zone", {}).get("then"))
    ok = all(x in tzs for x in ("'id': 'sun_time'", "sun_next_setting).state", "sun_next_rising).state"))
    out.append(r("FW-171", "Night mode", "Reader: apply_time_zone re-runs sun_time with sun.sun's next_setting and next_rising, so the stored sunset/sunrise follow a Time zone change",
                 ok, "both sun times recomputed in the new zone" if ok else "apply_time_zone keeps the old zone's sunset/sunrise minutes until sun.sun next updates"))

    # FW-173 BUG-008: the start-up sound waits (up to 20 s) for the time before deciding about night
    msgs = []
    then = [a for b in boot for a in as_list(b.get("then"))]
    idx_snd = next((i for i, a in enumerate(then) if "snd_startup" in str(a)), None)
    idx_wait = next((i for i, a in enumerate(then) if isinstance(a, dict) and "wait_until" in a and "is_valid" in str(a)), None)
    idx_night = next((i for i, a in enumerate(then) if isinstance(a, dict) and (a.get("script.execute") or {}).get("id") == "update_night"), None)
    if idx_snd is None:
        msgs.append("no start-up sound in on_boot")
    elif idx_wait is None or idx_wait > idx_snd:
        msgs.append("the start-up sound doesn't wait for a valid time")
    else:
        to = str(then[idx_wait]["wait_until"].get("timeout", ""))
        if not to or not re.fullmatch(r"(\d+)s|(\d+)ms", to) or (int(re.match(r"\d+", to).group()) / (1000 if to.endswith("ms") else 1)) > 20:
            msgs.append(f"wait for the time has timeout {to!r} (want <= 20 s)")
        if idx_night is None or not idx_wait < idx_night < idx_snd:
            msgs.append("night isn't worked out (update_night) between the wait and the sound")
    out.append(r("FW-173", "Sound at night", "Reader: on_boot waits up to 20 s for the time and runs update_night before deciding on the start-up sound",
                 not msgs, "; ".join(msgs) or "wait_until time valid (<= 20 s), update_night, then the sound"))

    # FW-177 SEC-005: the blue breathing ends with the pairing wait (asking again doesn't extend it)
    pw = scripts.get("pair_wait", {})
    ok = "pending_until" in str(pw.get("then")) and "2min" not in str(pw.get("then"))
    out.append(r("FW-177", "Reader pairing", "Reader: pair_wait (blue breathing) lasts until the pairing wait's own deadline, not 2 minutes from the latest request",
                 ok, "delay until pending_until" if ok else "pair_wait waits a fixed 2 minutes from each request"))

    # FW-165 airtime budget constants (bridge / add-on component)
    h = (REPO / "components/magicband/magicband.h").read_text()
    def const(n):
        mm = re.search(rf"{n}\s*=\s*([\d.]+)f?;", h)
        return float(mm.group(1)) if mm else None
    rate, mxa, start, maxd = const("AIRTIME_RATE"), const("AIRTIME_MAX_MS"), const("AIRTIME_START_MS"), const("MAX_DURATION_MS")
    ok = None not in (rate, mxa, start, maxd) and abs(rate - 0.5) < 1e-9 and mxa == 30000 and maxd == 60000 and mxa / (1 - rate) >= maxd and start < mxa
    out.append(r("FW-165", "Bridge airtime budget", "magicband.h: airtime earns 0.5 s/s up to 30 s, one command at most 60 s, and a full budget covers one 60 s command (as docs/security.md says)",
                 ok, f"AIRTIME_RATE {rate}, AIRTIME_MAX_MS {mxa}, AIRTIME_START_MS {start}, MAX_DURATION_MS {maxd}; full budget lasts {mxa / (1 - rate) if rate is not None and rate < 1 else '?'} ms on air"))
    return out


if __name__ == "__main__":
    for x in run():
        print(x["id"], x["status"], x["check"][:90], "|", str(x.get("detail"))[:200])
