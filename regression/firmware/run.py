#!/usr/bin/env python3
"""Firmware stage of the regression suite: one command for everything.

    python3 regression/firmware/run.py              # config + host tests + manual list
    python3 regression/firmware/run.py --compile    # also compile bridge, reader and BP2 as CI does
    python3 regression/firmware/run.py --compile --clean-build   # from scratch (~2 min per device, warm toolchain)

Writes regression/out/firmware.json (see regression/README.md). Needs ESPHome
2026.10.2 (venv at $ESPHOME_VENV, default /tmp/claude-0/esphvenv, or on PATH),
g++ and, for the page comparison, node. Exits non-zero only if the harness
itself breaks; product failures are results.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = Path(os.environ.get("ESPHOME_VENV", "/tmp/claude-0/esphvenv"))


def ensure_python() -> None:
    """Re-run under the ESPHome venv's Python if this one can't import esphome."""
    try:
        import esphome  # noqa: F401
        import aioesphomeapi  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        py = VENV / "bin" / "python"
        if py.exists() and Path(sys.prefix).resolve() != VENV.resolve():
            os.execv(str(py), [str(py), *sys.argv])
        sys.exit("ESPHome isn't importable: set ESPHOME_VENV or install esphome==2026.10.2")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compile", action="store_true", help="also compile the three signed firmware builds")
    ap.add_argument("--clean-build", action="store_true", help="with --compile: delete the previous build first (full rebuild)")
    ap.add_argument("--only", default="config,host,manual", help="comma list of parts: config,host,manual")
    args = ap.parse_args()
    ensure_python()
    sys.path.insert(0, str(HERE))
    import prep

    started = now()
    parts = set(args.only.split(","))
    results, broken = [], []

    def part(name, fn):
        try:
            results.extend(fn())
        except Exception:  # the harness broke: record it and keep going
            broken.append(name)
            results.append(dict(id=f"FW-HARNESS-{name}", feature="Firmware stage harness", check=f"{name} part ran",
                                status="fail", detail=traceback.format_exc()[-2500:]))

    if "config" in parts:
        import config_checks
        part("config", config_checks.run)
    if "host" in parts:
        import host_tests
        part("host", host_tests.run)
    if "manual" in parts:
        import manual
        part("manual", manual.results)
    import compile as fwcompile
    if args.compile:
        part("compile", lambda: fwcompile.run(list(fwcompile.IDS), clean=args.clean_build))
    else:
        for dev, ids in fwcompile.IDS.items():
            for i in ids:
                results.append(dict(id=i, feature=fwcompile.FEATURE[dev], check="Compile and image checks (run with --compile)",
                                    status="skip", detail="not compiled in this run: add --compile (about 2 min per device with a warm toolchain cache)"))

    def ver(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip().splitlines()[0]
        except Exception:
            return "unavailable"

    env = {
        "esphome": ver([prep.ESPHOME, "version"]),
        "cxx": ver([os.environ.get("CXX", "g++"), "--version"]),
        "node": ver(["node", "--version"]) if shutil.which("node") else "not installed",
        "python": platform.python_version(),
        "compiled": bool(args.compile),
        "note": "Config checks resolve copies of esphome/*.yaml made the way CI builds them (out/firmware-config); "
                "host tests use mocks of ESPHome's Color/ESPColorView plus ESPHome's real posix_tz.cpp, under ASan/UBSan.",
    }
    if broken:
        env["harness_errors"] = broken
    results.sort(key=lambda r: (r["id"].split("-")[0], r["id"]))
    out = prep.OUT / "firmware.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"stage": "firmware", "started": started, "finished": now(), "environment": env, "results": results}, indent=1))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"firmware: {len(results)} results {counts} -> {out}")
    for r in results:
        if r["status"] == "fail":
            print(f"  FAIL {r['id']} {r['check'][:100]}\n       {str(r.get('detail'))[:300]}")
    return 2 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
