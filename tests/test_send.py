"""Tests for magicband.send, bridge discovery and the bundled blueprint."""

import json
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.magicband.blueprint_installer import async_install_blueprints
from custom_components.magicband.bridges import build_command, find_bridges
from custom_components.magicband.const import DOMAIN

REPO = Path(__file__).resolve().parents[1]


def _add_bridge(hass: HomeAssistant, name: str, mac: str, *, with_light: bool = True) -> str:
    """Register an ESPHome device with a Command text entity (and MagicBand light)."""
    esphome_entry = MockConfigEntry(domain="esphome", title=name)
    esphome_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=esphome_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        name=name,
    )
    ent_reg = er.async_get(hass)
    command = ent_reg.async_get_or_create(
        "text", "esphome", f"{mac}-command", device_id=device.id, original_name="Command",
        config_entry=esphome_entry, suggested_object_id=f"{name}_command",
    )
    if with_light:
        ent_reg.async_get_or_create(
            "light", "esphome", f"{mac}-magicband", device_id=device.id, original_name="MagicBand",
            config_entry=esphome_entry, suggested_object_id=f"{name}_magicband",
        )
    return command.entity_id


async def test_find_bridges_by_light_not_name(hass: HomeAssistant) -> None:
    # Names don't matter: the SCREEK board has no "magicband" in its name.
    a = _add_bridge(hass, "virtual_screek_bp2_poe_849a4c", "aa:00:00:00:00:01")
    b = _add_bridge(hass, "kitchen_magicband_bridge", "aa:00:00:00:00:02")
    _add_bridge(hass, "some_other_device", "aa:00:00:00:00:03", with_light=False)
    assert find_bridges(hass) == sorted([a, b])


async def test_send_to_all_bridges(hass: HomeAssistant, setup_integration) -> None:
    a = _add_bridge(hass, "bp2", "aa:00:00:00:00:01")
    b = _add_bridge(hass, "kitchen", "aa:00:00:00:00:02")
    calls = async_mock_service(hass, "text", "set_value")

    result = await hass.services.async_call(
        DOMAIN, "send", {"effect": "color", "color": "red", "vibration": 1, "always_on": True},
        blocking=True, return_response=True,
    )
    assert sorted(result["bridges"]) == sorted([a, b])
    assert sorted(calls[-1].data["entity_id"]) == sorted([a, b])
    assert json.loads(calls[-1].data["value"]) == {
        "effect": "color", "color": "red", "always_on": True, "vibration": 1,
    }


async def test_send_off_is_the_string_off(hass: HomeAssistant, setup_integration) -> None:
    _add_bridge(hass, "bp2", "aa:00:00:00:00:01")
    calls = async_mock_service(hass, "text", "set_value")
    await hass.services.async_call(DOMAIN, "send", {"effect": "off"}, blocking=True)
    assert json.loads(calls[-1].data["value"]) == {"effect": "off"}


async def test_send_to_chosen_bridge_only(hass: HomeAssistant, setup_integration) -> None:
    a = _add_bridge(hass, "bp2", "aa:00:00:00:00:01")
    _add_bridge(hass, "kitchen", "aa:00:00:00:00:02")
    calls = async_mock_service(hass, "text", "set_value")
    await hass.services.async_call(
        DOMAIN, "send", {"effect": "animation", "animation": "lightning", "bridges": [a]}, blocking=True
    )
    assert calls[-1].data["entity_id"] == [a]
    assert json.loads(calls[-1].data["value"]) == {"effect": "animation", "name": "lightning"}


async def test_send_with_no_bridges_is_a_clear_error(hass: HomeAssistant, setup_integration) -> None:
    with pytest.raises(ServiceValidationError, match="No MagicBand bridges found"):
        await hass.services.async_call(DOMAIN, "send", {"effect": "buzz", "vibration": 3}, blocking=True)


def test_build_command_per_effect() -> None:
    assert build_command({"effect": "rgb", "rgb_color": [255, 0, 180], "color": "red", "vibration": 0}) == {
        "effect": "rgb", "rgb": [255, 0, 180], "vibration": 0,
    }
    assert build_command({"effect": "dual_color", "color": "cyan", "color2": "white", "vibration": 2}) == {
        "effect": "dual_color", "color": "cyan", "color2": "white", "vibration": 2,
    }
    assert build_command({"effect": "five_color", "colors": "red, blue", "color": "x"}) == {
        "effect": "five_color", "colors": "red, blue",
    }
    assert build_command({"command": {"effect": "raw", "hex": "E9 05"}}) == {"effect": "raw", "hex": "E9 05"}


async def test_blueprint_is_installed(hass: HomeAssistant, setup_integration) -> None:
    target = Path(hass.config.config_dir, "blueprints/automation/magicband/magicband_notify.yaml")
    assert target.is_file()
    assert "magicband.send" in target.read_text()


async def test_imported_blueprint_is_updated_in_place(hass: HomeAssistant) -> None:
    imported = Path(hass.config.config_dir, "blueprints/automation/Legal-Copy7045/magicband_notify.yaml")
    imported.parent.mkdir(parents=True, exist_ok=True)
    imported.write_text(
        "blueprint:\n  name: old\n  source_url: https://github.com/Legal-Copy7045/Magic-bHAnds/blob/main/x.yaml\n"
    )
    written = await async_install_blueprints(hass)
    assert written == [imported]
    assert "magicband.send" in imported.read_text()
    # No second copy is created alongside it.
    assert not Path(hass.config.config_dir, "blueprints/automation/magicband/magicband_notify.yaml").exists()
    # Already current: nothing to write.
    assert await async_install_blueprints(hass) == []


def test_repo_blueprint_matches_bundled_copy() -> None:
    bundled = REPO / "custom_components/magicband/blueprints/magicband_notify.yaml"
    repo = REPO / "homeassistant/blueprints/automation/magicband_notify.yaml"
    assert bundled.read_text() == repo.read_text()
