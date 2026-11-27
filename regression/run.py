#!/usr/bin/env python3
"""Run the regression stages (and optionally the walkthrough), and the project standard's commands.

Usage (the project standard's command set, STANDARD.md 3.3, plus this project's options):
  python3 regression/run.py check                  # ci + unit + quality, quiet: run before marking a PR ready
  python3 regression/run.py                        # every regression stage, then manual
  python3 regression/run.py --with-walkthrough     # the regression stages and the walkthrough, side by side
  python3 regression/run.py --stage unit           # one stage (repeat --stage for more)
  python3 regression/run.py --compile              # also compile every firmware (slow: ~20 min cold)
  python3 regression/run.py --serial               # one stage at a time (default: all at once)
  python3 regression/run.py report [--walkthrough] # this project's reports (out/report.html, walkthrough report)
  python3 regression/run.py brief|log|summary|manual|schema|walkthrough-due ...   (regression/standard.py)

Stages (standard names; this project's runners): ci (release tooling, regression/ci), unit (the integration's
pytest suite, regression/integration), device (firmware config, host tests and compiles, regression/firmware),
page (the page in Chromium, regression/page), live (read-only checks of what's released and running,
regression/live), quality (lint, static security scan, dependency audit: an extra stage), manual
(regression/manual.yaml). Each writes regression/out/<stage>.json in the standard's format (id, key, status,
detail, evidence; plus this project's feature and check). IDs keep their original prefixes (INT-, FW-, CI-, PAGE-,
LIVE-, QUAL-, WALK-) and are never renumbered; the committed registries are regression/ids/<stage>.yaml.

The walkthrough writes to regression/walkthrough/out/ with its own mock hosts and browser, so it runs alongside the
stages without colliding; afterwards its checks, inventory and screenshots are also copied to the standard's places
(out/walkthrough-checks.json, out/walkthrough.json, out/walkthrough/). After the stages, out/ids.json records
whether every reported check ID is in the committed registry. Environment the stages read:

  HA_PYTHON        python with pytest-homeassistant-custom-component (unit and walkthrough)
  ESPHOME_PYTHON   python with esphome and esptool (device and ci stages)
  QUALITY_PYTHON   python with ruff, bandit, pip-audit, pytest (quality; installed on first use otherwise)
  HA_URL, HA_TOKEN Home Assistant for the live stage and the walkthrough's entity list (read-only)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
WALK_OUT = HERE / "walkthrough" / "out"
STAGES = ["ci", "unit", "device", "page", "live", "quality"]   # the regression stages (the default)
CHECK = ["ci", "unit", "quality"]                              # `check`: quick, before a PR is marked ready
WALKTHROUGH = "walkthrough"
MANUAL = "manual"
ALL_STAGES = [*STAGES, MANUAL, WALKTHROUGH]
RUNNER_DIR = {"unit": "integration", "device": "firmware"}     # stage -> its runner's directory (if renamed)
PREFIX = {"ci": "CI", "unit": "INT", "device": "FW", "page": "PAGE", "live": "LIVE", "quality": "QUAL",
          MANUAL: "MAN", WALKTHROUGH: "WALK", "ids": "IDS"}
# The slow stages start first (they set the run's length).
ORDER = ["device", "walkthrough", "page", "quality", "unit", "ci", "live"]
PYTHON_ENV = {"unit": "HA_PYTHON", "walkthrough": "HA_PYTHON", "device": "ESPHOME_PYTHON",
              "ci": "ESPHOME_PYTHON", "quality": "QUALITY_PYTHON"}
STANDARD_COMMANDS = {"brief", "log", "summary", "manual", "schema", "walkthrough-due"}

sys.path.insert(0, str(HERE))


def out_dir(stage: str) -> Path:
    return WALK_OUT if stage == WALKTHROUGH else OUT


def parse_args(argv: list[str]) -> dict:
    """Which stages to run, and how. Raises SystemExit on an unknown stage."""
    stages: list[str] = []
    check = bool(argv) and argv[0] == "check"
    i = 1 if check else 0
    while i < len(argv):
        a = argv[i]
        if a == "--stage":
            if i + 1 >= len(argv):
                raise SystemExit("--stage needs a stage name")
            stages.append(argv[i + 1])
            i += 2
            continue
        if a.startswith("--stage="):
            stages.append(a.split("=", 1)[1])
        elif not a.startswith("--"):
            stages.append(a)  # positional stage names still work
        i += 1
    bad = [s for s in stages if s not in ALL_STAGES]
    if bad:
        raise SystemExit(f"unknown stage(s): {', '.join(bad)} (stages: {', '.join(ALL_STAGES)})")
    if check:
        stages = list(CHECK)
    elif not stages:
        stages = [*STAGES, MANUAL]
    if "--with-walkthrough" in argv and WALKTHROUGH not in stages:
        stages.append(WALKTHROUGH)
    return {"stages": list(dict.fromkeys(stages)), "compile": "--compile" in argv, "serial": "--serial" in argv,
            "quiet": check or "--quiet" in argv}


def command(stage: str, compile_fw: bool) -> list[str] | None:
    d = HERE / RUNNER_DIR.get(stage, stage)
    if (d / "run.py").is_file():
        py = os.environ.get(PYTHON_ENV.get(stage, ""), "") or sys.executable
        return [py, str(d / "run.py")] + (["--compile"] if stage == "device" and compile_fw else [])
    for name in ("run.mjs", "run.js"):
        if (d / name).is_file():
            return ["node", str(d / name)]
    return None


def normalise(stage: str, path: Path) -> dict:
    """The standard's stage format: prefix, and each result's key ("<ID> <what it checks>", so catalogue regexes
    over "<stage>:<key>" can match an ID) next to this project's feature and check."""
    data = json.loads(path.read_text())
    data["stage"], data["prefix"] = stage, PREFIX.get(stage, stage.upper())
    for r in data.get("results", []):
        r.setdefault("key", f"{r['id']} {r.get('check', '')}".strip())
        r.setdefault("detail", "")
        r.setdefault("evidence", "")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return data


def run_stage(stage: str, compile_fw: bool, quiet: bool = False) -> dict | None:
    if stage == MANUAL:
        import standard  # noqa: PLC0415
        data = standard.manual_stage(quiet=True)
        normalise(MANUAL, OUT / "manual.json")
        return _counts(data)
    cmd = command(stage, compile_fw)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    if cmd is None:
        print(f"{stage}: no runner (regression/{RUNNER_DIR.get(stage, stage)}/run.py or run.js)", flush=True)
        return None
    out = out_dir(stage)
    out.mkdir(parents=True, exist_ok=True)
    if not quiet:
        print(f"{stage}: started  {' '.join(Path(c).name if i else c for i, c in enumerate(cmd))}", flush=True)
    log = out / f"{stage}.log"
    with log.open("w") as fh:
        p = subprocess.run(cmd, cwd=HERE.parent, stdout=fh, stderr=subprocess.STDOUT, check=False)
    res = out / f"{stage}.json"
    fresh = res.is_file() and res.stat().st_mtime >= t0 - 1
    if p.returncode != 0 or not fresh:
        # Keep whatever results it wrote, and add one failure saying the stage broke.
        data = json.loads(res.read_text()) if fresh else {"stage": stage, "started": started, "results": []}
        data.setdefault("results", []).append({
            "id": f"{PREFIX.get(stage, stage.upper())}-RUN", "key": "RUN", "feature": "Regression harness",
            "check": f"The {stage} stage runs", "status": "fail",
            "detail": f"exit code {p.returncode}; see {log.relative_to(HERE)}", "evidence": log.name})
        data["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        res.write_text(json.dumps(data, indent=2) + "\n")
    data = normalise(stage, res)
    if stage == WALKTHROUGH:
        publish_walkthrough(data)
    counts = _counts(data)
    if quiet:
        print(f"{stage:<12} pass {counts['pass']:>4}  fail {counts['fail']:>3}  skip {counts['skip']:>3}  "
              f"manual {counts['manual']:>3}", flush=True)
        for r in data["results"]:
            if r["status"] == "fail":
                print(f"  FAIL {r['id']} {r.get('check') or r['key']}: {str(r.get('detail', ''))[:160]}", flush=True)
    else:
        print(f"{stage}: finished {counts}  ({time.time() - t0:.0f} s)", flush=True)
    return counts


def _counts(data: dict) -> dict:
    return {s: sum(r.get("status") == s for r in data["results"]) for s in ("pass", "fail", "skip", "manual")}


def publish_walkthrough(stage: dict) -> None:
    """Copy the walkthrough's checks, inventory and screenshots to the standard's places in regression/out/
    (out/walkthrough-checks.json, out/walkthrough.json as role -> width -> menu and pages, out/walkthrough/)."""
    OUT.mkdir(exist_ok=True)
    (OUT / "walkthrough-checks.json").write_text(json.dumps({**stage, "stage": WALKTHROUGH}, indent=1) + "\n")
    inv_path = WALK_OUT / "inventory.json"
    inv = json.loads(inv_path.read_text()) if inv_path.is_file() else {}
    roles: dict = {}
    for s in inv.get("surfaces", []):
        role = s.get("persona", "?")
        width = s.get("width", "?")
        pages = [{"title": x.get("heading", ""), "screen": x.get("id", ""), "shot": x.get("shot"),
                  "buttons": x.get("buttons", []), "fields": x.get("fields", []), "folds": x.get("folds", [])}
                 for x in s.get("screens", [])]
        roles.setdefault(role, {})[width] = {"surface": s.get("surface"), "who": s.get("who"),
                                             "menu": [m.get("label") for m in s.get("menu", [])],
                                             "pages": pages, "fullpage": s.get("fullpage")}
    if inv.get("home_assistant"):
        roles.setdefault("admin", {}).setdefault("home-assistant", {"surface": "Home Assistant screens",
                                                                    "pages": (inv["home_assistant"].get("flows") or {}).get("screens", [])})
    (OUT / "walkthrough.json").write_text(json.dumps(roles, indent=1, default=str) + "\n")
    shots = OUT / "walkthrough"
    shutil.rmtree(shots, ignore_errors=True)
    if (WALK_OUT / "shots").is_dir():
        shutil.copytree(WALK_OUT / "shots", shots)


def registry_results(stages: list[str]) -> list[dict]:
    """One check per stage that ran: every ID it reported is registered, every live registered ID reported."""
    import ids  # noqa: PLC0415

    results = []
    for n, stage in enumerate(["unit", "ci", "device", "page", "live", "quality", WALKTHROUGH, MANUAL], 1):
        if stage not in stages or not (out_dir(stage) / f"{stage}.json").is_file():
            continue
        unregistered, missing = ids.compare(stage, out_dir(stage))
        detail = "; ".join(x for x in (
            f"not registered: {', '.join(unregistered)} (python3 regression/ids.py sync {stage})" if unregistered else "",
            f"registered but not reported (retire them, never delete): {', '.join(missing)}" if missing else "") if x)
        check = (f"Every {stage} check ID is in the committed registry, and every registered {stage} ID is still "
                 "reported or marked retired")
        results.append({"id": f"IDS-{n:03d}", "key": f"IDS-{n:03d} {check}", "feature": "Regression harness: stable check IDs",
                        "check": check, "status": "fail" if detail else "pass", "detail": detail, "evidence": ""})
    return results


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in STANDARD_COMMANDS:
        import standard  # noqa: PLC0415
        return standard.main(argv) or 0
    if argv and argv[0] == "report":
        script = HERE / ("walkthrough/report.py" if "--walkthrough" in argv else "report.py")
        return subprocess.run([sys.executable, str(script)], check=False).returncode
    opts = parse_args(argv)
    stages = opts["stages"]
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    regular = [s for s in stages if s != MANUAL]
    if opts["serial"]:
        done = {stage: run_stage(stage, opts["compile"], opts["quiet"]) for stage in regular}
    else:
        order = sorted(regular, key=lambda s: ORDER.index(s) if s in ORDER else 99)
        with ThreadPoolExecutor(max_workers=max(1, len(order))) as pool:
            futures = {stage: pool.submit(run_stage, stage, opts["compile"], opts["quiet"]) for stage in order}
        done = {stage: futures[stage].result() for stage in regular}
    if MANUAL in stages:  # after the stages: records per version, nothing to run
        done[MANUAL] = run_stage(MANUAL, False, opts["quiet"])
    regs = registry_results(stages)
    for d in (OUT, WALK_OUT):
        mine = [r for r in regs if (r["check"].startswith(f"Every {WALKTHROUGH} ")) == (d == WALK_OUT)]
        if mine:
            d.mkdir(parents=True, exist_ok=True)
            (d / "ids.json").write_text(json.dumps({"stage": "ids", "prefix": "IDS", "results": mine}, indent=2) + "\n")
    summary = {stage: counts for stage, counts in done.items() if counts is not None}
    bad_ids = [r["id"] for r in regs if r["status"] == "fail"]
    fails = sum(c["fail"] for c in summary.values()) + len(bad_ids)
    if opts["quiet"]:
        if bad_ids:
            print("ID registry problems: " + ", ".join(bad_ids))
        print("check: " + ("passed" if not fails else f"{fails} failing check(s); logs in regression/out/"))
    else:
        print(f"all stages: {time.time() - t0:.0f} s" + (f"; ID registry problems: {', '.join(bad_ids)}" if bad_ids else ""))
        print(json.dumps(summary))
    return 1 if (opts["quiet"] and fails) else 0


if __name__ == "__main__":
    sys.exit(main())
