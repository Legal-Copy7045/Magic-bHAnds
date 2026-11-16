"""Fixtures for MagicBand integration tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from custom_components.magicband.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components/ in every test."""
    return


@pytest.fixture
async def reader_device(hass: HomeAssistant) -> dr.DeviceEntry:
    """A device that looks like a MagicBand reader added through ESPHome."""
    esphome_entry = MockConfigEntry(domain="esphome", title="MagicBand Reader")
    esphome_entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=esphome_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:01")},
        manufacturer="legal-copy7045",
        model="magicband-reader",
        name="Lounge reader",
    )


@pytest.fixture
async def other_device(hass: HomeAssistant) -> dr.DeviceEntry:
    """Some other device that also scans tags (e.g. a phone)."""
    other_entry = MockConfigEntry(domain="mobile_app", title="Phone")
    other_entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("mobile_app", "phone1")},
        name="Steve's phone",
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
