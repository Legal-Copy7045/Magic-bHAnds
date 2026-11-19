"""Fixtures for MagicBand integration tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.magicband.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components/ in every test."""
    return


@pytest.fixture(autouse=True)
def isolated_config_dir(hass: HomeAssistant, tmp_path):
    """Give each test its own config folder (the integration writes blueprints there)."""
    hass.config.config_dir = str(tmp_path)


@pytest.fixture
async def reader_device(hass: HomeAssistant) -> dr.DeviceEntry:
    """A device that looks like a MagicBand reader added through ESPHome."""
    return make_esphome_device(hass, "lounge-reader", "magicband-reader", "Lounge reader")


def make_esphome_device(hass: HomeAssistant, node: str, model: str, name: str | None = None) -> dr.DeviceEntry:
    """An ESPHome device as the ESPHome integration creates it, with its "ESPHome name" sensor (reader firmware 0.10.4+)."""
    esphome_entry = MockConfigEntry(domain="esphome", title=name or node)
    esphome_entry.add_to_hass(hass)
    mac = "aa:bb:cc:" + ":".join(f"{b:02x}" for b in abs(hash(node)).to_bytes(8, "big")[-3:])
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=esphome_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        manufacturer="legal-copy7045",
        model=model,
        name=name or node,
        sw_version="0.10.4 (ESPHome 2026.10.2)",
    )
    ent = er.async_get(hass).async_get_or_create(
        "sensor", "esphome", f"{mac}-node", device_id=device.id, config_entry=esphome_entry,
        original_name="ESPHome name", suggested_object_id=f"{node.replace('-', '_')}_esphome_name",
    )
    hass.states.async_set(ent.entity_id, node)
    return device


@pytest.fixture
async def other_device(hass: HomeAssistant) -> dr.DeviceEntry:
    """Some other device that also scans tags (e.g. a phone)."""
    other_entry = MockConfigEntry(domain="mobile_app", title="Phone")
    other_entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("mobile_app", "phone1")},
        name="Alex's phone",
    )


@pytest.fixture
async def setup_integration(hass: HomeAssistant) -> MockConfigEntry:
    """Set up MagicBand."""
    assert await async_setup_component(hass, "persistent_notification", {})
    entry = MockConfigEntry(domain=DOMAIN, title="MagicBand", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
