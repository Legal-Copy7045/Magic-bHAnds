#!/usr/bin/env python3
"""The committed registry of stable check IDs: regression/ids/<stage>.yaml.

Every ID a stage reports must be registered, and every registered ID must still be reported unless it
is marked retired. IDs are never renumbered or reused: a removed check is retired, not deleted, and a
new check takes a new number. (The integration stage keeps its own registry,
regression/integration/test_ids.yaml, which maps each ID to its pytest node.)

  python3 regression/ids.py check [stage ...]   compare out/<stage>.json with the registry
  python3 regression/ids.py sync [stage ...]    register new IDs found in out/<stage>.json (appends)

Registry format (YAML mapping, append-only):
  CI-001: "What the check checks"
  FW-206: "RETIRED (0.10.33): the image-version guard was removed"
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import yaml

HERE = Path(__file__).resolve().parent
REG = HERE / "ids"
HEADER = ("# Stable check IDs for the {stage} stage (regression/ids.py). Append-only: never renumber or reuse an\n"
          "# ID. A removed check stays here with its text starting \"RETIRED\"; a new check takes a new number.\n")
HARNESS = re.compile(r"-RUN$")  # the runner's own "stage broke" result


def registry_path(stage: str) -> Path:
    if stage == "integration":
        return HERE / "integration" / "test_ids.yaml"
    return REG / f"{stage}.yaml"


def load(stage: str) -> dict[str, str]:
    p = registry_path(stage)
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text()) or {}
    return {str(k): str(v) for k, v in data.items()}


def retired(text: str) -> bool:
    return text.upper().startswith("RETIRED")


def reported(stage: str, out: Path) -> dict[str, str]:
    p = out / f"{stage}.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text())
    return {r["id"]: r.get("check", "") for r in data.get("results", []) if not HARNESS.search(r["id"])}


def compare(stage: str, out: Path) -> tuple[list[str], list[str]]:
    """(reported but not registered, registered and live but not reported)."""
    reg, got = load(stage), reported(stage, out)
    unregistered = sorted(i for i in got if i not in reg)
    missing = sorted(i for i, t in reg.items() if i not in got and not retired(t))
    return unregistered, missing


def sync(stage: str, out: Path) -> list[str]:
    """Append the IDs out/<stage>.json reports that aren't registered yet. Returns them."""
    if stage == "integration":
        raise SystemExit("the integration registry maps IDs to tests: regression/integration/run.py assigns them")
    reg, got = load(stage), reported(stage, out)
    new = sorted((i for i in got if i not in reg), key=_key)
    if not new:
        return []
    p = registry_path(stage)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text() if p.is_file() else HEADER.format(stage=stage)
    if not text.endswith("\n"):
        text += "\n"
    text += "".join(f"{i}: {json.dumps(' '.join(got[i].split()))}\n" for i in new)
    p.write_text(text)
    return new


def _key(check_id: str):
    m = re.match(r"(.*?)(\d+)$", check_id)
    return (m.group(1), int(m.group(2))) if m else (check_id, 0)


def main(argv: list[str]) -> int:
    from run import ALL_STAGES  # noqa: PLC0415 - the runner owns the stage list

    out = HERE / "out"
    cmd, stages = (argv[0] if argv else "check"), (argv[1:] or ALL_STAGES)
    bad = 0
    for stage in stages:
        if not (out / f"{stage}.json").is_file() and not (stage == "walkthrough"):
            print(f"{stage}: no out/{stage}.json")
            continue
        if cmd == "sync":
            new = sync(stage, out)
            print(f"{stage}: registered {len(new)} new ID(s)" + (f": {', '.join(new)}" if new else ""))
        else:
            unregistered, missing = compare(stage, out)
            bad += bool(unregistered or missing)
            print(f"{stage}: {len(unregistered)} unregistered, {len(missing)} registered but not reported"
                  + (f"\n  unregistered: {unregistered}" if unregistered else "")
                  + (f"\n  missing: {missing}" if missing else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    sys.exit(main(sys.argv[1:]))
