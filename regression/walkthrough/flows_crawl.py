"""Walkthrough: crawl the integration's Home Assistant screens (config flow and options flow) in a test Home Assistant.

Run by regression/walkthrough/run.py with HA_PYTHON (pytest-homeassistant-custom-component), from the repository root:
  python -m pytest -q -p no:cacheprovider regression/walkthrough/flows_crawl.py
Writes the inventory to $WALK_FLOWS_OUT (JSON): every step the flows show, with its menu, fields (and whether each
has a label and help text in strings.json), and every abort or error reason they produced. It changes nothing
outside its throwaway test Home Assistant. Made-up names only (the repository is public).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.magicband.const import DOMAIN

ROOT = Path(__file__).resolve().parents[2]
STRINGS = json.loads((ROOT / "custom_components" / "magicband" / "strings.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture(autouse=True)
def isolated_config_dir(hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)


def _reader(hass: HomeAssistant):
    """A MagicBand reader as ESPHome adds it (as tests/conftest.py makes one)."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er  # noqa: PLC0415

    esphome = MockConfigEntry(domain="esphome", title="Hall reader")
    esphome.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=esphome.entry_id, connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:01:02:03")},
        manufacturer="legal-copy7045", model="magicband-reader", name="Hall reader",
        sw_version="0.10.37 (ESPHome 2026.10.2)")
    ent = er.async_get(hass).async_get_or_create(
        "sensor", "esphome", "aabbcc010203-node", device_id=device.id, config_entry=esphome,
        original_name="ESPHome name", suggested_object_id="hall_reader_esphome_name")
    hass.states.async_set(ent.entity_id, "hall-reader")
    return device


def fields(result) -> list[dict]:
    schema = result.get("data_schema")
    out = []
    for key, val in (schema.schema.items() if schema is not None else []):
        name = str(getattr(key, "schema", key))
        sel = type(val).__name__
        cfg = getattr(val, "config", None)
        options = None
        if isinstance(cfg, dict) and isinstance(cfg.get("options"), list):
            options = [o.get("label", o.get("value")) if isinstance(o, dict) else o for o in cfg["options"]][:20]
        out.append({"name": name, "required": isinstance(key, vol.Required), "selector": sel,
                    **({"options": options} if options is not None else {})})
    return out


def describe(kind: str, result) -> dict:
    """One screen: what Home Assistant would show for this flow result, with its strings.json texts."""
    step = result.get("step_id")
    tr = STRINGS.get(kind, {}).get("step", {}).get(step, {}) if step else {}
    screen = {"flow": kind, "type": str(result["type"]), "step_id": step,
              "title": tr.get("title"), "description": tr.get("description"),
              "errors": result.get("errors") or {}, "reason": result.get("reason")}
    if result["type"] == FlowResultType.MENU:
        opts = result.get("menu_options") or []
        labels = tr.get("menu_options", {})
        screen["menu"] = [{"option": o, "label": labels.get(o)} for o in opts]
    if result["type"] == FlowResultType.FORM:
        screen["fields"] = [{**f, "label": (tr.get("data") or {}).get(f["name"]),
                             "help": (tr.get("data_description") or {}).get(f["name"])} for f in fields(result)]
    if result["type"] == FlowResultType.ABORT:
        screen["reason_text"] = STRINGS.get(kind, {}).get("abort", {}).get(result.get("reason"))
    for err in (result.get("errors") or {}).values():
        screen.setdefault("error_texts", {})[err] = STRINGS.get(kind, {}).get("error", {}).get(err)
    return screen


async def test_crawl_the_flows(hass: HomeAssistant) -> None:
    screens: list[dict] = []
    # Config flow (adding the integration). A second attempt shows what someone who adds it twice sees.
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    screens.append(describe("config", first))
    if first["type"] == FlowResultType.FORM:
        done = await hass.config_entries.flow.async_configure(first["flow_id"], {})
        screens.append(describe("config", done))
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        entry = MockConfigEntry(domain=DOMAIN, title="MagicBand", data={})
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    screens.append({**describe("config", again), "note": "adding it a second time"})

    # Some made-up data, so the people and band screens have something to show: two people, and an unknown
    # band tapped on a (mock) reader.
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Morgan"}, blocking=True)
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Casey"}, blocking=True)
    reader = _reader(hass)
    hass.bus.async_fire("tag_scanned", {"tag_id": "04A1B2C3D4E5F6", "device_id": reader.id})
    await hass.async_block_till_done()

    # Options flow ("Configure"): the menu, then every entry in it.
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    screens.append(describe("options", menu))
    for option in menu.get("menu_options") or []:
        start = await hass.config_entries.options.async_init(entry.entry_id)
        res = await hass.config_entries.options.async_configure(start["flow_id"], {"next_step_id": option})
        screen = {**describe("options", res), "opened_from": option}
        screens.append(screen)
        # One step further where the first screen only picks someone to edit (edit a person -> their details).
        if res["type"] == FlowResultType.FORM:
            pick = [f for f in fields(res) if f["name"] == "person" and f.get("options")]
            if pick and len(fields(res)) == 1 and option.startswith("edit"):  # never submit a removal
                value = next(iter(res["data_schema"].schema.values())).config["options"][0]
                value = value.get("value") if isinstance(value, dict) else value
                nxt = await hass.config_entries.options.async_configure(res["flow_id"], {"person": value})
                screens.append({**describe("options", nxt), "opened_from": f"{option} → a person"})
    out = {"screens": screens,
           "entity_translations": {p: {k: (v or {}).get("name") for k, v in d.items()}
                                   for p, d in STRINGS.get("entity", {}).items()},
           "issues": {k: bool((v or {}).get("title")) for k, v in STRINGS.get("issues", {}).items()}}
    Path(os.environ.get("WALK_FLOWS_OUT", "flows.json")).write_text(json.dumps(out, indent=1, default=str))
