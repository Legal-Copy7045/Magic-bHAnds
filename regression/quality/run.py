#!/usr/bin/env python3
"""Regression stage "quality": code quality and supply chain -> regression/out/quality.json (IDs QUAL-...).

  python3 regression/quality/run.py

Checks (calibrated to a home hobby project: correctness and real security problems, not style):
  * lint: ruff with correctness rules only (pyflakes, syntax, bugbear without style-only rules) over the
    integration, the release scripts, the regression harness and the tests;
  * static security scan: bandit, medium and high severity, over the integration and the release scripts;
    results checked by hand and found fine are listed in quality/accepted.yaml (and an entry that no longer
    matches anything is reported, so the list can't go stale);
  * dependency audit: pip-audit (PyPI advisories) of every pinned Python package the project installs
    (signing toolchain, ESPHome, the test framework) and npm's advisory database for the vendored
    ESP Web Tools; the integration itself must declare no unpinned requirements;
  * JavaScript syntax of the page and panel scripts (node --check);
  * the regression harness's own tests (regression/tests).

Tools: ruff, bandit and pip-audit are taken from QUALITY_PYTHON's environment if it has them, else
installed (pinned) into regression/out/.venv-quality on first use. Network: PyPI and the npm registry;
without them the audit checks are skipped with the reason.
"""

from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import urllib.request

import yaml

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "regression" / "out"
VENV = OUT / ".venv-quality"
TOOLS = ["ruff==0.17.6", "bandit==1.9.4", "pip-audit==2.10.1", "pytest==9.2.0", "pyyaml==6.0.4"]
LINT_PATHS = ["custom_components", ".github/scripts", "regression", "tests"]
SCAN_PATHS = ["custom_components", ".github/scripts"]
# Correctness only: pyflakes (F), syntax errors (E9), pylint errors (PLE) and bugbear (B) minus its
# style-only rules (B905 zip strict=, B008 calls in defaults, B904 raise-from inside except).
LINT_SELECT = "F,E9,PLE,B"
LINT_IGNORE = "B905,B008,B904"
F_LINT = "Code quality: lint (ruff, correctness rules)"
F_SAST = "Code quality: static security scan (bandit)"
F_DEPS = "Supply chain: dependency audit"
F_JS = "Code quality: page and panel JavaScript"
F_HARNESS = "Regression harness: its own tests"

RESULTS: list[dict] = []


class Skip(Exception):
    pass


def check(check_id: str, feature: str, text: str):
    def wrap(fn):
        try:
            detail = fn() or ""
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "pass", "detail": detail})
        except Skip as err:
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "skip", "detail": str(err)})
        except AssertionError as err:
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "fail",
                            "detail": str(err)[:3000] or traceback.format_exc(limit=2)[-1500:]})
        except Exception as err:  # noqa: BLE001 - a broken check is a failure with its traceback
            RESULTS.append({"id": check_id, "feature": feature, "check": text, "status": "fail",
                            "detail": f"{type(err).__name__}: {err}\n{traceback.format_exc(limit=3)[-1500:]}"})
        return fn
    return wrap


def run(cmd, timeout=600, **kw):
    return subprocess.run([str(c) for c in cmd], cwd=REPO, capture_output=True, text=True, timeout=timeout,
                          check=False, **kw)


class _Scripts(HTMLParser):
    """Collects the text of every <script> without a src attribute."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self._inside = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not any(name == "src" for name, _ in attrs):
            self._inside = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._inside = False

    def handle_data(self, data):
        if self._inside:
            self.scripts[-1] += data


def inline_scripts(page: str) -> list[str]:
    parser = _Scripts()
    parser.feed(page)
    parser.close()
    return parser.scripts


def tool_python() -> Path:
    """A python whose environment has ruff, bandit, pip-audit and pytest."""
    for py in (os.environ.get("QUALITY_PYTHON"), str(VENV / "bin" / "python")):
        if py and Path(py).exists() and run([py, "-c", "import ruff, bandit, pip_audit, pytest, yaml"]).returncode == 0:
            return Path(py)
    run([sys.executable, "-m", "venv", VENV])
    proc = run([VENV / "bin" / "python", "-m", "pip", "install", "-q", *TOOLS], timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"couldn't install the quality tools: {proc.stderr[-800:]}")
    return VENV / "bin" / "python"


def workflow_pins() -> dict[str, str]:
    """Package pins the CI workflow installs (ESPHome, the integration's test framework)."""
    wf = (REPO / ".github" / "workflows" / "firmware.yml").read_text()
    pins = {"esphome": re.search(r'ESPHOME_VERSION:\s*"([^"]+)"', wf).group(1)}
    for name, ver in re.findall(r'"([A-Za-z0-9_.-]+)==([0-9][^"]*)"', wf):
        pins[name] = ver
    return pins


def main() -> int:
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        py = tool_python()
        tools_note = str(py.relative_to(REPO)) if py.is_relative_to(REPO) else str(py)
    except Exception as err:  # noqa: BLE001
        py, tools_note = None, f"tools unavailable: {err}"

    def need_tools():
        if py is None:
            raise Skip(tools_note)

    @check("QUAL-001", F_LINT, f"ruff --select {LINT_SELECT} (ignoring {LINT_IGNORE}) finds nothing in "
           + ", ".join(LINT_PATHS))
    def _():
        need_tools()
        proc = run([py, "-m", "ruff", "check", "--isolated", "--select", LINT_SELECT, "--ignore", LINT_IGNORE,
                    "--target-version", "py313", "--output-format", "concise", "--exclude", "**/.esphome/**",
                    *LINT_PATHS])
        lines = [ln for ln in proc.stdout.splitlines() if re.match(r"^\S+:\d+:\d+: ", ln)]
        assert proc.returncode == 0 and not lines, f"{len(lines)} problem(s):\n" + "\n".join(lines[:40])
        return "clean"

    bandit: dict = {}

    @check("QUAL-002", F_SAST, "bandit finds no medium or high severity issue in the integration and release "
           "scripts beyond the ones accepted in regression/quality/accepted.yaml")
    def _():
        need_tools()
        proc = run([py, "-m", "bandit", "-q", "-r", *SCAN_PATHS, "-ll", "-ii", "-f", "json"])
        data = json.loads(proc.stdout or "{}")
        accepted = yaml.safe_load((REPO / "regression" / "quality" / "accepted.yaml").read_text()) or []
        bandit["accepted"], bandit["used"] = accepted, set()
        new = []
        for r in data.get("results", []):
            path = os.path.relpath(r["filename"], REPO)
            hit = next((i for i, a in enumerate(accepted) if a["test"] == r["test_id"] and a["file"] == path
                        and a["match"] in r.get("code", "")), None)
            if hit is None:
                new.append(f"{r['test_id']} {r['issue_severity']} {path}:{r['line_number']} {r['issue_text']}")
            else:
                bandit["used"].add(hit)
        assert not new, f"{len(new)} new issue(s):\n" + "\n".join(new)
        return f"{len(data.get('results', []))} result(s), all accepted; {len(accepted)} accepted entr(ies)"

    @check("QUAL-003", F_SAST, "Every entry in regression/quality/accepted.yaml still matches a bandit result "
           "(no stale acceptances)")
    def _():
        if "accepted" not in bandit:
            raise Skip("QUAL-002 didn't run")
        stale = [f"{a['test']} {a['file']} ({a['match']})" for i, a in enumerate(bandit["accepted"])
                 if i not in bandit["used"]]
        assert not stale, "no longer matched: " + "; ".join(stale)

    def audit(lines: list[str], label: str, hashes: bool = False) -> str:
        need_tools()
        req = OUT / f".audit-{label}.txt"
        req.write_text("\n".join(lines) + "\n")
        cmd = [py, "-m", "pip_audit", "-r", req, "--disable-pip", "--progress-spinner", "off", "-f", "json"]
        cmd += ["--require-hashes"] if hashes else ["--no-deps"]
        proc = run(cmd, timeout=600)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise Skip(f"pip-audit couldn't run (network?): {(proc.stderr or proc.stdout)[-400:]}") from None
        deps = data.get("dependencies", data if isinstance(data, list) else [])
        vulns = [f"{d['name']} {d['version']}: " + ", ".join(v["id"] for v in d.get("vulns", []))
                 for d in deps if d.get("vulns")]
        assert not vulns, "known vulnerabilities: " + "; ".join(vulns)
        return f"{len(deps)} package(s), no known vulnerabilities"

    @check("QUAL-004", F_DEPS, "pip-audit: the signing toolchain (.github/requirements-signing*.txt, the only "
           "packages that ever see the signing key) has no known vulnerabilities")
    def _():
        text = "".join((REPO / ".github" / n).read_text() for n in ("requirements-signing-build.txt",
                                                                    "requirements-signing.txt"))
        return audit([text], "signing", hashes=True)

    @check("QUAL-005", F_DEPS, "pip-audit: the ESPHome version CI builds the firmware with has no known "
           "vulnerabilities")
    def _():
        return audit([f"esphome=={workflow_pins()['esphome']}"], "esphome")

    @check("QUAL-006", F_DEPS, "pip-audit: the integration's test framework pins (pytest-homeassistant-custom-"
           "component, fonttools) have no known vulnerabilities")
    def _():
        pins = workflow_pins()
        names = [n for n in pins if n != "esphome"]
        assert names, "no test framework pins found in firmware.yml"
        return audit([f"{n}=={pins[n]}" for n in names], "testfw")

    @check("QUAL-007", F_DEPS, "npm advisories: the vendored ESP Web Tools version (the code that runs on the "
           "web installer page) has no known advisory")
    def _():
        ver = re.search(r'ESP_WEB_TOOLS_VERSION = "([^"]+)"', (REPO / ".github/scripts/make_site.py").read_text()).group(1)
        req = urllib.request.Request("https://registry.npmjs.org/-/npm/v1/security/advisories/bulk",
                                     data=json.dumps({"esp-web-tools": [ver]}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https URL
                adv = json.loads(resp.read() or b"{}")
        except Exception as err:  # noqa: BLE001
            raise Skip(f"npm advisory API unreachable: {err}") from None
        hits = adv.get("esp-web-tools", [])
        assert not hits, "; ".join(f"{a.get('severity')} {a.get('title')} {a.get('url')}" for a in hits)
        return f"esp-web-tools {ver}: no advisories (its bundled dependencies aren't listed separately)"

    @check("QUAL-008", F_DEPS, "The integration declares no unpinned Python requirements (manifest.json)")
    def _():
        reqs = json.loads((REPO / "custom_components/magicband/manifest.json").read_text()).get("requirements", [])
        loose = [r for r in reqs if "==" not in r]
        assert not loose, f"unpinned: {loose}"
        return f"{len(reqs)} requirement(s)"

    @check("QUAL-009", F_JS, "node --check passes for the page and panel scripts (frontend/*.js) and the "
           "regression page harness")
    def _():
        files = sorted((REPO / "custom_components/magicband/frontend").glob("*.js")) + \
            sorted((REPO / "regression").glob("*/*.js"))
        bad = []
        for f in files:
            proc = run(["node", "--check", f])
            if proc.returncode != 0:
                bad.append(f"{f.relative_to(REPO)}: {proc.stderr.strip()[:300]}")
        assert not bad, "\n".join(bad)
        return f"{len(files)} file(s)"

    @check("QUAL-010", F_JS, "The page's inline scripts parse (frontend/page.html, after the shared code is "
           "spliced in as panel.py does)")
    def _():
        fe = REPO / "custom_components/magicband/frontend"
        page = (fe / "page.html").read_text().split("/*COMMON*/")
        page = (fe / "common.js").read_text().join(page)
        # Not a security filter: it pulls the page's own inline scripts out to syntax-check them, with the
        # standard library's HTML parser (no regular expression over HTML).
        scripts = inline_scripts(page)
        assert scripts, "no inline scripts found"
        tmp = OUT / ".page-inline.js"
        bad = []
        for i, s in enumerate(scripts):
            tmp.write_text(s)
            proc = run(["node", "--check", tmp])
            if proc.returncode != 0:
                bad.append(f"script {i}: {proc.stderr.strip()[:300]}")
        assert not bad, "\n".join(bad)
        return f"{len(scripts)} inline script(s)"

    @check("QUAL-011", F_HARNESS, "The regression harness's own tests pass (regression/tests: report renderers, "
           "stage selection, ID registry)")
    def _():
        need_tools()
        proc = run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "regression/tests"], timeout=600)
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or ["no output"]
        assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2500:]
        return tail[0]

    counts = {s: sum(r["status"] == s for r in RESULTS) for s in ("pass", "fail", "skip", "manual")}
    stage = {"stage": "quality", "started": started,
             "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "environment": {"tools": tools_note, "pins": TOOLS, "counts": counts}, "results": RESULTS}
    (OUT / "quality.json").write_text(json.dumps(stage, indent=2) + "\n")
    print(f"quality: {counts['pass']} pass, {counts['fail']} fail, {counts['skip']} skip -> {OUT / 'quality.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
