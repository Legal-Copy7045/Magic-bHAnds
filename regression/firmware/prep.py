"""Prepare a scratch copy of the device files the way CI builds them.

Everything is written under regression/out/firmware-work/ (git-ignored), never
into esphome/. Each device gets a plain and a signed variant:

  bridge      magicband-bridge.yaml (as-is; the add-on is already !include)
  reader      magicband-reader.yaml with CI's two sed substitutions
  bp2         screek-bp2-poe.yaml with CI's sed substitution
  standalone  screek-bp2-poe-standalone.yaml with the component source local

The signed variants go through .github/scripts/signed_build.py exactly as CI.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ESPHOME_DIR = REPO / "esphome"
COMPONENTS = REPO / "components"
OUT = REPO / "regression" / "out"
WORK = OUT / "firmware-work"
VENV = Path(os.environ.get("ESPHOME_VENV", "/tmp/claude-0/esphvenv"))
# Prefer the esphome next to the running Python (run.py re-runs itself under the venv, or ESPHOME_PYTHON), then the venv, then PATH.
_HERE_BIN = Path(sys.executable).parent / "esphome"
ESPHOME = str(_HERE_BIN if _HERE_BIN.exists() else VENV / "bin" / "esphome" if (VENV / "bin" / "esphome").exists()
              else shutil.which("esphome") or "esphome")
PYTHON = sys.executable if _HERE_BIN.exists() else str(VENV / "bin" / "python") if (VENV / "bin" / "python").exists() else sys.executable

DEVICES = {
    "bridge": "magicband-bridge.yaml",
    "reader": "magicband-reader.yaml",
    "bp2": "screek-bp2-poe.yaml",
    "standalone": "screek-bp2-poe-standalone.yaml",
}


def _sub_reader(text: str, work: Path) -> str:
    text = re.sub(r"magicband: github://.*magicband-addon\.yaml@main", "magicband: !include magicband-addon.yaml", text)
    return text.replace("https://raw.githubusercontent.com/Legal-Copy7045/Magic-bHAnds/main/esphome/sounds/", "sounds/")


def _sub_bp2(text: str, work: Path) -> str:
    return re.sub(r"magicband: github://.*magicband-addon\.yaml@main", "magicband: !include magicband-addon.yaml", text)


def _sub_standalone(text: str, work: Path) -> str:
    return text.replace("source: github://Legal-Copy7045/Magic-bHAnds@main", f"source: {work / 'components'}")


SUBS = {"bridge": lambda t, w: t, "reader": _sub_reader, "bp2": _sub_bp2, "standalone": _sub_standalone}


def prepare(work: Path = WORK) -> dict[str, dict[str, Path]]:
    """Return {device: {"plain": path, "signed": path}} inside <work>/esphome."""
    edir = work / "esphome"
    edir.mkdir(parents=True, exist_ok=True)
    for name in ("magicband-addon.yaml", "firmware-signing-key.pub.pem"):
        shutil.copy2(ESPHOME_DIR / name, edir / name)
    if (edir / "sounds").exists():
        shutil.rmtree(edir / "sounds")
    shutil.copytree(ESPHOME_DIR / "sounds", edir / "sounds")
    comp = work / "components"
    if comp.exists():
        shutil.rmtree(comp)
    shutil.copytree(COMPONENTS, comp, ignore=shutil.ignore_patterns("__pycache__"))
    files: dict[str, dict[str, Path]] = {}
    for dev, src in DEVICES.items():
        text = SUBS[dev]((ESPHOME_DIR / src).read_text(), work)
        plain = edir / f"{dev}-plain.yaml"
        plain.write_text(text)
        signed = edir / f"{dev}-signed.yaml"
        r = subprocess.run([sys.executable, str(REPO / ".github/scripts/signed_build.py"), str(plain), str(signed)],
                           capture_output=True, text=True)
        files[dev] = {"plain": plain, "signed": signed if r.returncode == 0 else None,
                      "signed_error": (r.stdout + r.stderr).strip() if r.returncode else ""}
    return files


def esphome_cmd(*args: str) -> list[str]:
    return [ESPHOME, "-s", "component_source", "../components", *args]


if __name__ == "__main__":
    for d, v in prepare().items():
        print(d, v)
