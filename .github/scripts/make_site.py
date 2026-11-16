#!/usr/bin/env python3
"""Assemble the GitHub Pages site: web installer page, firmware and manifests.

Usage: make_site.py <output dir> <product>=<esphome build dir>=<device yaml> ...

Products:
  bridge -> manifest.json and firmware/ at the site root (kept there so
            existing bridges' update checks keep working)
  reader -> reader/manifest.json and reader/firmware/

Each manifest serves two purposes:
  * ESP Web Tools reads `builds[].parts` to flash a new board from the browser.
  * ESPHome's http_request update platform reads `version` and `builds[].ota`
    to offer over-the-air updates in Home Assistant.
"""

import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
RELEASES = "https://github.com/Legal-Copy7045/Magic-bHAnds/releases"
PRODUCTS = {
    "bridge": ("MagicBand Bridge", "magicband-bridge", ""),
    "reader": ("MagicBand Reader", "magicband-reader", "reader/"),
}


def project_version(yaml_path: Path) -> str:
    m = re.search(r'^\s*project_version:\s*"?([^"\s]+)"?', yaml_path.read_text(), re.M)
    if not m:
        sys.exit(f"project_version substitution not found in {yaml_path}")
    return m.group(1)


def build_product(out: Path, product: str, build_dir: Path, yaml_path: Path) -> str:
    title, slug, sub = PRODUCTS[product]
    version = project_version(yaml_path)
    factory, ota = build_dir / "firmware.factory.bin", build_dir / "firmware.ota.bin"
    for f in (factory, ota):
        if not f.is_file():
            sys.exit(f"missing build output: {f}")
    base = out / sub
    (base / "firmware").mkdir(parents=True, exist_ok=True)
    shutil.copy(factory, base / "firmware" / f"{slug}.factory.bin")
    shutil.copy(ota, base / "firmware" / f"{slug}.ota.bin")
    manifest = {
        "name": title,
        "version": version,
        "home_assistant_domain": "esphome",
        "new_install_prompt_erase": True,
        "builds": [
            {
                "chipFamily": "ESP32-S3",
                "parts": [{"path": f"firmware/{slug}.factory.bin", "offset": 0}],
                "ota": {
                    "path": f"firmware/{slug}.ota.bin",
                    "md5": hashlib.md5(ota.read_bytes()).hexdigest(),
                    "summary": f"{title} {version}",
                    "release_url": f"{RELEASES}/tag/v{version}",
                },
            }
        ],
    }
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{title} {version} -> {base}")
    return version


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    versions = set()
    for spec in sys.argv[2:]:
        product, build_dir, yaml_path = spec.split("=", 2)
        versions.add(build_product(out, product, Path(build_dir), Path(yaml_path)))
    if len(versions) != 1:
        sys.exit(f"Bridge and reader versions differ: {sorted(versions)}")
    version = versions.pop()
    page = (REPO / "web" / "index.html").read_text().replace("{{VERSION}}", version)
    (out / "index.html").write_text(page)
    shutil.copy(REPO / "docs" / "images" / "icon.png", out / "icon.png")
    (out / ".nojekyll").write_text("")


if __name__ == "__main__":
    main()
