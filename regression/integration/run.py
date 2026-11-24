#!/usr/bin/env python3
"""Regression stage "integration": pytest over tests/ (the Home Assistant integration) -> out/integration.json.

Usage (from the test venv, the one with pytest-homeassistant-custom-component):

    python regression/integration/run.py [--python /path/to/python] [extra pytest args]

Writes regression/out/integration-junit.xml (JUnit), regression/out/integration-tests.jsonl (raw outcomes)
and regression/out/integration.json (the stage result, README.md format).

IDs: every test (each parametrised case too) has a stable INT- ID in regression/integration/test_ids.yaml.
A test not in that file yet gets the next free number, appended to the file (commit it). IDs are never
renumbered or reused: if a test is renamed, edit its line in test_ids.yaml to keep its ID; a removed test's
line stays and shows as a `skip` ("no longer exists") until the line is deleted, and its number is not
given out again (the file records the highest number issued).

Outcomes: passed -> pass; failed/error -> fail; skipped -> skip; xfail (a test marked as a known product
bug) -> fail, with the bug in `detail`; an unexpected pass of a non-strict known bug -> pass, with a note to
remove the marker. The feature for each result comes from regression/catalogue/integration.yaml.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "regression" / "out"
IDS = HERE / "test_ids.yaml"
CATALOGUE = REPO / "regression" / "catalogue" / "integration.yaml"
_LINE = re.compile(r'^(INT-\d{3,})\s*:\s*"(.*)"\s*$')
_HIGHEST = re.compile(r"^# highest issued:\s*INT-(\d+)\s*$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_ids() -> tuple[dict[str, str], int]:
    """nodeid -> INT id, and the highest number ever issued."""
    ids: dict[str, str] = {}
    highest = 0
    if IDS.is_file():
        for line in IDS.read_text(encoding="utf-8").splitlines():
            if m := _HIGHEST.match(line):
                highest = max(highest, int(m.group(1)))
            elif m := _LINE.match(line):
                nodeid = json.loads(f'"{m.group(2)}"')
                ids[nodeid] = m.group(1)
                highest = max(highest, int(m.group(1)[4:]))
    return ids, highest


def save_ids(ids: dict[str, str], highest: int) -> None:
    lines = [
        "# Stable IDs for the integration tests (regression/integration/run.py). Append-only: never renumber or",
        "# reuse an ID. Renamed a test? Edit its line here to keep its ID.",
        f"# highest issued: INT-{highest:03d}",
    ]
    for nodeid, check_id in sorted(ids.items(), key=lambda kv: int(kv[1][4:])):
        lines.append(f"{check_id}: {json.dumps(nodeid)}")
    IDS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_features() -> dict[str, list[str]]:
    """INT id -> the catalogue features that list it."""
    features: dict[str, list[str]] = {}
    if not CATALOGUE.is_file():
        return features
    try:
        import yaml  # noqa: PLC0415 - in the HA test venv
    except ImportError:
        return features
    for item in yaml.safe_load(CATALOGUE.read_text(encoding="utf-8")) or []:
        for check in item.get("checks") or []:
            features.setdefault(str(check), []).append(item.get("feature", ""))
    return features


def humanise(nodeid: str, doc: str) -> str:
    if doc:
        return doc
    name = nodeid.split("::")[-1]
    param = ""
    if "[" in name:
        name, param = name.split("[", 1)
        param = f" [{param.rstrip(']')}]"
    words = name.removeprefix("test_").replace("_", " ")
    return words[:1].upper() + words[1:] + param


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", default=sys.executable, help="interpreter with the HA test framework")
    args, extra = parser.parse_known_args()
    OUT.mkdir(parents=True, exist_ok=True)
    junit, raw = OUT / "integration-junit.xml", OUT / "integration-tests.jsonl"
    raw.unlink(missing_ok=True)
    started = _now()
    env = {**os.environ, "MB_REGRESSION_OUT": str(raw),
           "PYTHONPATH": os.pathsep.join(filter(None, [str(HERE), os.environ.get("PYTHONPATH", "")]))}
    cmd = [args.python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "mb_regression_plugin",
           f"--junitxml={junit}", "tests", *extra]
    proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, check=False)
    (OUT / "integration-pytest.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    summary = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]

    records: dict[str, dict] = {}
    if raw.is_file():
        for line in raw.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            prev = records.get(rec["nodeid"])
            # One record per test; a setup or teardown error outranks the call's own outcome.
            if prev is None or (rec["outcome"] == "failed" and prev["outcome"] != "failed"):
                records[rec["nodeid"]] = rec

    ids, highest = load_ids()
    for nodeid in records:
        if nodeid not in ids:
            highest += 1
            ids[nodeid] = f"INT-{highest:03d}"
    save_ids(ids, highest)
    features = load_features()

    results = []
    for nodeid, check_id in sorted(ids.items(), key=lambda kv: int(kv[1][4:])):
        rec = records.get(nodeid)
        feature = "; ".join(features.get(check_id, [])) or "(not in the catalogue)"
        result = {"id": check_id, "feature": feature, "check": humanise(nodeid, rec["doc"] if rec else ""),
                  "status": "skip", "detail": "", "evidence": f"out/integration-pytest.log ({nodeid})"}
        if rec is None:
            result["detail"] = "test no longer exists (renamed or removed? see test_ids.yaml)" if not extra else \
                "not run (pytest was given a selection)"
        elif rec["outcome"] == "passed":
            result["status"] = "pass"
        elif rec["outcome"] == "xpassed":
            result["status"] = "pass"
            result["detail"] = f"was marked as a known bug but passed: remove the xfail marker ({rec['wasxfail']})"
        elif rec["outcome"] == "xfailed":
            result["status"] = "fail"
            result["detail"] = f"Known product bug (xfail): {rec['wasxfail']}"
        elif rec["outcome"] == "failed":
            result["status"] = "fail"
            result["detail"] = (f"[{rec['when']}] " if rec["when"] != "call" else "") + rec["detail"]
        else:
            result["detail"] = rec["detail"]
        results.append(result)

    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("pass", "fail", "skip", "manual")}
    stage = {
        "stage": "integration",
        "started": started,
        "finished": _now(),
        "environment": {
            "note": "pytest over tests/ with pytest-homeassistant-custom-component; known product bugs are "
                    "xfail tests reported here as fail",
            "python": subprocess.run([args.python, "--version"], capture_output=True, text=True).stdout.strip(),
            "pytest_summary": summary,
            "pytest_exit_code": proc.returncode,
            "counts": counts,
        },
        "results": results,
    }
    (OUT / "integration.json").write_text(json.dumps(stage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"integration: {counts['pass']} pass, {counts['fail']} fail, {counts['skip']} skip ({summary})")
    print(f"-> {OUT / 'integration.json'}")
    if proc.returncode not in (0, 1):  # 1 = some tests failed; anything else = pytest itself broke
        print(proc.stdout[-3000:], proc.stderr[-3000:], sep="\n")
        return proc.returncode
    return 0  # failing checks are results, not a broken stage (regression/run.py treats exit != 0 as broken)


if __name__ == "__main__":
    sys.exit(main())
