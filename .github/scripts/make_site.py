#!/usr/bin/env python3
"""Assemble the GitHub Pages site: web installer page, firmware and manifest.

Usage: make_site.py <esphome build dir> <device yaml> <output dir>

The manifest serves two purposes:
  * ESP Web Tools reads `builds[].parts` to flash a new board from the browser.
  * ESPHome's http_request update platform reads `version` and
    `builds[].ota` to offer over-the-air updates in Home Assistant.
"""

import hashlib
import json
from pathlib import Path
import re
import shutil
import sys


def main() -> None:
    build_dir, yaml_path, out_dir = (Path(p) for p in sys.argv[1:4])
    repo_root = Path(__file__).resolve().parents[2]

    yaml_text = yaml_path.read_text()
    m = re.search(r'^\s*project_version:\s*"?([^"\s]+)"?', yaml_text, re.M)
    if not m:
        sys.exit("project_version substitution not found in " + str(yaml_path))
    version = m.group(1)

    factory = build_dir / "firmware.factory.bin"
    ota = build_dir / "firmware.ota.bin"
    for f in (factory, ota):
        if not f.is_file():
            sys.exit(f"missing build output: {f}")

    out_dir.mkdir(parents=True, exist_ok=True)
    fw_dir = out_dir / "firmware"
    fw_dir.mkdir(exist_ok=True)
    shutil.copy(factory, fw_dir / "magicband-bridge.factory.bin")
    shutil.copy(ota, fw_dir / "magicband-bridge.ota.bin")

    manifest = {
        "name": "MagicBand Bridge",
        "version": version,
        "home_assistant_domain": "esphome",
        "new_install_prompt_erase": True,
        "builds": [
            {
                "chipFamily": "ESP32-S3",
                "parts": [
                    {"path": "firmware/magicband-bridge.factory.bin", "offset": 0}
                ],
                "ota": {
                    "path": "firmware/magicband-bridge.ota.bin",
                    "md5": hashlib.md5(ota.read_bytes()).hexdigest(),
                    "summary": f"MagicBand Bridge {version}",
                    "release_url": "https://github.com/Legal-Copy7045/Magic-bHAnds",
                },
            }
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    page = (repo_root / "web" / "index.html").read_text().replace("{{VERSION}}", version)
    (out_dir / "index.html").write_text(page)
    (out_dir / ".nojekyll").write_text("")
    print(f"Site for version {version} written to {out_dir}")


if __name__ == "__main__":
    main()
