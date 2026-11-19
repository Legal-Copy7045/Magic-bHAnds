#!/usr/bin/env python3
"""Assemble the GitHub Pages site: web installer page, firmware and manifests.

Usage: make_site.py <output dir> <product>=<esphome build dir>=<device yaml> ...

Products:
  bridge -> manifest.json and firmware/ at the site root (kept there so
            existing bridges' update checks keep working)
  reader -> reader/manifest.json and reader/firmware/
  bp2    -> bp2/manifest.json and bp2/firmware/

Each manifest serves two purposes:
  * ESP Web Tools reads `builds[].parts` to flash a new board from the browser.
  * ESPHome's http_request update platform reads `version` and `builds[].ota`
    to offer over-the-air updates in Home Assistant.
"""

import base64
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import urllib.request

REPO = Path(__file__).resolve().parents[2]
# The browser installer (ESP Web Tools) is published with the site rather than
# loaded from a CDN, so the page that flashes boards (and sees the Wi-Fi
# password) runs only code checked here. To upgrade: change both values; the
# integrity is npm's "dist.integrity" for that version.
ESP_WEB_TOOLS_VERSION = "10.4.0"
ESP_WEB_TOOLS_INTEGRITY = (
    "sha512-3pwkeFFm5Fj7UQo8SJNYK5RXrtNCpq6X9QoI6bMT4GBZWgrJqjn0YvM9ihG74BtMoSFYXfmDtkehuxe50PTMPQ=="
)
RELEASES = "https://github.com/Legal-Copy7045/Magic-bHAnds/releases"
PRODUCTS = {
    "bridge": ("MagicBand Bridge", "magicband-bridge", ""),
    "reader": ("MagicBand Reader", "magicband-reader", "reader/"),
    "bp2": ("SCREEK BP2-POE + MagicBand", "screek-bp2-poe", "bp2/"),
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


def vendor_esp_web_tools(out: Path) -> None:
    """Download ESP Web Tools from npm, check its hash, and copy its browser build to out/esp-web-tools/."""
    url = f"https://registry.npmjs.org/esp-web-tools/-/esp-web-tools-{ESP_WEB_TOOLS_VERSION}.tgz"
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    algo, _, expected = ESP_WEB_TOOLS_INTEGRITY.partition("-")
    actual = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if actual != expected:
        sys.exit(f"esp-web-tools {ESP_WEB_TOOLS_VERSION}: hash mismatch ({algo}-{actual})")
    dest = out / "esp-web-tools"
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            if not member.isfile():
                continue
            if name.startswith("package/dist/web/") and "/" not in name.removeprefix("package/dist/web/"):
                target = dest / Path(name).name
            elif name == "package/LICENSE":
                target = dest / "LICENSE"
            else:
                continue
            target.write_bytes(tar.extractfile(member).read())
    if not (dest / "install-button.js").is_file():
        sys.exit("esp-web-tools: install-button.js missing from the package")
    print(f"ESP Web Tools {ESP_WEB_TOOLS_VERSION} -> {dest}")


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    versions = set()
    for spec in sys.argv[2:]:
        product, build_dir, yaml_path = spec.split("=", 2)
        versions.add(build_product(out, product, Path(build_dir), Path(yaml_path)))
    if len(versions) != 1:
        sys.exit(f"Firmware versions differ: {sorted(versions)}")
    version = versions.pop()
    page = (REPO / "web" / "index.html").read_text().replace("{{VERSION}}", version)
    (out / "index.html").write_text(page)
    shutil.copy(REPO / "docs" / "images" / "icon.png", out / "icon.png")
    # The Waltograph font for the headings, with its readme and licence (its licence
    # asks for both to go with every copy).
    fonts = out / "fonts"
    fonts.mkdir(exist_ok=True)
    for name in ("waltograph42-light.otf", "waltograph.txt", "license.txt"):
        shutil.copy(REPO / "custom_components" / "magicband" / "frontend" / "fonts" / name, fonts / name)
    vendor_esp_web_tools(out)
    (out / ".nojekyll").write_text("")


if __name__ == "__main__":
    main()
