#!/usr/bin/env python3
"""Write a copy of a device file for the official (signed) builds.

Usage: signed_build.py <device yaml> <output yaml>

Two additions, to CI's copy only:

1. Signed updates. The firmware CI publishes only installs an update (from
   Home Assistant, the setup hotspot or any other over-the-air upload) signed
   with the project's key: ESP-IDF checks the new image's signature against
   the key that signed the running one, in esp_ota_end, before the image can
   boot. It is checked on update only, not at boot, and no eFuses are burned,
   so a USB flash still works.

2. The Wi-Fi setup hotspot, for devices that use Wi-Fi (not the Ethernet BP2).
   When the device can't reach its Wi-Fi for 2 minutes (or has none set yet)
   it starts an open access point named "<friendly name> Setup" with ESPHome's
   captive portal, where you pick a new network. The captive portal also
   accepts a firmware upload; with signed updates on, an image not signed with
   the project's key is refused, so nobody who joins can install their own
   code. The hotspot goes away as soon as the device is back on Wi-Fi.

The device files in the repository stay as they are, so a build of your own
("Take control", the standalone BP2 file) isn't locked to a key you don't
have, and doesn't get a hotspot whose upload would install anything. See
docs/security.md, "Signed updates" and "Setup hotspot".
"""

from pathlib import Path
import re
import sys

OPTIONS = {
    "CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT": "y",
    "CONFIG_SECURE_SIGNED_APPS_RSA_SCHEME": "y",
    "CONFIG_SECURE_SIGNED_ON_UPDATE_NO_SECURE_BOOT": "y",
    # CI signs the image itself (sign_firmware.py), so the build doesn't need the key.
    "CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES": "n",
}
ANCHOR = "  framework:\n    type: esp-idf\n"

# The setup hotspot (Wi-Fi devices only): open, since a password published here
# would protect nothing; it starts only after 2 minutes without Wi-Fi.
WIFI = "wifi:\n"
AP = ('  ap:\n'
      '    ssid: "${friendly_name} Setup"\n'
      '    ap_timeout: 2min\n')
PORTAL = "\n# Setup hotspot page (official signed builds only; see signed_build.py).\ncaptive_portal:\n"


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    text = src.read_text()
    if text.count(ANCHOR) != 1 or "sdkconfig_options:" in text:
        sys.exit(f"{src}: expected one 'framework: type: esp-idf' block and no sdkconfig_options")
    block = "    sdkconfig_options:\n" + "".join(f"      {k}: {v}\n" for k, v in OPTIONS.items())
    text = text.replace(ANCHOR, ANCHOR + block)
    wifi = re.findall(r"^wifi:[ \t]*(?:#.*)?$", text, re.M)
    if wifi:
        if len(wifi) != 1 or not re.search(r"^wifi:\n", text, re.M):
            sys.exit(f"{src}: expected one top-level 'wifi:' line")
        if re.search(r"^(captive_portal|ethernet):", text, re.M) or re.search(r"^  ap:", text, re.M):
            sys.exit(f"{src}: already has captive_portal, ethernet or a wifi ap")
        text = re.sub(r"^wifi:\n", WIFI + AP, text, count=1, flags=re.M)
        text = text.rstrip("\n") + "\n" + PORTAL
    out.write_text(text)


if __name__ == "__main__":
    main()
