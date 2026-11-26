"""Firmware checks that need a person with the hardware (status "manual").

The checklist itself is regression/manual.yaml (every stage's manual checks); this returns the firmware
ones. Nothing here is run automatically: it would tap, light, sound, update or restart a device.
"""

from pathlib import Path

import yaml

CHECKLIST = Path(__file__).resolve().parents[1] / "manual.yaml"


def items(stage: str) -> list[dict]:
    return [i for i in yaml.safe_load(CHECKLIST.read_text()) or [] if i.get("stage") == stage]


MANUAL = [(i["id"], i["feature"], i["check"], i["steps"]) for i in items("firmware")]


def results() -> list[dict]:
    return [dict(id=i, feature=f, check=c, status="manual", detail=steps) for i, f, c, steps in MANUAL]
