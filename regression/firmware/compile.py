"""Compile the three signed variants as CI does and check the app images.

For each of bridge, reader and bp2 (signed variant from prep.py):
  * `esphome -s component_source ../components compile <device>-signed.yaml`
  * firmware.ota.bin size is a multiple of 64 KB (signed updates pad the app,
    sign_firmware.py refuses otherwise)
  * the app plus the 4 KB signature sector fits the smallest app (ota_0/ota_1)
    partition from the build's partition table, with >= MARGIN free
  * firmware.factory.bin is bootloader/partitions/otadata + the app at 0x10000
  * the image carries the project version (esp_app_desc) from the device file

Writes results to out/firmware-compile.json, merged by run.py. Usable on its
own:  python3 regression/firmware/compile.py [bridge reader bp2]
"""

from __future__ import annotations

import csv
import io
import json
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prep  # noqa: E402

MARGIN = 0.10  # want at least 10 % of the app partition free after signing
APP_OFFSET = 0x10000
SIG_SECTOR = 0x1000
IDS = {  # stable result IDs per device: compile, alignment, fits, factory layout, version, sdkconfig
    "bridge": ("FW-200", "FW-201", "FW-202", "FW-203", "FW-204", "FW-205"),
    "reader": ("FW-210", "FW-211", "FW-212", "FW-213", "FW-214", "FW-215"),
    "bp2": ("FW-220", "FW-221", "FW-222", "FW-223", "FW-224", "FW-225"),
}
SECURE = ("CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT=y", "CONFIG_SECURE_SIGNED_APPS_RSA_SCHEME=y",
          "CONFIG_SECURE_SIGNED_ON_UPDATE_NO_SECURE_BOOT=y")
NOT_SET = ("CONFIG_SECURE_BOOT=y", "CONFIG_SECURE_FLASH_ENC_ENABLED=y", "CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES=y")
FEATURE = {"bridge": "Firmware build: MagicBand Bridge", "reader": "Firmware build: MagicBand Reader",
           "bp2": "Firmware build: SCREEK BP2-POE"}


def device_name(yaml_path: Path) -> str:
    m = re.search(r"^\s+name: (\S+)\s*$", yaml_path.read_text(), re.M)
    return m.group(1).strip('"') if m else ""


def partitions(build: Path) -> list[dict]:
    """Parse partitions.csv (or decode the partitions.bin) of an esp-idf build."""
    rows = []
    for csvp in [build / "partitions.csv", *build.glob("**/partitions.csv")]:
        if csvp.exists():
            for r in csv.reader(io.StringIO(csvp.read_text())):
                r = [c.strip() for c in r]
                if not r or r[0].startswith("#") or len(r) < 5:
                    continue
                rows.append({"name": r[0], "type": r[1], "subtype": r[2], "offset": int(r[3], 0) if r[3] else None,
                             "size": _size(r[4])})
            if rows:
                return rows
    for binp in build.glob("**/partition_table/partition-table.bin"):
        data = binp.read_bytes()
        for i in range(0, len(data), 32):
            e = data[i:i + 32]
            if e[:2] != b"\xaa\x50":
                break
            t, st, off, size = e[2], e[3], *struct.unpack("<II", e[4:12])
            rows.append({"name": e[12:28].rstrip(b"\0").decode(), "type": "app" if t == 0 else "data",
                         "subtype": st, "offset": off, "size": size})
        return rows
    return rows


def _size(s: str) -> int:
    s = s.strip().upper()
    if s.endswith("K"):
        return int(s[:-1], 0) * 1024
    if s.endswith("M"):
        return int(s[:-1], 0) * 1024 * 1024
    return int(s, 0)


def check_build(dev: str, yaml_path: Path, log: Path, rc: int, secs: float) -> list[dict]:
    cid, aid, fid, lid, vid, sid = IDS[dev]
    feat = FEATURE[dev]
    res = []
    name = device_name(yaml_path)
    build = yaml_path.parent / ".esphome" / "build" / name / ".pioenvs" / name
    if not build.exists():
        cands = list((yaml_path.parent / ".esphome" / "build" / name).glob("**/firmware.ota.bin"))
        build = cands[0].parent if cands else build
    ota, factory = build / "firmware.ota.bin", build / "firmware.factory.bin"
    rel = log.relative_to(prep.OUT)
    if rc != 0 or not ota.exists():
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-25:]) if log.exists() else ""
        res.append(dict(id=cid, feature=feat, check=f"Signed {dev} variant compiles as in CI", status="fail",
                        detail=f"esphome compile exit {rc} after {secs:.0f}s; ota image {'present' if ota.exists() else 'missing'}\n{tail}",
                        evidence=str(rel)))
        for i, c in ((aid, "App image is padded to 64 KB"), (fid, "Signed app fits its OTA partition with margin"),
                     (lid, "Factory image = boot/partitions + app at 0x10000"), (vid, "Image carries the project version"),
                     (sid, "Built sdkconfig has signed-on-update on, secure boot and flash encryption off")):
            res.append(dict(id=i, feature=feat, check=c, status="skip", detail="compile failed"))
        return res
    res.append(dict(id=cid, feature=feat, check=f"Signed {dev} variant compiles as in CI", status="pass",
                    detail=f"compiled in {secs:.0f}s", evidence=str(rel)))
    app = ota.read_bytes()
    n = len(app)
    res.append(dict(id=aid, feature=feat, check="App image is padded to 64 KB (signed updates on)",
                    status="pass" if n % 0x10000 == 0 else "fail", detail=f"firmware.ota.bin = {n} bytes ({n / 0x10000:.3f} x 64 KB)"))
    parts = partitions(build)
    apps = [p for p in parts if p["type"] in ("app", 0) and p["name"].startswith("app") or str(p["subtype"]).startswith("ota_")]
    if not apps:
        apps = [p for p in parts if p["type"] in ("app", 0)]
    if apps:
        smallest = min(p["size"] for p in apps)
        need = n + SIG_SECTOR
        free = smallest - need
        ok = free >= MARGIN * smallest
        res.append(dict(id=fid, feature=feat, check=f"Signed app (+4 KB signature) fits the smallest OTA partition with >= {int(MARGIN * 100)} % free",
                        status="pass" if ok else "fail",
                        detail=f"app+sig {need} bytes, partition {smallest} bytes ({', '.join(p['name'] for p in apps)}), free {free} bytes = {100 * free / smallest:.1f} %"))
    else:
        res.append(dict(id=fid, feature=feat, check="Signed app fits its OTA partition", status="fail",
                        detail=f"no app partitions found in build {build}"))
    if factory.exists():
        img = factory.read_bytes()
        ok = img[APP_OFFSET:] == app
        res.append(dict(id=lid, feature=feat, check="Factory image = bootloader/partitions/otadata + the app at 0x10000",
                        status="pass" if ok else "fail", detail=f"factory {len(img)} bytes, app {n} bytes"))
    else:
        res.append(dict(id=lid, feature=feat, check="Factory image exists", status="fail", detail="firmware.factory.bin missing"))
    # esp_app_desc_t sits right after the image header + first segment header (offset 0x20)
    want = re.search(r'project_version: "?([0-9.]+)', (prep.ESPHOME_DIR / prep.DEVICES[dev]).read_text())
    want = want.group(1) if want else None
    magic = struct.unpack("<I", app[0x20:0x24])[0] if n > 0x40 else 0
    ver = app[0x30:0x50].rstrip(b"\0").decode(errors="replace") if magic == 0xABCD5432 else None
    found = want is not None and (want.encode() in app)
    res.append(dict(id=vid, feature=feat, check="App image carries the device file's project_version (what the update entity compares)",
                    status="pass" if found else "fail",
                    detail=f"device file version {want}: {'found' if found else 'NOT found'} in the image (esp_app_desc holds the ESPHome version {ver!r})"))
    sdk = next((p for p in (yaml_path.parent / ".esphome" / "build" / name).glob("sdkconfig.*") if not p.name.endswith("esphomeinternal")), None)
    if sdk is None:
        res.append(dict(id=sid, feature=feat, check="Built sdkconfig has signed-on-update on", status="fail", detail="no sdkconfig in the build"))
    else:
        lines = set(sdk.read_text().splitlines())
        missing = [o for o in SECURE if o not in lines]
        bad = [o for o in NOT_SET if o in lines]
        res.append(dict(id=sid, feature=feat,
                        check="Built sdkconfig has signed-on-update on (RSA, no secure boot), secure boot, flash encryption and build-time signing off",
                        status="pass" if not missing and not bad else "fail",
                        detail=f"missing {missing}; unexpectedly set {bad}" if missing or bad else f"{sdk.name}: {', '.join(SECURE)}; none of {', '.join(NOT_SET)}"))
    return res


def run(devices: list[str], clean: bool = False) -> list[dict]:
    files = prep.prepare()
    edir = prep.WORK / "esphome"
    if clean and (edir / ".esphome").exists():
        import shutil
        shutil.rmtree(edir / ".esphome")
    logs = prep.OUT / "firmware-logs"
    logs.mkdir(parents=True, exist_ok=True)
    results = []
    for dev in devices:
        y = files[dev]["signed"]
        log = logs / f"compile-{dev}.log"
        t0 = time.time()
        with log.open("w") as fh:
            rc = subprocess.run(prep.esphome_cmd("compile", y.name), cwd=edir, stdout=fh, stderr=subprocess.STDOUT).returncode
        results += check_build(dev, y, log, rc, time.time() - t0)
        print(f"{dev}: rc={rc} {time.time() - t0:.0f}s", flush=True)
    return results


if __name__ == "__main__":
    devs = sys.argv[1:] or list(IDS)
    out = run(devs)
    path = prep.OUT / "firmware-compile.json"
    old = json.loads(path.read_text()) if path.exists() else []
    keep = [r for r in old if not any(r["id"] in IDS[d] for d in devs)]
    path.write_text(json.dumps(keep + out, indent=1))
    for r in out:
        print(r["id"], r["status"], r["check"], "-", r.get("detail", "").splitlines()[0] if r.get("detail") else "")
