"""End-to-end tests for the MagicBand integration."""

from datetime import timedelta

from pytest_homeassistant_custom_component.common import async_capture_events, async_mock_service

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.magicband.config_flow import NEW_PERSON
from custom_components.magicband.const import DOMAIN, EVENT_TAP

NANA_BAND = "04-11-22-33-44-55-66"
JACKIE_BAND_1 = "04-53-65-2A-C0-5F-80"
JACKIE_BAND_2 = "04-AA-BB-CC-DD-EE-FF"


async def _tap(hass: HomeAssistant, tag_id: str, device_id: str) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": tag_id, "device_id": device_id})
    await hass.async_block_till_done()


def _registry(entry):
    return entry.runtime_data.registry


async def test_config_flow_creates_single_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert again["type"] is FlowResultType.ABORT


async def test_unknown_band_is_logged_denied_and_notified(hass, setup_integration, reader_device) -> None:
    taps = async_capture_events(hass, EVENT_TAP)
    await _tap(hass, NANA_BAND, reader_device.id)

    band = _registry(setup_integration).get_band(NANA_BAND)
    assert band is not None and band.scans == 1 and band.last_reader == "Lounge reader"
    assert taps[-1].data["allowed"] is False
    assert taps[-1].data["known"] is False
    assert taps[-1].data["band"] == NANA_BAND

    notifications = hass.data["persistent_notification"]
    assert f"{DOMAIN}_unknown_04112233445566" in notifications

    assert hass.states.get("sensor.magicband_unknown_bands").state == "1"


async def test_scans_from_other_devices_are_ignored(hass, setup_integration, other_device) -> None:
    await _tap(hass, NANA_BAND, other_device.id)
    assert _registry(setup_integration).get_band(NANA_BAND) is None


async def test_people_with_and_without_ha_users_and_multiple_bands(
    hass, setup_integration, reader_device
) -> None:
    calls = async_mock_service(hass, "esphome", "lounge_reader_set_known_bands")
    taps = async_capture_events(hass, EVENT_TAP)

    # Nana is not an HA user; Jackie is, with two bands.
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Nana"}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "add_person", {"name": "Jackie", "ha_person": "person.jackie"}, blocking=True
    )
    await hass.services.async_call(DOMAIN, "assign_band", {"band": NANA_BAND, "person": "Nana"}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "assign_band", {"band": JACKIE_BAND_1, "person": "Jackie", "label": "blue"}, blocking=True
    )
    await hass.services.async_call(
        DOMAIN, "assign_band", {"band": JACKIE_BAND_2, "person": "person.jackie", "label": "plus"}, blocking=True
    )

    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    synced = calls[-1].data["bands"].split(",")
    assert sorted(synced) == sorted(["04112233445566", "0453652AC05F80", "04AABBCCDDEEFF"])

    # Jackie taps her second band.
    await _tap(hass, JACKIE_BAND_2, reader_device.id)
    data = taps[-1].data
    assert data["person"] == "Jackie"
    assert data["ha_person"] == "person.jackie"
    assert data["label"] == "plus"
    assert data["allowed"] is True

    # Nana taps in: known, not an HA user.
    await _tap(hass, NANA_BAND, reader_device.id)
    assert taps[-1].data["person"] == "Nana"
    assert taps[-1].data["ha_person"] is None
    assert taps[-1].data["allowed"] is True

    # Per-person sensors exist and track the last tap.
    nana = hass.states.get("sensor.magicband_nana_last_tap")
    jackie = hass.states.get("sensor.magicband_jackie_last_tap")
    assert nana is not None and nana.state not in ("unknown", "unavailable")
    assert jackie is not None and len(jackie.attributes["bands"]) == 2

    # Disallowing Nana removes her band from the readers' list.
    await hass.services.async_call(DOMAIN, "update_person", {"person": "Nana", "allowed": False}, blocking=True)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert "04112233445566" not in calls[-1].data["bands"].split(",")
    assert len(calls[-1].data["bands"].split(",")) == 2


async def test_changes_sync_automatically(hass, setup_integration) -> None:
    calls = async_mock_service(hass, "esphome", "lounge_reader_set_known_bands")
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Nana"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": NANA_BAND, "person": "Nana"}, blocking=True)

    # The debouncer waits a couple of seconds, then pushes once.
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()
    assert calls and calls[-1].data["bands"] == "04112233445566"


async def test_assign_last_band_and_list(hass, setup_integration, reader_device) -> None:
    await _tap(hass, JACKIE_BAND_1, reader_device.id)
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Jackie"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": "last", "person": "Jackie"}, blocking=True)

    result = await hass.services.async_call(DOMAIN, "list", {}, blocking=True, return_response=True)
    assert result["people"][0]["name"] == "Jackie"
    assert result["people"][0]["bands"] == [JACKIE_BAND_1]
    assert result["bands"][0]["allowed"] is True
    # Assigning dismisses the unknown-band notification.
    assert f"{DOMAIN}_unknown_0453652AC05F80" not in hass.data["persistent_notification"]


async def test_options_flow_assigns_new_band_to_new_person(hass, setup_integration, reader_device) -> None:
    await _tap(hass, NANA_BAND, reader_device.id)

    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "assign_band"})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "assign_band"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"band": "04112233445566", "person": NEW_PERSON, "label": "Nana's band"}
    )
    assert result["step_id"] == "new_person"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Nana", "allowed": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    registry = _registry(setup_integration)
    nana = registry.find_person("Nana")
    assert nana is not None and nana.ha_person is None
    assert registry.band_allowed(NANA_BAND)
    assert registry.get_band(NANA_BAND).label == "Nana's band"


async def test_options_flow_edit_person_links_ha_user(hass, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Jackie"}, blocking=True)
    jackie = _registry(setup_integration).find_person("Jackie")

    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "edit_person"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"person": jackie.id})
    assert result["step_id"] == "edit_person_details"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Jackie", "ha_person": "person.jackie", "allowed": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _registry(setup_integration).find_person("Jackie").ha_person == "person.jackie"


async def test_data_survives_reload(hass, setup_integration, reader_device) -> None:
    await _tap(hass, NANA_BAND, reader_device.id)
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Nana"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": NANA_BAND, "person": "Nana"}, blocking=True)

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))  # flush delayed save
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    registry = _registry(setup_integration)
    assert registry.band_allowed(NANA_BAND)
    assert registry.get_band(NANA_BAND).scans == 1


async def test_removing_person_unassigns_bands(hass, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Nana"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": NANA_BAND, "person": "Nana"}, blocking=True)
    await hass.services.async_call(DOMAIN, "remove_person", {"person": "Nana"}, blocking=True)
    registry = _registry(setup_integration)
    assert registry.get_band(NANA_BAND).person_id is None
    assert not registry.band_allowed(NANA_BAND)
