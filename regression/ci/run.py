#!/usr/bin/env python3
"""Regression stage "ci": the release tooling in .github/ -> regression/out/ci.json.

Usage:

    /path/to/esphome-venv/bin/python regression/ci/run.py [--bin DIR]

Needs Python with PyYAML, and espsecure (esptool 5.x) on PATH, in --bin, or next to the interpreter (an
ESPHome venv has all of them). Everything runs on copies in a temporary folder: a throwaway RSA-3072 key made
with espsecure there (never in the repository), fake firmware images, and temporary git repositories for the
privacy guard. The real PRIVACY_DENYLIST is never read: the guard runs with an empty one.

Checks (CI-001 ...): sign_firmware.py end to end, signed_build.py, check_versions.py, privacy_guard.py's own
rules, make_site.py with fake builds (ESP Web Tools comes from npm: skip without network), release_notes.py,
check_bp2_standalone.py (needs esphome), and invariants of .github/workflows/*.yml. IDs are stable: add new
checks with new numbers, never reuse one. Catalogue: regression/catalogue/ci.yaml.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / ".github" / "scripts"
OUT = REPO / "regression" / "out"
APP_OFFSET = 0x10000
PUB_KEY = REPO / "esphome" / "firmware-signing-key.pub.pem"
# Strings that look like secrets are put together at run time, so this file never trips the privacy guard.
PRIVATE_KEY_HEADER = "-----BEGIN " + "PRIVATE KEY-----"
PRIVATE_KEY_FOOTER = "-----END " + "PRIVATE KEY-----"
FAKE_GITHUB_TOKEN = "gh" + "p_" + "Q" * 36

RESULTS: list[dict] = []


class Skip(Exception):
    """The check can't run here (reason in the message)."""


def check(check_id: str, feature: str, text: str):
    def wrap(fn):
        try:
            detail = fn() or ""
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "pass", "detail": detail})
        except Skip as err:
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "skip", "detail": str(err)})
        except AssertionError as err:
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "fail",
                            "detail": str(err) or traceback.format_exc(limit=2)[-1500:]})
        except Exception as err:  # noqa: BLE001 - a broken check is a failure with its traceback
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "fail",
                            "detail": f"{type(err).__name__}: {err}\n{traceback.format_exc(limit=3)[-1500:]}"})
        return fn
    return wrap


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 300):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)


def script(name: str, *args: str, cwd: Path | None = None, env: dict | None = None, path: Path | None = None):
    return run([sys.executable, str(path or SCRIPTS / name), *map(str, args)], cwd=cwd, env=env)


def out_of(proc) -> str:
    return (proc.stdout + proc.stderr).strip()[-1200:]


# ---------------------------------------------------------------------------- set-up


def make_env(bin_dir: str | None) -> dict:
    extra = [d for d in (bin_dir, str(Path(sys.executable).parent)) if d]
    return {**os.environ, "PATH": os.pathsep.join([*extra, os.environ.get("PATH", "")])}


def gen_key(env: dict, path: Path) -> None:
    proc = run(["espsecure", "generate-signing-key", "--version", "2", "--scheme", "rsa3072", str(path)], env=env)
    assert proc.returncode == 0 and path.is_file(), f"espsecure generate-signing-key failed: {out_of(proc)}"


def public_key(private: Path, public: Path) -> None:
    from cryptography.hazmat.primitives import serialization  # noqa: PLC0415 - comes with esptool

    key = serialization.load_pem_private_key(private.read_bytes(), password=None)
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                     serialization.PublicFormat.SubjectPublicKeyInfo))


def fake_build(folder: Path, *, app_size: int = 0x30000, seed: int = 1, real: Path | None = None) -> tuple[bytes, bytes]:
    """A build dir with firmware.ota.bin and firmware.factory.bin in the official layout (app at 0x10000).

    With `real` (an ESPHome build dir) the bootloader area and app come from a real build, the app padded with
    0xFF to a multiple of 64 KB as a signed-updates build pads it; otherwise both are made up.
    """
    folder.mkdir(parents=True, exist_ok=True)
    if real is not None:
        app = (real / "firmware.ota.bin").read_bytes()
        head = (real / "firmware.factory.bin").read_bytes()[:APP_OFFSET]
        app += b"\xff" * (-len(app) % 0x10000)
    else:
        rnd = hashlib.sha256(str(seed).encode()).digest()
        app = b"\xe9" + (rnd * (app_size // len(rnd) + 1))[: app_size - 1]
        head = (b"\xe9\x03\x02\x20" + rnd) .ljust(0x8000, b"\xff") + b"\xaa\x50".ljust(0x1000, b"\xff")
        head = head.ljust(APP_OFFSET, b"\xff")
    (folder / "firmware.ota.bin").write_bytes(app)
    (folder / "firmware.factory.bin").write_bytes(head + app)
    return head, app


def verify(env: dict, pub: Path, image: Path):
    return run(["espsecure", "verify-signature", "--version", "2", "--keyfile", str(pub), str(image)], env=env)


# ---------------------------------------------------------------------------- the stage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bin", help="folder with espsecure (e.g. an ESPHome venv's bin)")
    args = parser.parse_args()
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    env = make_env(args.bin)
    have_espsecure = shutil.which("espsecure", path=env["PATH"]) is not None
    real_build = REPO / "esphome" / ".esphome" / "build" / "magicband-bridge" / "build"
    real_build = real_build if (real_build / "firmware.ota.bin").is_file() and (real_build / "firmware.factory.bin").is_file() else None

    with tempfile.TemporaryDirectory(prefix="mb-ci-") as tmp_name:
        tmp = Path(tmp_name)
        signing_checks(tmp, env, have_espsecure, real_build)
        signed_build_checks(tmp)
        version_checks(tmp)
        privacy_checks(tmp)
        site_checks(tmp)
        other_script_checks(env)
    workflow_checks()

    RESULTS.sort(key=lambda r: r["id"])
    counts = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("pass", "fail", "skip", "manual")}
    try:
        from importlib.metadata import version as _pkg_version  # noqa: PLC0415

        espsecure_version = f"esptool {_pkg_version('esptool')}" if have_espsecure else None
    except Exception:  # noqa: BLE001 - espsecure from another environment
        espsecure_version = "found (version unknown)" if have_espsecure else None
    stage = {
        "stage": "ci",
        "started": started,
        "finished": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {
            "note": "throwaway signing key and fake images in a temp folder; privacy guard run with an empty "
                    "PRIVACY_DENYLIST; workflow invariants read from .github/workflows",
            "python": sys.version.split()[0],
            "espsecure": espsecure_version or "not found",
            "real_build_used": str(real_build.relative_to(REPO)) if real_build else None,
            "counts": counts,
        },
        "results": RESULTS,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ci.json").write_text(json.dumps(stage, indent=2) + "\n", encoding="utf-8")
    print(f"ci: {counts['pass']} pass, {counts['fail']} fail, {counts['skip']} skip -> {OUT / 'ci.json'}")
    for r in RESULTS:
        if r["status"] != "pass":
            print(f"  {r['id']} {r['status'].upper()}: {r['check']}\n      {r['detail'][:300]}")
    return 0  # failing checks are results, not a broken stage (regression/run.py treats exit != 0 as broken)


# ---------------------------------------------------------------------------- sign_firmware.py

F_SIGN = "Signed firmware updates: CI signing (sign_firmware.py)"


def signing_checks(tmp: Path, env: dict, have_espsecure: bool, real_build: Path | None) -> None:
    key, pub = tmp / "keys" / "test-key.pem", tmp / "keys" / "test-key.pub.pem"
    other, other_pub = tmp / "keys" / "other-key.pem", tmp / "keys" / "other-key.pub.pem"
    state: dict = {}

    def need():
        if not have_espsecure:
            raise Skip("espsecure not found (pass --bin <esphome venv>/bin)")
        if "keys" not in state:
            raise Skip("no throwaway key (CI-001 failed)")

    @check("CI-001", F_SIGN, "A throwaway RSA-3072 key pair is made with espsecure in a temp folder (not the repo)")
    def _():
        if not have_espsecure:
            raise Skip("espsecure not found (pass --bin <esphome venv>/bin)")
        key.parent.mkdir(parents=True)
        gen_key(env, key)
        public_key(key, pub)
        gen_key(env, other)
        public_key(other, other_pub)
        assert REPO not in key.resolve().parents
        state["keys"] = True
        return f"keys in {key.parent} (deleted afterwards)"

    build = tmp / "sign" / "magicband-bridge" / "build"
    build2 = tmp / "sign" / "magicband-reader" / "build"

    @check("CI-002", F_SIGN, "Signs a 64 KB-aligned app pair: exit 0, firmware.ota.bin = app + one 4 KB signature sector")
    def _():
        need()
        head, app = fake_build(build, real=real_build)
        fake_build(build2, seed=2)
        state["orig"] = (head, app)
        proc = script("sign_firmware.py", key, pub, build, build2, env=env)
        assert proc.returncode == 0, f"exit {proc.returncode}: {out_of(proc)}"
        signed = (build / "firmware.ota.bin").read_bytes()
        assert len(signed) == len(app) + 0x1000 and signed[: len(app)] == app, "signed image layout"
        assert (build2 / "firmware.ota.bin").stat().st_size == 0x30000 + 0x1000, "second build dir not signed"
        state["signed"] = signed
        return f"{len(app)} + 4096 bytes ({'real bridge build, padded' if real_build else 'made-up image'}); two build dirs"

    @check("CI-003", F_SIGN, "The signed image verifies with the matching public key (espsecure verify-signature)")
    def _():
        need()
        if "signed" not in state:
            raise Skip("nothing signed (CI-002 failed)")
        proc = verify(env, pub, build / "firmware.ota.bin")
        assert proc.returncode == 0, out_of(proc)

    @check("CI-004", F_SIGN, "The signed image does NOT verify with a different key")
    def _():
        need()
        if "signed" not in state:
            raise Skip("nothing signed (CI-002 failed)")
        proc = verify(env, other_pub, build / "firmware.ota.bin")
        assert proc.returncode != 0, "verified with the wrong key"

    @check("CI-005", F_SIGN, "Factory image rebuilt: bootloader/partitions/otadata unchanged, signed app at 0x10000")
    def _():
        need()
        if "signed" not in state:
            raise Skip("nothing signed (CI-002 failed)")
        head, _app = state["orig"]
        factory = (build / "firmware.factory.bin").read_bytes()
        assert factory[:APP_OFFSET] == head, "first 64 KB changed"
        assert factory[APP_OFFSET:] == state["signed"], "app at 0x10000 isn't the signed image"

    @check("CI-006", F_SIGN, "Refuses to sign again an image that's already signed (files left as they were)")
    def _():
        need()
        if "signed" not in state:
            raise Skip("nothing signed (CI-002 failed)")
        before = {p: p.read_bytes() for p in build.iterdir()}
        proc = script("sign_firmware.py", key, pub, build, env=env)
        assert proc.returncode != 0, "signed an already-signed image"
        assert {p: p.read_bytes() for p in build.iterdir()} == before, "files changed"
        # The refusal comes from the 64 KB check (a signed app is 4 KB over), so its message talks about padding.
        return "refused: " + out_of(proc).splitlines()[-1].split(": ", 1)[-1]

    @check("CI-007", F_SIGN, "Refuses an app that isn't padded to 64 KB (built without signed updates)")
    def _():
        need()
        folder = tmp / "sign-unaligned"
        if real_build is not None:
            folder.mkdir()
            for name in ("firmware.ota.bin", "firmware.factory.bin"):
                shutil.copy(real_build / name, folder / name)
            note = "real unsigned bridge build"
        else:
            fake_build(folder, app_size=0x30000 + 0x800, seed=3)
            note = "made-up image"
        assert (folder / "firmware.ota.bin").stat().st_size % 0x10000, "test image is aligned"
        before = (folder / "firmware.ota.bin").read_bytes()
        proc = script("sign_firmware.py", key, pub, folder, env=env)
        assert proc.returncode != 0 and "64 KB" in out_of(proc), out_of(proc)
        assert (folder / "firmware.ota.bin").read_bytes() == before
        return note

    @check("CI-008", F_SIGN, "Refuses when the private key doesn't match the committed public key (wrong secret)")
    def _():
        need()
        folder = tmp / "sign-wrongkey"
        fake_build(folder, seed=4)
        before = (folder / "firmware.ota.bin").read_bytes()
        proc = script("sign_firmware.py", other, pub, folder, env=env)
        assert proc.returncode != 0 and "verify-signature" in out_of(proc), out_of(proc)
        assert (folder / "firmware.ota.bin").read_bytes() == before, "the image was replaced"

    @check("CI-009", F_SIGN, "Refuses a factory image that doesn't end with the app at 0x10000")
    def _():
        need()
        folder = tmp / "sign-badfactory"
        head, app = fake_build(folder, seed=5)
        (folder / "firmware.factory.bin").write_bytes(head[:0x8000] + app)
        proc = script("sign_firmware.py", key, pub, folder, env=env)
        assert proc.returncode != 0 and "0x10000" in out_of(proc), out_of(proc)

    @check("CI-010", F_SIGN, "Refuses to run without the public key file")
    def _():
        need()
        folder = tmp / "sign-nopub"
        fake_build(folder, seed=6)
        proc = script("sign_firmware.py", key, tmp / "missing.pub.pem", folder, env=env)
        assert proc.returncode != 0 and "missing" in out_of(proc), out_of(proc)

    @check("CI-011", F_SIGN, "The committed esphome/firmware-signing-key.pub.pem is an RSA-3072 public key, not a private one")
    def _():
        from cryptography.hazmat.primitives import serialization  # noqa: PLC0415

        text = PUB_KEY.read_text()
        assert "PRIVATE" not in text
        k = serialization.load_pem_public_key(text.encode())
        assert k.key_size == 3072, k.key_size
        return "RSA-3072"


# ---------------------------------------------------------------------------- signed_build.py

F_SB = "Signed firmware updates: official builds switch them on (signed_build.py)"
OPTIONS = {
    "CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT": "y",
    "CONFIG_SECURE_SIGNED_APPS_RSA_SCHEME": "y",
    "CONFIG_SECURE_SIGNED_ON_UPDATE_NO_SECURE_BOOT": "y",
    "CONFIG_SECURE_BOOT_BUILD_SIGNED_BINARIES": "n",
}


def _yaml_load(text: str):
    import yaml  # noqa: PLC0415

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_multi_constructor("!", lambda loader, suffix, node: None)
    return yaml.load(text, Loader=Loader)  # noqa: S506 - SafeLoader subclass


def _framework(doc) -> dict:
    return ((doc or {}).get("esp32") or {}).get("framework") or {}


def signed_build_checks(tmp: Path) -> None:
    folder = tmp / "signed-build"
    folder.mkdir()
    devices = ["magicband-bridge.yaml", "magicband-reader.yaml", "screek-bp2-poe.yaml"]

    @check("CI-012", F_SB, "Adds exactly the four sdkconfig options under esp32 framework esp-idf, nothing else changes "
           "(bridge, reader, BP2)")
    def _():
        notes = []
        for name in devices:
            src = REPO / "esphome" / name
            out = folder / name
            proc = script("signed_build.py", src, out)
            assert proc.returncode == 0, f"{name}: {out_of(proc)}"
            before, after = src.read_text().splitlines(), out.read_text().splitlines()
            added = [line for line in after if line not in before]
            assert len(after) == len(before) + 5, f"{name}: {len(after) - len(before)} lines added"
            assert added[0].strip() == "sdkconfig_options:", f"{name}: {added}"
            assert {a.strip().split(":")[0]: a.split(":")[1].strip() for a in added[1:]} == OPTIONS, f"{name}: {added}"
            assert _framework(_yaml_load(out.read_text())).get("sdkconfig_options") == OPTIONS, f"{name}: YAML"
            rest = [line for line in after if line not in added]
            assert rest == before, f"{name}: other lines changed"
            notes.append(name)
        return ", ".join(notes)

    @check("CI-013", F_SB, "Refuses a file that already has sdkconfig_options")
    def _():
        out = folder / "magicband-bridge.yaml"
        if not out.is_file():
            raise Skip("no output from CI-012")
        before = out.read_text()
        proc = script("signed_build.py", out, folder / "again.yaml")
        assert proc.returncode != 0 and "sdkconfig_options" in out_of(proc), out_of(proc)
        assert not (folder / "again.yaml").exists() and out.read_text() == before

    @check("CI-014", F_SB, "Works in place (the workflow passes the same file as input and output for reader and BP2)")
    def _():
        copy = folder / "inplace.yaml"
        shutil.copy(REPO / "esphome" / "magicband-reader.yaml", copy)
        proc = script("signed_build.py", copy, copy)
        assert proc.returncode == 0, out_of(proc)
        assert _framework(_yaml_load(copy.read_text())).get("sdkconfig_options") == OPTIONS

    @check("CI-015", F_SB, "Refuses a file without one 'framework: type: esp-idf' block; device files in the repo stay unlocked")
    def _():
        bad = folder / "arduino.yaml"
        bad.write_text("esp32:\n  board: esp32dev\n  framework:\n    type: arduino\n")
        proc = script("signed_build.py", bad, folder / "arduino-out.yaml")
        assert proc.returncode != 0, "accepted a file with no esp-idf block"
        for name in [*devices, "screek-bp2-poe-standalone.yaml"]:
            assert "CONFIG_SECURE_SIGNED" not in (REPO / "esphome" / name).read_text(), f"{name} is locked to the key"


# ---------------------------------------------------------------------------- check_versions.py

F_VER = "Release: every part carries the same version (check_versions.py, release_notes.py)"
VERSION_FILES = ["VERSION", "CHANGELOG.md", "custom_components/magicband/manifest.json", "esphome/magicband-bridge.yaml",
                 "esphome/magicband-reader.yaml", "esphome/screek-bp2-poe.yaml", "esphome/screek-bp2-poe-standalone.yaml",
                 ".github/scripts/check_versions.py"]


def _version_copy(tmp: Path, name: str) -> Path:
    root = tmp / name
    for rel in VERSION_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, root / rel)
    return root


def version_checks(tmp: Path) -> None:
    version = (REPO / "VERSION").read_text().strip()

    @check("CI-016", F_VER, "Passes on the current tree, and with the matching tag v<VERSION>")
    def _():
        proc = script("check_versions.py")
        assert proc.returncode == 0, out_of(proc)
        proc = script("check_versions.py", f"v{version}")
        assert proc.returncode == 0, out_of(proc)
        proc = script("check_versions.py", f"refs/tags/v{version}")
        assert proc.returncode == 0, out_of(proc)
        return f"VERSION {version}"

    @check("CI-017", F_VER, "Fails when one part has another version (temp copy: manifest.json and a device file)")
    def _():
        root = _version_copy(tmp, "versions-manifest")
        manifest = root / "custom_components/magicband/manifest.json"
        data = json.loads(manifest.read_text())
        data["version"] = "0.0.1"
        manifest.write_text(json.dumps(data))
        proc = script("check_versions.py", path=root / ".github/scripts/check_versions.py")
        assert proc.returncode != 0 and "BAD custom_components/magicband/manifest.json: 0.0.1" in out_of(proc), out_of(proc)
        root = _version_copy(tmp, "versions-yaml")
        reader = root / "esphome/magicband-reader.yaml"
        reader.write_text(re.sub(r'(project_version:\s*")[^"]+', r"\g<1>9.9.9", reader.read_text(), count=1))
        proc = script("check_versions.py", path=root / ".github/scripts/check_versions.py")
        assert proc.returncode != 0 and "BAD esphome/magicband-reader.yaml: 9.9.9" in out_of(proc), out_of(proc)

    @check("CI-018", F_VER, "Fails on a wrong tag and on a CHANGELOG without the version's section")
    def _():
        proc = script("check_versions.py", "v0.0.1")
        assert proc.returncode != 0 and "BAD git tag" in out_of(proc), out_of(proc)
        root = _version_copy(tmp, "versions-changelog")
        log = root / "CHANGELOG.md"
        log.write_text(log.read_text().replace(f"## [{version}]", "## [unreleased]"))
        proc = script("check_versions.py", path=root / ".github/scripts/check_versions.py")
        assert proc.returncode != 0 and "BAD CHANGELOG.md" in out_of(proc), out_of(proc)

    @check("CI-019", F_VER, "release_notes.py prints the CHANGELOG section for VERSION and refuses an unknown version")
    def _():
        proc = script("release_notes.py", f"v{version}")
        assert proc.returncode == 0 and proc.stdout.strip(), out_of(proc)
        assert "## [" not in proc.stdout, "ran into the next section"
        proc = script("release_notes.py", "v0.0.0")
        assert proc.returncode != 0


# ---------------------------------------------------------------------------- privacy_guard.py

F_PG = "Privacy guard (privacy_guard.py): no-reply commits, no credentials or secrets files, private terms"
NOREPLY = "123+morgan@users.noreply.github.com"


def _guard_env(denylist: str = "") -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PRIVACY_DENYLIST", "BASE", "HEAD") and not k.startswith("GIT_")}
    env["PRIVACY_DENYLIST"] = denylist  # never the real one
    return env


def _repo(tmp: Path, name: str, files: dict[str, str], email: str = NOREPLY) -> Path:
    root = tmp / "privacy" / name
    root.mkdir(parents=True)
    env = _guard_env()
    run(["git", "init", "-q"], cwd=root, env=env)
    for rel, text in {"README.md": "Lakeview test repo\n", **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    run(["git", "add", "-A"], cwd=root, env=env)
    proc = run(["git", "-c", f"user.email={email}", "-c", "user.name=Morgan", "-c", "commit.gpgsign=false",
                "commit", "-q", "-m", "test"], cwd=root, env=env)
    assert proc.returncode == 0, out_of(proc)
    return root


def _guard(root: Path, denylist: str = "", base: str | None = None, head: str | None = None):
    env = _guard_env(denylist)
    env.update({k: v for k, v in (("BASE", base), ("HEAD", head)) if v is not None})
    return run([sys.executable, str(SCRIPTS / "privacy_guard.py")], cwd=root, env=env)


def _public_pem() -> str:
    return PUB_KEY.read_text()


def privacy_checks(tmp: Path) -> None:
    @check("CI-020", F_PG, "Passes on the current tree (HEAD commit and tracked files) with an empty PRIVACY_DENYLIST")
    def _():
        proc = _guard(REPO)
        assert proc.returncode == 0, out_of(proc)
        return out_of(proc).splitlines()[-1]

    @check("CI-021", F_PG, "A clean repository with a no-reply author passes")
    def _():
        proc = _guard(_repo(tmp, "clean", {"a.txt": "nothing to see\n"}))
        assert proc.returncode == 0, out_of(proc)

    @check("CI-022", F_PG, "Flags a tracked *.pem (a key file) by name")
    def _():
        proc = _guard(_repo(tmp, "pem", {"keys/signing.pem": _public_pem()}))
        assert proc.returncode != 0 and "file=keys/signing.pem" in proc.stdout and "secrets file" in proc.stdout, out_of(proc)

    @check("CI-023", F_PG, "Does not flag a tracked *.pub.pem holding a public key")
    def _():
        proc = _guard(_repo(tmp, "pubpem", {"esphome/firmware-signing-key.pub.pem": _public_pem()}))
        assert proc.returncode == 0, out_of(proc)

    @check("CI-024", F_PG, "Flags BEGIN PRIVATE KEY content even in a *.pub.pem")
    def _():
        body = f"{PRIVATE_KEY_HEADER}\nMIIfake\n{PRIVATE_KEY_FOOTER}\n"
        proc = _guard(_repo(tmp, "privinpub", {"esphome/sneaky.pub.pem": body}))
        assert proc.returncode != 0 and "file=esphome/sneaky.pub.pem,line=1" in proc.stdout, out_of(proc)

    @check("CI-025", F_PG, "Flags a commit whose author isn't a no-reply address")
    def _():
        proc = _guard(_repo(tmp, "author", {"a.txt": "x\n"}, email="morgan@example.com"))
        assert proc.returncode != 0 and "author email isn't a no-reply address" in proc.stdout, out_of(proc)
        assert "committer email" in proc.stdout

    @check("CI-026", F_PG, "Flags a credential-looking token in a file and a tracked secrets.yaml")
    def _():
        proc = _guard(_repo(tmp, "token", {"config.txt": f"token: {FAKE_GITHUB_TOKEN}\n", "secrets.yaml": "x: 1\n"}))
        assert proc.returncode != 0
        assert "file=config.txt,line=1::Looks like a credential" in proc.stdout, out_of(proc)
        assert "file=secrets.yaml::A secrets file is tracked" in proc.stdout, out_of(proc)

    @check("CI-027", F_PG, "A private term from PRIVACY_DENYLIST is reported by file, line and rule number, never echoed")
    def _():
        term = "Hillcrest Close 42"  # made up
        root = _repo(tmp, "denylist", {"notes.md": f"meet at {term}\n"})
        proc = _guard(root, denylist="# made-up terms\nnobody-here\nhillcrest close \\d+\n")
        assert proc.returncode != 0 and "file=notes.md,line=1::Matches private term #2" in proc.stdout, out_of(proc)
        assert term.lower() not in (proc.stdout + proc.stderr).lower(), "the matched text was printed"
        proc = _guard(root)
        assert proc.returncode == 0 and "PRIVACY_DENYLIST secret isn't set" in proc.stdout, out_of(proc)

    # Made-up private terms for the history, path and binary checks below (never the real denylist).
    term, rule = "Hillcrest Close 42", "hillcrest close \\d+"

    @check("CI-041", F_PG, "A private term added in one commit and removed in the next of the same push (BASE..HEAD) "
           "is caught, by commit and rule number, without echoing it")
    def _():
        root = _history(tmp, "addremove")
        base = _commit(root, {"a.txt": "clean\n"})
        _commit(root, {"notes.md": f"line one\nmeet at {term}\n"})
        head = _commit(root, {"notes.md": None})
        proc = _guard(root, denylist=rule, base=base, head=head)
        assert proc.returncode != 0 and "adds a line matching private term #1" in proc.stdout, out_of(proc)
        assert "file=notes.md,line=2" in proc.stdout, out_of(proc)
        _assert_not_echoed(proc, term)
        proc = _guard(root, denylist=rule, base=head, head=head)
        assert proc.returncode == 0, f"only the pushed range counts: {out_of(proc)}"

    @check("CI-042", F_PG, "A new branch or tag (BASE all zeros) is checked from its merge base with origin/main: "
           "an earlier commit's removed term and author address are caught, main's own history is not re-checked")
    def _():
        root = _history(tmp, "newbranch")
        _commit(root, {"old.txt": f"before the branch: {term}\n"})  # on main already: not this push's business
        main = _commit(root, {"old.txt": "cleaned\n"})
        run(["git", "update-ref", "refs/remotes/origin/main", main], cwd=root, env=_guard_env())
        run(["git", "checkout", "-q", "-b", "feature"], cwd=root, env=_guard_env())
        _commit(root, {"b.txt": f"{term}\n"}, email="morgan@example.com")
        _commit(root, {"b.txt": "fixed\n"})
        proc = _guard(root, denylist=rule, base="0" * 40, head="HEAD")
        assert proc.returncode != 0 and "file=b.txt,line=1" in proc.stdout, out_of(proc)
        assert "author email isn't a no-reply address" in proc.stdout, out_of(proc)
        assert "old.txt" not in proc.stdout, f"re-checked main's history: {out_of(proc)}"
        _assert_not_echoed(proc, term)

    @check("CI-043", F_PG, "A private term in a file name or path is caught (tracked tree and the commit adding it) "
           "and the path isn't printed")
    def _():
        root = _history(tmp, "pathname")
        base = _commit(root, {"a.txt": "clean\n"})
        head = _commit(root, {"photos/hillcrest-close-42.txt": "nothing private inside\n"})
        proc = _guard(root, denylist=rule.replace(" ", "[ -]"), base=base, head=head)
        assert proc.returncode != 0, out_of(proc)
        assert "Tracked file #" in proc.stdout and "path matches private term #1" in proc.stdout, out_of(proc)
        assert f"Commit {head[:8]}, path #" in proc.stdout, out_of(proc)
        assert "hillcrest" not in (proc.stdout + proc.stderr).lower(), "the path was printed"

    @check("CI-044", F_PG, "Binary files: a private term in a PNG text chunk, in a UTF-16 string, and in a .zip "
           "member's name or content is caught (tree and history) without echoing it; credentials rules don't "
           "apply to binary runs")
    def _():
        root = _history(tmp, "binary")
        base = _commit(root, {"a.txt": "clean\n"})
        head = _commit(root, {
            "docs/images/photo.png": _png_with_text("Comment", f"taken at {term}"),
            "docs/notes.bin": b"\x00\x01" + f"near {term}".encode("utf-16-le") + b"\x00\x00",
            "hardware/gerbers.zip": _zip({"readme.txt": f"ship to {term}\n"}),
            "hardware/named.zip": _zip({f"{term}.txt": "plain\n"}),
            "docs/token.bin": b"\x00" + FAKE_GITHUB_TOKEN.encode() + b"\x00",
        })
        proc = _guard(root, denylist=rule, base=base, head=head)
        out = proc.stdout
        assert proc.returncode != 0, out_of(proc)
        for path in ("docs/images/photo.png", "docs/notes.bin", "hardware/gerbers.zip"):
            assert f"file={path}::Binary content" in out or f"file={path}::Zip member #1" in out, (path, out_of(proc))
        assert "file=hardware/named.zip::Zip member #1 (list them with unzip -Z1): its name matches private term #1" \
            in out, out_of(proc)
        assert f"Commit {head[:8]}, an added binary file" in out, f"history not scanned: {out_of(proc)}"
        assert "docs/token.bin" not in out, f"credential rules applied to a binary: {out_of(proc)}"
        _assert_not_echoed(proc, term)
        # Removed again in the same push: still caught from the history.
        head2 = _commit(root, {"docs/images/photo.png": None, "docs/notes.bin": None, "hardware/gerbers.zip": None,
                               "hardware/named.zip": None})
        proc = _guard(root, denylist=rule, base=base, head=head2)
        assert proc.returncode != 0 and f"Commit {head[:8]}, an added binary file" in proc.stdout, out_of(proc)
        assert "Tracked file" not in proc.stdout and "::Binary content" not in proc.stdout.replace(
            "an added binary file: binary content", ""), out_of(proc)

    @check("CI-045", F_PG, "privacy.yml gives the guard the pushed range: full history checkout, BASE = the push's "
           "before (or the PR base), HEAD = the pushed commit (or the PR head)")
    def _():
        pv, _ = _workflow("privacy.yml")
        assert set(pv["on"]) >= {"push", "pull_request"}, pv["on"]
        steps = _steps(pv["jobs"]["privacy"])
        co = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
        assert (co.get("with") or {}).get("fetch-depth") == 0, "the guard needs the full history (merge base, BASE)"
        env = next(s for s in steps if "privacy_guard.py" in (s.get("run") or "")).get("env") or {}
        assert env.get("BASE") == ("${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha "
                                   "|| github.event.before }}"), env.get("BASE")
        assert env.get("HEAD") == ("${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha "
                                   "|| github.sha }}"), env.get("HEAD")
        assert env.get("PRIVACY_DENYLIST") == "${{ secrets.PRIVACY_DENYLIST }}", "denylist not from the secret"


def _history(tmp: Path, name: str) -> Path:
    root = tmp / "privacy-history" / name
    root.mkdir(parents=True)
    run(["git", "init", "-q", "-b", "main"], cwd=root, env=_guard_env())
    return root


def _commit(root: Path, files: dict, email: str = NOREPLY) -> str:
    """Write (str/bytes) or delete (None) files, commit, and return the new commit's SHA."""
    env = _guard_env()
    for rel, body in files.items():
        f = root / rel
        if body is None:
            f.unlink()
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body if isinstance(body, bytes) else body.encode())
    run(["git", "add", "-A"], cwd=root, env=env)
    proc = run(["git", "-c", f"user.email={email}", "-c", "user.name=Morgan", "-c", "commit.gpgsign=false",
                "commit", "-q", "-m", "test"], cwd=root, env=env)
    assert proc.returncode == 0, out_of(proc)
    return run(["git", "rev-parse", "HEAD"], cwd=root, env=env).stdout.strip()


def _assert_not_echoed(proc, term: str) -> None:
    assert term.lower() not in (proc.stdout + proc.stderr).lower(), "the matched text was printed"


def _png_with_text(key: str, text: str) -> bytes:
    import struct  # noqa: PLC0415
    import zlib  # noqa: PLC0415

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
            + chunk(b"tEXt", key.encode() + b"\x00" + text.encode("latin-1"))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b""))


def _zip(members: dict[str, str]) -> bytes:
    import io  # noqa: PLC0415
    import zipfile  # noqa: PLC0415

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in members.items():
            zf.writestr(name, body)
    return buf.getvalue()


# ---------------------------------------------------------------------------- make_site.py

F_SITE = "Web installer site and update manifests (make_site.py, vendored ESP Web Tools)"


def site_checks(tmp: Path) -> None:
    builds, site = tmp / "site-builds", tmp / "site"
    specs = []
    for product, slug, yaml_name in (("bridge", "magicband-bridge", "magicband-bridge.yaml"),
                                     ("reader", "magicband-reader", "magicband-reader.yaml"),
                                     ("bp2", "screek-bp2-poe", "screek-bp2-poe.yaml")):
        fake_build(builds / slug, seed=len(slug))
        specs.append(f"{product}={builds / slug}={REPO / 'esphome' / yaml_name}")
    state: dict = {}

    @check("CI-028", F_SITE, "Assembles the site from fake builds: manifests for bridge (root), reader/ and bp2/ with "
           "VERSION, firmware copied, OTA md5 matching the file")
    def _():
        proc = script("make_site.py", site, *specs)
        state["proc"] = proc
        version = (REPO / "VERSION").read_text().strip()
        for sub, slug in (("", "magicband-bridge"), ("reader/", "magicband-reader"), ("bp2/", "screek-bp2-poe")):
            manifest = site / sub / "manifest.json"
            assert manifest.is_file(), f"no {sub}manifest.json: {out_of(proc)}"
            data = json.loads(manifest.read_text())
            assert data["version"] == version, (sub, data["version"])
            build = data["builds"][0]
            ota = site / sub / build["ota"]["path"]
            factory = site / sub / build["parts"][0]["path"]
            assert ota.read_bytes() == (builds / slug / "firmware.ota.bin").read_bytes(), f"{sub}: ota copy"
            assert factory.read_bytes() == (builds / slug / "firmware.factory.bin").read_bytes(), f"{sub}: factory copy"
            assert build["ota"]["md5"] == hashlib.md5(ota.read_bytes()).hexdigest(), f"{sub}: md5"  # noqa: S324
            assert build["parts"][0]["offset"] == 0 and build["chipFamily"] == "ESP32-S3"
            assert build["ota"]["release_url"].endswith(f"/tag/v{version}")
        index = (site / "index.html").read_text()
        assert "{{VERSION}}" not in index and version in index
        return f"make_site exit {proc.returncode}"

    @check("CI-029", F_SITE, "Vendors ESP Web Tools from npm, checked against its fixed integrity hash")
    def _():
        proc = state.get("proc")
        if proc is None:
            raise Skip("make_site didn't run")
        text = out_of(proc)
        if proc.returncode != 0 and re.search(r"URLError|urlopen|Name or service|timed out|Connection|HTTP Error|SSL", text):
            raise Skip(f"no network to registry.npmjs.org: {text.splitlines()[-1]}")
        assert proc.returncode == 0, text
        assert (site / "esp-web-tools" / "install-button.js").is_file() and (site / ".nojekyll").is_file()

    @check("CI-030", F_SITE, "Refuses builds whose device files have different versions, and a missing build output")
    def _():
        odd = tmp / "odd-reader.yaml"
        odd.write_text(re.sub(r'(project_version:\s*")[^"]+', r"\g<1>9.9.9",
                              (REPO / "esphome" / "magicband-reader.yaml").read_text(), count=1))
        proc = script("make_site.py", tmp / "site-odd", specs[0], f"reader={builds / 'magicband-reader'}={odd}")
        assert proc.returncode != 0 and "versions differ" in out_of(proc), out_of(proc)
        proc = script("make_site.py", tmp / "site-missing", f"bridge={tmp / 'nowhere'}={REPO / 'esphome/magicband-bridge.yaml'}")
        assert proc.returncode != 0 and "missing build output" in out_of(proc), out_of(proc)


# ---------------------------------------------------------------------------- other scripts

def other_script_checks(env: dict) -> None:
    @check("CI-031", "SCREEK BP2-POE standalone file matches the shared add-on (check_bp2_standalone.py)",
           "check_bp2_standalone.py passes (esphome config of both BP2 files resolves to the same device)")
    def _():
        if shutil.which("esphome", path=env["PATH"]) is None:
            raise Skip("esphome not found (pass --bin <esphome venv>/bin)")
        proc = run([sys.executable, str(SCRIPTS / "check_bp2_standalone.py")], cwd=REPO / "esphome", env=env, timeout=900)
        assert proc.returncode == 0, out_of(proc)
        return out_of(proc).splitlines()[-1] if out_of(proc) else ""


# ---------------------------------------------------------------------------- workflows

F_WF = "Release pipeline security (.github/workflows/firmware.yml, privacy.yml)"
SHA_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def _workflow(name: str) -> tuple[dict, str]:
    text = (REPO / ".github" / "workflows" / name).read_text()
    doc = _yaml_load(text)
    if True in doc and "on" not in doc:  # YAML 1.1 reads the key `on` as True
        doc["on"] = doc.pop(True)
    return doc, text


def _steps(job: dict) -> list[dict]:
    return job.get("steps") or []


def _uses(doc: dict) -> list[str]:
    return [s["uses"] for job in doc["jobs"].values() for s in _steps(job) if "uses" in s] + \
           [job["uses"] for job in doc["jobs"].values() if "uses" in job]


def _secrets_in(obj) -> set[str]:
    return set(re.findall(r"secrets\.(\w+)", json.dumps(obj)))


def workflow_checks() -> None:
    fw, fw_text = _workflow("firmware.yml")
    pv, _pv_text = _workflow("privacy.yml")
    jobs = fw["jobs"]

    @check("CI-032", F_WF, "Every action in firmware.yml and privacy.yml is pinned to a commit SHA (firmware.yml: with its tag as a comment)")
    def _():
        bad = [u for doc in (fw, pv) for u in _uses(doc) if not SHA_PIN.match(u)]
        assert not bad, f"not pinned: {bad}"
        uncommented = [line.strip() for line in fw_text.splitlines()
                       if "uses:" in line and re.search(r"@[0-9a-f]{40}\s*$", line)]
        assert not uncommented, f"no tag comment: {uncommented}"
        return f"{len(_uses(fw)) + len(_uses(pv))} uses, all pinned"

    @check("CI-033", F_WF, "The sign job only runs for main or v* tags, never for pull_request, after build")
    def _():
        sign = jobs["sign"]
        cond = sign.get("if", "")
        assert "github.event_name != 'pull_request'" in cond, cond
        assert "github.ref == 'refs/heads/main'" in cond and "startsWith(github.ref, 'refs/tags/v')" in cond, cond
        assert re.fullmatch(r"github\.event_name != 'pull_request' && \(github\.ref == 'refs/heads/main' \|\| "
                            r"startsWith\(github\.ref, 'refs/tags/v'\)\)", cond.strip()), f"unexpected condition: {cond}"
        assert sign.get("needs") in ("build", ["build"]), sign.get("needs")

    @check("CI-034", F_WF, "The sign job uses the release-signing environment (which holds OTA_SIGNING_KEY)")
    def _():
        env = jobs["sign"].get("environment")
        assert env == "release-signing" or (isinstance(env, dict) and env.get("name") == "release-signing"), env

    @check("CI-035", F_WF, "deploy and release need sign (and the tests); deploy only on main; release only tags or a "
           "release run on main, and checks the commit is on main")
    def _():
        for name in ("deploy", "release"):
            needs = jobs[name].get("needs")
            needs = [needs] if isinstance(needs, str) else needs
            assert "sign" in needs and "test-integration" in needs, (name, needs)
        assert jobs["deploy"]["if"].strip() == "github.ref == 'refs/heads/main'", jobs["deploy"]["if"]
        rel = jobs["release"]["if"]
        assert "startsWith(github.ref, 'refs/tags/v')" in rel and "inputs.release" in rel and "refs/heads/main" in rel, rel
        on_main = [s for s in _steps(jobs["release"]) if "merge-base --is-ancestor" in (s.get("run") or "")]
        assert on_main, "release doesn't check the commit is on main"

    @check("CI-036", F_WF, "Secrets: OTA_SIGNING_KEY only in the sign job; the build job (runs for every branch and PR) "
           "has no secrets; no pull_request_target")
    def _():
        used = {name: _secrets_in(job) for name, job in jobs.items()}
        assert used.get("build") == set(), f"build uses secrets: {used.get('build')}"
        holders = {name for name, s in used.items() if "OTA_SIGNING_KEY" in s}
        assert holders == {"sign"}, holders
        others = {name: s for name, s in used.items() if s and name != "sign"}
        assert not others, f"other jobs use secrets: {others}"
        assert "pull_request_target" not in fw["on"] and "pull_request_target" not in pv["on"]
        sign_step = next(s for s in _steps(jobs["sign"]) if "OTA_SIGNING_KEY" in json.dumps(s))
        assert "${{" not in sign_step["run"], "the secret is expanded into the script text instead of an env variable"

    @check("CI-037", F_WF, "Permissions are minimal: read-only by default; write only where a job needs it")
    def _():
        problems = []
        if fw.get("permissions") != {"contents": "read"}:
            problems.append(f"workflow default {fw.get('permissions')}")
        if pv.get("permissions") != {"contents": "read"}:
            problems.append(f"privacy.yml default {pv.get('permissions')}")
        attest = "actions/attest-build-provenance"
        for name, job in jobs.items():
            perms = job.get("permissions") or {}
            steps = json.dumps(_steps(job)) + json.dumps(job.get("uses", ""))
            if perms.get("contents") == "write" and name != "release":
                problems.append(f"{name}: contents: write")
            if perms.get("pages") == "write" and name != "deploy":
                problems.append(f"{name}: pages: write")
            if perms.get("attestations") == "write" and attest not in steps:
                problems.append(f"{name}: attestations: write but no attestation step")
            if perms.get("id-token") == "write" and attest not in steps and "deploy-pages" not in steps:
                problems.append(f"{name}: id-token: write but nothing uses an OIDC token")
        assert not problems, "; ".join(problems)

    @check("CI-038", F_WF, "The signing key is written with umask 077 in a subshell and removed on exit (trap)")
    def _():
        run_text = next(s["run"] for s in _steps(jobs["sign"]) if "OTA_SIGNING_KEY" in json.dumps(s))
        assert re.search(r"\(umask 077;\s*printf '%s\\n' \"\$OTA_SIGNING_KEY\" > \"\$key\"\)", run_text), run_text
        trap = re.search(r"trap 'rm -f \"\$key\"' EXIT", run_text)
        write = run_text.find("umask 077")
        assert trap and trap.start() < write, "no trap set before the key is written"
        assert 'key="$RUNNER_TEMP/' in run_text, "key not under RUNNER_TEMP"
        assert "esphome/firmware-signing-key.pub.pem" in run_text, "not verified against the committed public key"

    @check("CI-039", F_WF, "Every checkout drops its credentials (persist-credentials: false)")
    def _():
        bad = [f"{wf}:{name}" for wf, doc in (("firmware", fw), ("privacy", pv)) for name, job in doc["jobs"].items()
               for s in _steps(job) if str(s.get("uses", "")).startswith("actions/checkout@")
               and (s.get("with") or {}).get("persist-credentials") is not False]
        assert not bad, bad

    @check("CI-040", F_WF, "Pages and release files come from the signed images: the site is assembled in sign from "
           "the signed builds; release downloads the 'firmware' artifact sign uploads")
    def _():
        sign_runs = " ".join(s.get("run") or "" for s in _steps(jobs["sign"]))
        assert sign_runs.find("sign_firmware.py") < sign_runs.find("make_site.py _site"), "site built before signing"
        assert "builds/magicband-bridge/build" in sign_runs.split("make_site.py _site")[1]
        uploads = [s for s in _steps(jobs["sign"]) if "upload-pages-artifact" in str(s.get("uses"))]
        assert uploads and "_site" in json.dumps(uploads[0]), "Pages artifact not from sign"
        dl = [s for s in _steps(jobs["release"]) if "download-artifact" in str(s.get("uses"))]
        assert dl and (dl[0].get("with") or {}).get("name") == "firmware", dl
        build_uploads = [s for s in _steps(jobs["build"]) if "upload-pages-artifact" in str(s.get("uses"))]
        assert not build_uploads, "build (unsigned) uploads a Pages artifact"

    @check("CI-046", F_WF, "The sign job checks the commit is on main (as release does) before it installs anything or "
           "touches the key, with the full history checked out")
    def _():
        steps = _steps(jobs["sign"])
        on_main = [i for i, s in enumerate(steps) if "merge-base --is-ancestor \"$GITHUB_SHA\" origin/main"
                   in (s.get("run") or "") and "git fetch --no-tags origin main" in (s.get("run") or "")]
        assert on_main, "sign doesn't check the commit is on main"
        first_other = min(i for i, s in enumerate(steps)
                          if "OTA_SIGNING_KEY" in json.dumps(s) or "pip install" in (s.get("run") or ""))
        assert on_main[0] < first_other, "the main check runs after the install or the key"
        co = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
        assert (co.get("with") or {}).get("fetch-depth") == 0, "sign checkout needs fetch-depth: 0 for merge-base"

    @check("CI-047", F_WF, "The sign job (holds OTA_SIGNING_KEY) installs only hash-pinned packages: pip "
           "--require-hashes --no-deps from .github/requirements-signing*.txt, every package pinned with == and a "
           "sha256 hash, esptool at the version the CI tooling expects")
    def _():
        installs = [line.strip() for s in _steps(jobs["sign"]) for line in (s.get("run") or "").splitlines()
                    if re.search(r"\bpip3? install\b", line)]
        assert installs, "sign installs nothing (where does espsecure come from?)"
        files = set()
        for line in installs:
            assert "--require-hashes" in line and "--no-deps" in line, f"not hash-pinned: {line}"
            m = re.search(r"-r\s+(\S+)", line)
            assert m and re.fullmatch(r"\.github/requirements-signing[\w-]*\.txt", m.group(1)), f"no pinned file: {line}"
            files.add(m.group(1))
        names = set()
        for rel in sorted(files):
            text = (REPO / rel).read_text()
            reqs = re.split(r"\n(?=[A-Za-z0-9])", "\n".join(ln for ln in text.splitlines()
                                                          if not ln.lstrip().startswith("#") and ln.strip()))
            for req in reqs:
                head = req.split("\\")[0].strip()
                assert re.fullmatch(r"[A-Za-z0-9._-]+==[\w.]+", head), f"{rel}: not pinned with ==: {head}"
                hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})\b", req)
                assert hashes, f"{rel}: {head} has no sha256 hash"
                assert len(hashes) == req.count("--hash="), f"{rel}: {head} has a hash that isn't sha256"
                names.add(head.split("==")[0].lower())
        assert "esptool" in names and "esptool==5.4.0" in (REPO / ".github/requirements-signing.txt").read_text()
        return f"{len(names)} packages pinned by hash"

    @check("CI-048", F_WF, "The attestation check in docs/security.md and the release job pins the signer workflow "
           "and the main branch, not only the repository")
    def _():
        repo = "Legal-Copy7045/Magic-bHAnds"
        want = (f"--signer-workflow {repo}/.github/workflows/firmware.yml", "--source-ref refs/heads/main")
        doc = re.sub(r"\s+", " ", (REPO / "docs" / "security.md").read_text())
        cmds = re.findall(r"gh attestation verify [^`]*", doc)
        assert cmds, "docs/security.md has no gh attestation verify command"
        for cmd in cmds:
            assert f"--repo {repo}" in cmd and want[0] in cmd, f"signer workflow not pinned: {cmd}"
            assert re.search(r"--source-ref refs/(heads/main|tags/v)", cmd), f"ref not pinned: {cmd}"
        assert any(all(w in c for w in want) for c in cmds), cmds
        rel = re.sub(r"\s*\\\n\s*#\s*", " ", fw_text)
        assert all(w in rel for w in want), "release job comment shows an unpinned verify command"


if __name__ == "__main__":
    sys.exit(main())
