#!/usr/bin/env python3
"""Fail if esphome/screek-bp2-poe-standalone.yaml drifts from the shared add-on.

The standalone file has the MagicBand parts copied in (so it can be pasted
into the Device Builder). It must resolve to exactly the same device as
esphome/screek-bp2-poe.yaml, which pulls them from magicband-addon.yaml - the
same file the MagicBand Bridge uses.

Run from esphome/ (no secrets needed).
"""

import json
from pathlib import Path
import subprocess
import sys

import yaml

HERE = Path.cwd()
COMPONENTS = str((HERE / "../components").resolve())


def resolved(path: Path) -> dict:
    out = subprocess.run(
        ["esphome", "-s", "component_source", COMPONENTS, "config", str(path)],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        sys.exit(f"esphome config failed for {path}:\n{out.stdout}\n{out.stderr}")

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_multi_constructor(
        "!", lambda l, suf, n: {"!" + suf: l.construct_scalar(n) if isinstance(n, yaml.ScalarNode) else None}
    )
    text = "".join(line for line in out.stdout.splitlines(True) if not line.startswith(("INFO", "WARNING")))
    data = yaml.load(text, Loader=Loader)
    for key in ("substitutions", "packages", "external_components"):
        data.pop(key, None)
    return data


def norm(x):
    if isinstance(x, dict):
        return {k: norm(v) for k, v in sorted(x.items())}
    if isinstance(x, list):
        return sorted((norm(i) for i in x), key=lambda i: json.dumps(i, sort_keys=True, default=str))
    return x


def main() -> None:
    standalone = HERE / "bp2-standalone-ci.yaml"
    standalone.write_text(
        (HERE / "screek-bp2-poe-standalone.yaml").read_text().replace(
            "source: github://Legal-Copy7045/Magic-bHAnds@main", f"source: {COMPONENTS}"
        )
    )
    package = HERE / "bp2-package-ci.yaml"
    package.write_text(
        (HERE / "screek-bp2-poe.yaml").read_text().replace(
            "magicband: github://Legal-Copy7045/Magic-bHAnds/esphome/magicband-addon.yaml@main",
            "magicband: !include magicband-addon.yaml",
        )
    )
    stub = HERE / "bp2-stub-ci.yaml"
    stub.write_text(
        "substitutions:\n  name: screek-bp2-poe-849a4c\n  friendly_name: SCREEK BP2-POE 849a4c\n"
        "packages:\n  bp2: !include bp2-package-ci.yaml\nesphome:\n  name_add_mac_suffix: false\n"
    )
    a, b = norm(resolved(standalone)), norm(resolved(stub))
    if a != b:
        sys.exit(
            "screek-bp2-poe-standalone.yaml no longer matches screek-bp2-poe.yaml + "
            "magicband-addon.yaml. Copy the add-on changes into the standalone file."
        )
    print("BP2-POE standalone config matches the shared MagicBand add-on.")


if __name__ == "__main__":
    main()
