#!/usr/bin/env python3
"""Sign the official firmware builds with the project's key, in place.

Usage: sign_firmware.py <private key file> <public key file> <esphome build dir> ...

For each build dir (holding firmware.ota.bin and firmware.factory.bin):
  * signs the app image (firmware.ota.bin) with espsecure (Secure Boot V2
    scheme, RSA-3072), which appends a signature sector;
  * checks the signature against the public key committed in the repository
    (esphome/firmware-signing-key.pub.pem), so a wrong key in the secret fails
    the build instead of publishing firmware the devices would refuse;
  * rebuilds firmware.factory.bin (bootloader, partition table and otadata
    from the build, then the signed app at 0x10000) for the web installer.

The firmware itself is built with signed updates on (signed_build.py).
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

APP_OFFSET = 0x10000
ESPSECURE = shutil.which("espsecure") or sys.exit("espsecure not found (pip install esptool)")


def run(*args: str) -> None:
    out = subprocess.run([ESPSECURE, *args], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        sys.exit(f"espsecure {args[0]} failed:\n{out.stdout}\n{out.stderr}")


def sign(key: Path, pub: Path, build: Path) -> None:
    ota, factory = build / "firmware.ota.bin", build / "firmware.factory.bin"
    app, image = ota.read_bytes(), factory.read_bytes()
    if image[APP_OFFSET:APP_OFFSET + len(app)] != app or len(image) != APP_OFFSET + len(app):
        sys.exit(f"{build}: the factory image doesn't end with the app at 0x{APP_OFFSET:x}")
    if len(app) % 0x10000:
        sys.exit(f"{build}: the app isn't padded to 64 KB (built without signed updates?)")
    with tempfile.TemporaryDirectory() as tmp:
        signed = Path(tmp) / "signed.bin"
        run("sign-data", "--version", "2", "--keyfile", str(key), "--output", str(signed), str(ota))
        run("verify-signature", "--version", "2", "--keyfile", str(pub), str(signed))
        data = signed.read_bytes()
    if data[: len(app)] != app or len(data) != len(app) + 0x1000:
        sys.exit(f"{build}: unexpected signed image layout")
    ota.write_bytes(data)
    factory.write_bytes(image[:APP_OFFSET] + data)
    print(f"signed {build} ({len(app)} + {len(data) - len(app)} bytes)")


def main() -> None:
    key, pub, *builds = (Path(a) for a in sys.argv[1:])
    if not builds:
        sys.exit(__doc__)
    if not pub.is_file():
        sys.exit(f"public key {pub} missing")
    for build in builds:
        sign(key, pub, build)


if __name__ == "__main__":
    main()
