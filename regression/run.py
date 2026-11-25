#!/usr/bin/env python3
"""Run the full regression suite (or some stages) and write regression/out/<stage>.json.

Usage:
  python3 regression/run.py                    # every stage
  python3 regression/run.py page firmware      # just these
  python3 regression/run.py --compile          # also compile every firmware (slow: ~20 min cold)
  python3 regression/run.py --serial           # one stage at a time (default: all at once)

The stages are independent (each writes its own out/<stage>.* files), so they
run at the same time; the run takes as long as the slowest stage (the
firmware compile) instead of the sum.

Each stage is regression/<stage>/run.py (or run.mjs for the page). A stage that
crashes still gets a result file, with one failing result saying so, so the
report shows it rather than leaving it out. Environment the stages read:

  HA_PYTHON        python with pytest-homeassistant-custom-component (integration stage)
  ESPHOME_PYTHON   python with esphome and esptool (firmware and ci stages)
  HA_URL, HA_TOKEN Home Assistant for the live stage (read-only; skipped without HA_URL)
  HA_EXTRA_PAGE    optional path of an embedded copy of the page to check (live stage)

Then build the report: python3 regression/report.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
STAGES = ["integration", "ci", "firmware", "page", "live"]


def command(stage: str, compile_fw: bool) -> list[str] | None:
    d = HERE / stage
    if (d / "run.py").is_file():
        py = os.environ.get("HA_PYTHON" if stage == "integration" else "ESPHOME_PYTHON" if stage in ("firmware", "ci")
                            else "", "") or sys.executable
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
        print(f"{stage}: no runner (regression/{stage}/run.py or run.mjs)", flush=True)
        return None
    print(f"{stage}: started  {' '.join(Path(c).name if i else c for i, c in enumerate(cmd))}", flush=True)
    log = OUT / f"{stage}.log"
    with log.open("w") as fh:
        p = subprocess.run(cmd, cwd=HERE.parent, stdout=fh, stderr=subprocess.STDOUT, check=False)
    res = OUT / f"{stage}.json"
    fresh = res.is_file() and res.stat().st_mtime >= t0 - 1
    if p.returncode != 0 or not fresh:
        # Keep whatever results it wrote, and add one failure saying the stage broke.
        data = json.loads(res.read_text()) if fresh else {"stage": stage, "started": started, "results": []}
        data.setdefault("results", []).append({
            "id": f"{stage.upper()[:4]}-RUN", "feature": "Regression harness", "check": f"The {stage} stage runs",
            "status": "fail", "detail": f"exit code {p.returncode}; see out/{stage}.log", "evidence": f"{stage}.log"})
        data["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        res.write_text(json.dumps(data, indent=2) + "\n")
    data = json.loads(res.read_text())
    counts = {s: sum(r.get("status") == s for r in data["results"]) for s in ("pass", "fail", "skip", "manual")}
    print(f"{stage}: finished {counts}  ({time.time() - t0:.0f} s)", flush=True)
    return counts


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    compile_fw = "--compile" in sys.argv
    stages = args or STAGES
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    if "--serial" in sys.argv:
        done = [run_stage(stage, compile_fw) for stage in stages]
    else:
        # The slow stages start first (they set the run's length).
        order = sorted(stages, key=lambda s: ["firmware", "page", "integration", "ci", "live"].index(s)
                       if s in STAGES else 9)
        with ThreadPoolExecutor(max_workers=len(order)) as pool:
            futures = {stage: pool.submit(run_stage, stage, compile_fw) for stage in order}
        done = [futures[stage].result() for stage in stages]
    summary = {stage: counts for stage, counts in zip(stages, done) if counts is not None}
    print(f"all stages: {time.time() - t0:.0f} s")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
