#!/usr/bin/env python3
"""Run the regression stages (and optionally the walkthrough) and write their results.

Usage:
  python3 regression/run.py                        # every regression stage
  python3 regression/run.py --stage page           # one stage (repeat --stage for more)
  python3 regression/run.py --with-walkthrough     # the regression stages and the walkthrough
  python3 regression/run.py --stage walkthrough    # the walkthrough only
  python3 regression/run.py --compile              # also compile every firmware (slow: ~20 min cold)
  python3 regression/run.py --serial               # one stage at a time (default: all at once)

Regression stages: integration, ci, firmware, page, live, quality. Each writes regression/out/<stage>.json.
The walkthrough writes to its own directory (regression/walkthrough/out/), uses its own local server and
browser contexts, and never touches regression/out/, so both can run at once without colliding.

The stages are independent, so they run at the same time: the run takes as long as the slowest stage
instead of the sum. A stage that crashes still gets a result file, with one failing result saying so.
After the stages, regression/out/ids.json records whether every reported check ID is in the committed
registry (regression/ids/, see ids.py). Environment the stages read:

  HA_PYTHON        python with pytest-homeassistant-custom-component (integration and walkthrough)
  ESPHOME_PYTHON   python with esphome and esptool (firmware and ci stages)
  QUALITY_PYTHON   python with ruff, bandit, pip-audit, pytest (quality; installed on first use otherwise)
  HA_URL, HA_TOKEN Home Assistant for the live stage and the walkthrough's entity list (read-only)

Then build the reports: python3 regression/report.py and python3 regression/walkthrough/report.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
WALK_OUT = HERE / "walkthrough" / "out"
STAGES = ["integration", "ci", "firmware", "page", "live", "quality"]   # the regression stages (the default)
WALKTHROUGH = "walkthrough"
ALL_STAGES = [*STAGES, WALKTHROUGH]
# The slow stages start first (they set the run's length).
ORDER = ["firmware", "walkthrough", "page", "quality", "integration", "ci", "live"]
PYTHON_ENV = {"integration": "HA_PYTHON", "walkthrough": "HA_PYTHON", "firmware": "ESPHOME_PYTHON",
              "ci": "ESPHOME_PYTHON", "quality": "QUALITY_PYTHON"}


def out_dir(stage: str) -> Path:
    return WALK_OUT if stage == WALKTHROUGH else OUT


def parse_args(argv: list[str]) -> dict:
    """Which stages to run, and how. Raises SystemExit on an unknown stage."""
    stages: list[str] = []
    i = 0
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
    if not stages:
        stages = list(STAGES)
    if "--with-walkthrough" in argv and WALKTHROUGH not in stages:
        stages.append(WALKTHROUGH)
    return {"stages": list(dict.fromkeys(stages)), "compile": "--compile" in argv, "serial": "--serial" in argv}


def command(stage: str, compile_fw: bool) -> list[str] | None:
    d = HERE / stage
    if (d / "run.py").is_file():
        py = os.environ.get(PYTHON_ENV.get(stage, ""), "") or sys.executable
        return [py, str(d / "run.py")] + (["--compile"] if stage == "firmware" and compile_fw else [])
    for name in ("run.mjs", "run.js"):
        if (d / name).is_file():
            return ["node", str(d / name)]
    return None


def run_stage(stage: str, compile_fw: bool) -> dict | None:
    cmd = command(stage, compile_fw)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    if cmd is None:
        print(f"{stage}: no runner (regression/{stage}/run.py or run.js)", flush=True)
        return None
    out = out_dir(stage)
    out.mkdir(parents=True, exist_ok=True)
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
            "id": f"{stage.upper()[:4]}-RUN", "feature": "Regression harness", "check": f"The {stage} stage runs",
            "status": "fail", "detail": f"exit code {p.returncode}; see {log.relative_to(HERE)}", "evidence": log.name})
        data["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        res.write_text(json.dumps(data, indent=2) + "\n")
    data = json.loads(res.read_text())
    counts = {s: sum(r.get("status") == s for r in data["results"]) for s in ("pass", "fail", "skip", "manual")}
    print(f"{stage}: finished {counts}  ({time.time() - t0:.0f} s)", flush=True)
    return counts


def registry_results(stages: list[str]) -> list[dict]:
    """One check per stage that ran: every ID it reported is registered, every live registered ID reported."""
    sys.path.insert(0, str(HERE))
    import ids  # noqa: PLC0415

    results = []
    for n, stage in enumerate(ALL_STAGES, 1):
        if stage not in stages or not (out_dir(stage) / f"{stage}.json").is_file():
            continue
        unregistered, missing = ids.compare(stage, out_dir(stage))
        detail = "; ".join(x for x in (
            f"not registered: {', '.join(unregistered)} (python3 regression/ids.py sync {stage})" if unregistered else "",
            f"registered but not reported (retire them, never delete): {', '.join(missing)}" if missing else "") if x)
        results.append({"id": f"IDS-{n:03d}", "feature": "Regression harness: stable check IDs",
                         "check": f"Every {stage} check ID is in the committed registry, and every registered "
                                  f"{stage} ID is still reported or marked retired",
                         "status": "fail" if detail else "pass", "detail": detail})
    return results


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(sys.argv[1:] if argv is None else argv)
    stages = opts["stages"]
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    if opts["serial"]:
        done = [run_stage(stage, opts["compile"]) for stage in stages]
    else:
        order = sorted(stages, key=lambda s: ORDER.index(s) if s in ORDER else 99)
        with ThreadPoolExecutor(max_workers=len(order)) as pool:
            futures = {stage: pool.submit(run_stage, stage, opts["compile"]) for stage in order}
        done = [futures[stage].result() for stage in stages]
    regs = registry_results(stages)
    for d, name in ((OUT, "ids"), (WALK_OUT, "ids")):
        mine = [r for r in regs if (r["id"] == f"IDS-{ALL_STAGES.index(WALKTHROUGH) + 1:03d}") == (d == WALK_OUT)]
        if mine:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.json").write_text(json.dumps({"stage": "ids", "results": mine}, indent=2) + "\n")
    summary = {stage: counts for stage, counts in zip(stages, done, strict=True) if counts is not None}
    bad_ids = [r["id"] for r in regs if r["status"] == "fail"]
    print(f"all stages: {time.time() - t0:.0f} s" + (f"; ID registry problems: {', '.join(bad_ids)}" if bad_ids else ""))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
