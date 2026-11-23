#!/usr/bin/env python3
"""Write a copy of a device file with signed updates switched on, for the official builds.

Usage: signed_build.py <device yaml> <output yaml>

The firmware CI publishes only installs an update (from Home Assistant or any
other over-the-air upload) signed with the project's key: ESP-IDF checks the
new image's signature against the key that signed the running one. It is
checked on update only, not at boot, and no eFuses are burned, so a USB flash
still works. The device files in the repository stay as they are, so a build of
your own ("Take control", the standalone BP2 file) isn't locked to a key you
don't have. See docs/security.md, "Signed updates".
"""

from pathlib import Path
import sys

OPTIONS = {
    "CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT": "y",
    "CONFIG_SECURE_SIGNED_APPS_RSA_SCHEME": "y",
    "CONFIG_SECURE_SIGNED_ON_UPDATE_NO_SECURE_BOOT": "y",
    # CI signs the image itself (sign_firmware.py), so the build doesn't need the key.
    "CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES": "n",
}
ANCHOR = "  framework:\n    type: esp-idf\n"


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    text = src.read_text()
    if text.count(ANCHOR) != 1 or "sdkconfig_options:" in text:
        sys.exit(f"{src}: expected one 'framework: type: esp-idf' block and no sdkconfig_options")
    block = "    sdkconfig_options:\n" + "".join(f"      {k}: {v}\n" for k, v in OPTIONS.items())
    out.write_text(text.replace(ANCHOR, ANCHOR + block))


if __name__ == "__main__":
    main()
