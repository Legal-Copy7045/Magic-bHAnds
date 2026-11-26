"""Tests for the regression harness itself: stage selection, the ID registry and the report renderers.

Run with plain pytest (no Home Assistant needed): python3 -m pytest regression/tests
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import ids  # noqa: E402
import report  # noqa: E402
import run  # noqa: E402

# ───────── stage selection ─────────


def test_default_is_the_regression_stages_only():
    opts = run.parse_args([])
    assert opts["stages"] == run.STAGES and run.WALKTHROUGH not in opts["stages"]
    assert not opts["compile"] and not opts["serial"]


def test_stage_flag_selects_one_or_more_stages():
    assert run.parse_args(["--stage", "page"])["stages"] == ["page"]
    assert run.parse_args(["--stage", "page", "--stage=quality"])["stages"] == ["page", "quality"]
    assert run.parse_args(["page", "live"])["stages"] == ["page", "live"]  # positional still works
    assert run.parse_args(["--stage", "walkthrough"])["stages"] == ["walkthrough"]


def test_with_walkthrough_adds_it_to_the_regression_stages_once():
    assert run.parse_args(["--with-walkthrough"])["stages"] == [*run.STAGES, "walkthrough"]
    assert run.parse_args(["--stage", "walkthrough", "--with-walkthrough"])["stages"] == ["walkthrough"]
    assert run.parse_args(["--stage", "page", "--with-walkthrough", "--compile"]) == {
        "stages": ["page", "walkthrough"], "compile": True, "serial": False}


def test_unknown_stage_is_refused():
    with pytest.raises(SystemExit, match="unknown stage"):
        run.parse_args(["--stage", "nope"])
    with pytest.raises(SystemExit, match="needs a stage"):
        run.parse_args(["--stage"])


def test_walkthrough_writes_outside_the_regression_out_dir():
    assert run.out_dir("walkthrough") != run.OUT and run.out_dir("page") == run.OUT
    assert run.command("quality", False)[-1].endswith("quality/run.py")
    assert run.command("firmware", True)[-1] == "--compile"


# ───────── ID registry ─────────


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(ids, "REG", tmp_path / "ids")
    out = tmp_path / "out"
    out.mkdir()

    def write(stage, results):
        (out / f"{stage}.json").write_text(json.dumps({"stage": stage, "results": results}))
    return out, write


def test_sync_appends_new_ids_and_never_rewrites(registry):
    out, write = registry
    write("page", [{"id": "PAGE-002", "check": "second"}, {"id": "PAGE-001", "check": "first  one"}])
    assert ids.sync("page", out) == ["PAGE-001", "PAGE-002"]
    text = (ids.REG / "page.yaml").read_text()
    assert text.startswith("# Stable check IDs") and 'PAGE-001: "first one"' in text
    write("page", [{"id": "PAGE-001", "check": "renamed"}, {"id": "PAGE-002", "check": "x"},
                   {"id": "PAGE-010", "check": "new"}])
    assert ids.sync("page", out) == ["PAGE-010"]
    assert ids.load("page")["PAGE-001"] == "first one"  # existing text is kept


def test_compare_flags_unregistered_and_vanished_ids_but_not_retired_ones(registry):
    out, write = registry
    (ids.REG).mkdir()
    (ids.REG / "ci.yaml").write_text('CI-001: "a"\nCI-002: "b"\nCI-003: "RETIRED (0.1): gone"\n')
    write("ci", [{"id": "CI-001"}, {"id": "CI-004"}, {"id": "CI-RUN"}])
    assert ids.compare("ci", out) == (["CI-004"], ["CI-002"])


def test_every_committed_registry_is_append_only_shaped():
    for p in sorted((HERE / "ids").glob("*.yaml")):
        data = ids.load(p.stem)
        assert data, p
        prefixes = {k.split("-")[0] for k in data}
        assert len(prefixes) == 1, f"{p.name}: mixed prefixes {prefixes}"


def test_registry_results_one_check_per_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(ids, "REG", tmp_path / "ids")
    monkeypatch.setattr(run, "OUT", tmp_path / "out")
    monkeypatch.setattr(run, "WALK_OUT", tmp_path / "wout")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "quality.json").write_text(json.dumps({"results": [{"id": "QUAL-001", "check": "x"}]}))
    res = run.registry_results(["quality", "page"])
    assert [r["id"] for r in res] == [f"IDS-{run.ALL_STAGES.index('quality') + 1:03d}"]
    assert res[0]["status"] == "fail" and "QUAL-001" in res[0]["detail"]


# ───────── report renderers ─────────

STAGES = {
    "page": {"results": [
        {"id": "PAGE-001", "feature": "F", "check": "ok", "status": "pass"},
        {"id": "PAGE-002", "feature": "F", "check": "<b>bad</b>", "status": "fail", "detail": "broke <script>"}]},
    "quality": {"results": [{"id": "QUAL-004", "feature": "D", "check": "audit", "status": "skip", "detail": "offline"}]},
    "firmware": {"results": [{"id": "FW-300", "feature": "M", "check": "by hand", "status": "manual", "detail": "1. tap"}]},
}
CATALOGUE = [
    {"feature": "Listed", "checks": ["PAGE-001"], "area": "page"},
    {"feature": "By regex", "match": ["page:PAGE-00[12]"], "area": "page"},
    {"feature": "Audit", "match": ["quality:QUAL-00[4-7]"], "area": "quality"},
    {"feature": "Nothing", "area": "page"},
    {"feature": "Not run", "checks": ["LIVE-999"], "area": "live"},
]
FINDINGS = [{"id": "SEC-001", "severity": "low", "area": "page", "title": "T <x>", "verified": True},
            {"id": "BUG-001", "severity": "high", "area": "x", "title": "Worse", "verified": False}]


def test_catalogue_regexes_match_stage_qualified_ids_in_full():
    keys = {"page:PAGE-001", "page:PAGE-002", "page:PAGE-0021", "ci:PAGE-001"}
    assert report.matched_ids({"match": ["page:PAGE-00[12]"]}, keys) == ["PAGE-001", "PAGE-002"]
    assert report.matched_ids({"checks": ["X-1"], "match": ["ci:.*"]}, keys) == ["X-1", "PAGE-001"]


def test_coverage_states():
    rows, unlisted = report.coverage(STAGES, CATALOGUE)
    state = {r["feature"]: r["state"] for r in rows}
    assert state == {"Listed": "pass", "By regex": "fail", "Audit": "skip", "Nothing": "uncovered",
                     "Not run": "not run"}
    assert unlisted == ["FW-300"]


def test_markdown_and_html_render_totals_failures_findings_and_escape():
    cov, unlisted = report.coverage(STAGES, CATALOGUE)
    notes = {"summary": "All <fine>.", "observations": ["one"], "_claims": []}
    md = report.markdown(STAGES, FINDINGS, cov, unlisted, notes, "9.9.9", "now")
    assert "9.9.9" in md and "PAGE-002" in md and "SEC-001" in md and "FW-300" in md
    ordered = sorted(FINDINGS, key=lambda f: report.SEV.index(f["severity"]))  # as load() sorts them
    html = report.page(STAGES, ordered, cov, unlisted, notes, "9.9.9", "now")
    assert "<script>" not in html.replace("<script>window", "")  # page content is escaped
    assert "&lt;b&gt;bad&lt;/b&gt;" in html and "All &lt;fine&gt;." in html
    assert html.index("BUG-001") < html.index("SEC-001")  # findings most severe first (high before low)


def test_report_load_reads_stage_files_findings_and_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUT", tmp_path)
    (tmp_path / "page.json").write_text(json.dumps(STAGES["page"]))
    (tmp_path / "findings-security.json").write_text(json.dumps({"findings": FINDINGS[:1], "claims": [{"c": 1}]}))
    (tmp_path / "findings-bugs.json").write_text(json.dumps(FINDINGS[1:]))
    (tmp_path / "notes.json").write_text(json.dumps({"summary": "s"}))
    (tmp_path / "broken.json").write_text("{")
    stages, findings, catalogue, notes = report.load()
    assert list(stages) == ["page"]
    assert [f["id"] for f in findings] == ["BUG-001", "SEC-001"] and notes["_claims"] == [{"c": 1}]
    assert catalogue  # the committed catalogue loads
