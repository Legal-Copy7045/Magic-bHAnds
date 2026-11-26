"""Tests for the walkthrough's report renderer and its Home Assistant screen checks (no browser or HA needed)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wreport = _load("walk_report", HERE / "walkthrough" / "report.py")
wrun = _load("walk_run", HERE / "walkthrough" / "run.py")

FINDINGS = {"findings": [
    {"id": "W-2", "group": "mobile", "title": "Small <links>", "now": "16 px", "proposal": "44 px", "who": "phone users",
     "effort": "S", "risk": "low", "width": "phone", "evidence": ["shots/a.png"]},
    {"id": "W-1", "group": "rename", "title": "Add vs New", "now": "menu says Add", "proposal": "say Add", "who": "admins",
     "effort": "S", "risk": "none", "width": "both"},
    {"id": "W-3", "group": "bogus", "title": "Unknown group goes last"}],
    "menus": [{"role": "admin", "menu": ["Needs attention", "People"], "why": "most used first"}]}
STAGE = {"results": [{"id": "WALK-101", "check": "menu = heading", "status": "pass"},
                     {"id": "WALK-204", "check": "taps", "status": "fail", "detail": "a <b>16</b>"},
                     {"id": "WALK-901", "check": "by hand", "status": "manual"}]}
INV = {"surfaces": [{"surface": "MagicbHAnds page", "persona": "admin", "width": "phone",
                     "menu": [{"label": "People"}], "screens": [{"heading": "People and access"}]}],
       "home_assistant": {"flows": {"screens": [{"opened_from": "add_person", "step_id": "new_person", "title": "New person",
                                                 "fields": [{"name": "name", "label": "Name"}]}]}},
       "not_crawled": [{"surface": "Readers", "why": "no screen"}]}


@pytest.fixture
def out(tmp_path):
    (tmp_path / "walkthrough.json").write_text(json.dumps(STAGE))
    (tmp_path / "inventory.json").write_text(json.dumps(INV))
    (tmp_path / "findings.json").write_text(json.dumps(FINDINGS))
    (tmp_path / "ids.json").write_text(json.dumps({"results": [{"id": "IDS-007", "check": "ids", "status": "pass"}]}))
    return tmp_path


def test_load_orders_findings_by_group_and_merges_the_id_check(out):
    stage, inv, findings, menus, notes = wreport.load(out)
    assert [f["id"] for f in findings] == ["W-1", "W-2", "W-3"]  # rename, mobile, then unknown
    assert [r["id"] for r in stage["results"]][-1] == "IDS-007"
    assert menus[0]["role"] == "admin" and notes == {}


def test_markdown_lists_failures_groups_menus_and_surfaces(out):
    stage, inv, findings, menus, notes = wreport.load(out)
    md = wreport.markdown(stage, inv, findings, menus, {"summary": "Fine."}, "now")
    assert "WALK-204" in md and "## Rename" in md and "## Mobile" in md and "Needs attention · People" in md
    assert md.index("## Rename") < md.index("## Mobile")


def test_html_escapes_and_embeds_evidence_screenshots(out):
    pil = pytest.importorskip("PIL.Image")
    (out / "shots").mkdir()
    pil.new("RGB", (390, 900), "white").save(out / "shots" / "a.png")
    stage, inv, findings, menus, notes = wreport.load(out)
    html = wreport.page(stage, inv, findings, menus, {"summary": "<x>"}, "now", out)
    assert "Small &lt;links&gt;" in html and "&lt;x&gt;" in html and "<links>" not in html
    assert html.count("data:image/jpeg;base64,") == 1  # W-2's evidence
    assert "New person" in html and "Not crawled: Readers" in html


def test_log_line_counts_and_groups(out):
    stage, inv, findings, menus, notes = wreport.load(out)
    line = wreport.log_line(stage, findings, "2026-11-26", "https://example.invalid/r")
    assert line.startswith("- 2026-11-26: 2 pass, 1 fail, 1 manual")
    assert "failing WALK-204" in line and "rename 1, mobile 1" in line and line.endswith("report https://example.invalid/r")


def _flows(menu_label="Add a person", title="Add a person", field_label="Name", reason_text="No bands yet."):
    return {"screens": [
        {"flow": "options", "type": "FlowResultType.MENU", "step_id": "init", "title": "People and bands",
         "menu": [{"option": "add_person", "label": menu_label}, {"option": "settings", "label": "Settings"}]},
        {"flow": "options", "type": "FlowResultType.FORM", "step_id": "new_person", "title": title, "opened_from": "add_person",
         "fields": [{"name": "name", "label": field_label}]},
        {"flow": "options", "type": "FlowResultType.ABORT", "step_id": None, "reason": "no_bands", "reason_text": reason_text,
         "opened_from": "remove_band"}]}


def test_ha_checks_pass_on_consistent_screens():
    res = {r["id"]: r for r in wrun.ha_checks(_flows(), [{"device": "Hall", "name": "Last tap"}])}
    assert all(res[f"WALK-70{n}"]["status"] == "pass" for n in (1, 2, 3, 4, 5, 7, 8))


def test_ha_checks_flag_mismatched_menu_labels_missing_texts_and_duplicate_names():
    res = {r["id"]: r for r in wrun.ha_checks(_flows(title="New person", field_label=None, reason_text=None),
                                               [{"device": "Hall", "name": "Ring"}, {"device": "Hall", "name": "ring"}])}
    assert res["WALK-701"]["status"] == "fail" and "New person" in res["WALK-701"]["detail"]
    assert res["WALK-702"]["status"] == "fail" and res["WALK-703"]["status"] == "fail"
    assert res["WALK-707"]["status"] == "fail" and "Hall" in res["WALK-707"]["detail"]


def test_ha_checks_skip_without_a_crawl_or_home_assistant():
    res = {r["id"]: r for r in wrun.ha_checks(None, None)}
    assert res["WALK-701"]["status"] == "skip" and res["WALK-707"]["status"] == "skip"
    assert res["WALK-706"]["status"] in ("pass", "fail")  # the static strings.json check always runs
