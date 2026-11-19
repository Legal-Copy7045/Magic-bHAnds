"""MagicBand+ Bluetooth beacons: recognising bands, presence, battery and pairing with NFC."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.magicband.beacons import SIGNATURE_MASK, battery_from_level, parse
from custom_components.magicband.const import DOMAIN, EVENT_BEACON

# Real beacons heard by Home Assistant from two MagicBand+ bands (17 Nov 2026).
REAL = [
    ("C0 0F 01 01 64 1E 26 76 78 E3 A8 42 80 00 35 33 00", -91),
    ("C0 0F 01 01 50 49 DE 75 59 63 8A 57 4A 00 35 33 00", -86),
    ("C0 0F 01 01 62 9F 26 36 38 EF AC 42 C0 00 35 33 00", -88),
    ("C0 0F 01 01 48 48 9C 75 D9 67 8A 57 00 00 35 33 00", -76),
    ("C0 0F 01 01 62 9C 66 76 38 67 AC 52 8A 00 35 33 00", -88),
    ("C0 0F 01 01 48 48 9C 75 99 E7 8E 57 42 00 35 33 00", -89),
    ("C0 0F 01 01 50 1D 66 76 78 EF A8 42 80 00 35 33 00", -90),
    ("C0 0F 01 01 48 4A 9C 75 99 6F 8E 47 00 00 35 33 00", -90),
    ("C0 0F 01 01 50 1C 64 36 F8 67 AC 52 8A 00 35 33 00", -78),
    ("C0 0F 01 01 48 4A 9E 35 D9 EB 8A 47 08 00 35 33 00", -91),
    ("C0 0F 01 01 50 9F 24 36 38 EB A8 42 82 00 35 33 00", -85),
    ("C0 0F 01 01 48 48 DC 75 D9 6B 8E 47 08 00 35 33 00", -86),
    ("0F 11 01 95 EB DD DB 2F 48 63 8B 9B 28 F3 36 EC 7A 2B 33", -87),
    ("0F 11 01 5B 40 5E E0 9F AF 6B 97 AC B6 B2 8B 22 9E 77 46", -88),
    ("C0 0F 01 01 48 48 DC 75 D9 6B 8E 47 08 00 35 33 00", -78),
    ("C0 0F 01 01 50 1C 26 36 78 EB A8 52 8A 00 35 33 00", -85),
    ("C0 0F 01 01 48 4B DC 75 D9 67 8E 57 48 00 35 33 00", -78),
    ("C0 0F 01 01 48 4A DC 75 D9 EF 8A 57 4A 00 35 33 00", -91),
    ("C0 0F 01 01 50 1F 24 76 78 E7 AC 52 C0 00 35 33 00", -64),
    ("0F 11 01 B8 5F FA CD BD 9E 6A A5 8E 51 97 8F DC A6 EF C7", -80),
    ("C0 0F 01 01 50 1F 24 76 78 E7 AC 52 C0 00 35 33 00", -93),
    ("C0 0F 01 01 48 4A DC 75 D9 EF 8A 57 4A 00 35 33 00", -90),
    ("C0 0F 01 01 48 1D 66 36 78 E3 AC 42 82 00 35 33 00", -85),
    ("C0 0F 01 01 32 48 DC 35 99 E3 8A 57 4A 00 35 33 00", -63),
    ("C0 0F 01 01 48 9E 24 36 B8 67 AC 52 C2 00 35 33 00", -86),
    ("C0 0F 01 01 32 4B DC 35 19 EB 8A 47 40 00 35 33 00", -95),
    ("C0 0F 01 01 48 9F 64 76 38 67 AC 42 C0 00 35 33 00", -70),
    ("C0 0F 01 01 32 CA DE 35 99 6B 8E 47 40 00 35 33 00", -60),
    ("C0 0F 01 01 32 CA DE 35 99 6B 8E 47 40 00 35 33 00", -60),
    ("C0 0F 01 01 48 9D 26 36 78 6B A8 42 C0 00 35 33 00", -60),
    ("C0 0F 01 01 32 4A DC 75 19 E7 8A 47 42 00 35 33 00", -71),
    ("C0 0F 01 01 48 9D 26 36 78 6B A8 42 C0 00 35 33 00", -66),
    ("C0 0F 01 01 48 9E 24 36 F8 EF A8 42 C8 00 35 33 00", -62),
    ("C0 0F 01 01 32 C9 DC 75 19 67 8E 57 00 00 35 33 00", -87),
    ("C0 0F 01 01 32 C9 DC 75 19 67 8E 57 00 00 35 33 00", -74),
    ("C0 0F 01 01 48 9E 24 36 F8 EF A8 42 C8 00 35 33 00", -78),]
BAND_X = "C0 0F 01 01 48 9E 24 36 F8 EF A8 42 C8 00 35 33 00"
BAND_Y = "C0 0F 01 01 32 C9 DC 75 19 67 8E 57 00 00 35 33 00"
# A third band, just switched on: the longer C0 13 form.
BAND_Z = [
    "C0 13 01 01 3C 9A 2D B0 B9 6B 8E 16 94 00 36 31 00 00 00 00 00",
    "C0 13 01 01 32 9B 6D F0 79 E7 8E 16 DC 00 36 31 00 00 00 00 00",
]


@pytest.fixture(autouse=True)
def no_beacon_rate_limit(monkeypatch):
    """These tests replay captured beacons back to back; the rate limit has its own tests."""
    from custom_components.magicband import beacons

    monkeypatch.setattr(beacons, "MIN_BEACON_INTERVAL", timedelta(0))


def _tracker(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data.beacons


def _beacon(hass: HomeAssistant, payload: str, rssi: int = -62, source: str = "hci0", address: str = "11:22:33:44:55:66"):
    return _tracker(hass).async_beacon(address, rssi, source, bytes.fromhex(payload))


def test_parse() -> None:
    beacon = parse(bytes.fromhex(BAND_X))
    assert beacon is not None
    assert beacon.level == 0x48
    assert beacon.tail == bytes.fromhex("00353300")
    assert len(SIGNATURE_MASK) == 8
    assert parse(bytes.fromhex("E1 00 CC 03 00 01 00")) is None
    assert parse(bytes.fromhex("C0 0F 01 01 48")) is None
    assert parse(bytes.fromhex("C0 0E 01 01 48 9E 24 36 F8 EF A8 42 C8 00 35 33 00")) is None  # wrong length byte
    long = parse(bytes.fromhex(BAND_Z[0]))
    assert long is not None and long.form == "C0 13" and long.level == 0x3C
    assert battery_from_level(0x48) == 72
    assert battery_from_level(0xC8) is None


async def test_real_beacons_make_two_bands(hass: HomeAssistant, setup_integration) -> None:
    for i, (payload, rssi) in enumerate(REAL):
        _beacon(hass, payload, rssi, address=f"11:22:33:44:55:{i:02X}")
    await hass.async_block_till_done()

    tracker = _tracker(hass)
    assert len(tracker.bands) == 2
    assert len(tracker.encrypted) == 3
    levels = sorted(b.level for b in tracker.bands.values())
    assert levels == [0x32, 0x48]
    x = tracker.find("1c24")
    assert x is not None and [lv for _, lv in x.level_history] == [0x64, 0x62, 0x50, 0x48]
    assert x.variable_bits() != ""

    # Entities for each band.
    nearby = [s for s in hass.states.async_all("binary_sensor") if s.entity_id.endswith("_nearby")]
    assert len(nearby) == 2 and all(s.state == "on" for s in nearby)
    batteries = sorted(
        s.state for s in hass.states.async_all("sensor") if s.entity_id.endswith("_battery")
    )
    assert batteries == ["50", "72"]

    report = await hass.services.async_call(DOMAIN, "list_bluetooth_bands", {}, blocking=True, return_response=True)
    assert len(report["bluetooth_bands"]) == 2
    assert len(report["encrypted_messages"]) == 3


async def test_nearby_goes_off_after_missed_beacons(
    hass: HomeAssistant, setup_integration, freezer: FrozenDateTimeFactory
) -> None:
    _beacon(hass, BAND_X)
    await hass.async_block_till_done()
    entity = next(s.entity_id for s in hass.states.async_all("binary_sensor") if s.entity_id.endswith("_nearby"))
    assert hass.states.get(entity).state == "on"

    freezer.tick(timedelta(minutes=36))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "off"

    _beacon(hass, BAND_X)
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "on"


async def test_give_to_person_names_the_device(hass: HomeAssistant, setup_integration) -> None:
    band = _beacon(hass, BAND_X)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Nana"}, blocking=True)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id[:6], "person": "Nana"}, blocking=True)
    await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"bluetooth_{band.id}")})
    assert device is not None and device.name == "Nana's MagicBand+"

    await hass.services.async_call(DOMAIN, "forget_bluetooth", {"bluetooth_band": band.id}, blocking=True)
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"bluetooth_{band.id}")}) is None
    assert not _tracker(hass).bands


async def test_tap_links_the_only_band_heard(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    band = _beacon(hass, BAND_X)  # known before the tap
    hass.bus.async_fire("tag_scanned", {"tag_id": "04-53-65-2A-C0-5F-80", "device_id": reader_device.id})
    await hass.async_block_till_done()

    freezer.tick(timedelta(minutes=10))
    _beacon(hass, BAND_X, rssi=-45)  # its next beacon, within the window
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert band.band_uid == "0453652AC05F80"
    assert _tracker(hass).for_nfc("04-53-65-2A-C0-5F-80") is band


async def test_tap_with_two_bands_heard_asks(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    x = _beacon(hass, BAND_X)
    y = _beacon(hass, BAND_Y)
    hass.bus.async_fire("tag_scanned", {"tag_id": "0453652AC05F80", "device_id": reader_device.id})
    await hass.async_block_till_done()
    _beacon(hass, BAND_X, rssi=-70)
    _beacon(hass, BAND_Y, rssi=-72)
    freezer.tick(timedelta(minutes=21))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # Two unlinked bands heard and neither clearly closer: nothing is guessed.
    assert x.band_uid is None and y.band_uid is None

    # Linking by hand works, and fires beacon events as normal afterwards.
    await hass.services.async_call(
        DOMAIN, "link_bluetooth", {"bluetooth_band": y.id, "band": "last"}, blocking=True
    )
    assert y.band_uid == "0453652AC05F80"
    events = []
    hass.bus.async_listen(EVENT_BEACON, events.append)
    _beacon(hass, BAND_Y)
    await hass.async_block_till_done()
    assert events[0].data["band"] == "04-53-65-2A-C0-5F-80"


async def test_tap_prefers_the_band_given_to_the_same_person(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Nana"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": "0453652AC05F80", "person": "Nana"}, blocking=True)
    x = _beacon(hass, BAND_X)
    y = _beacon(hass, BAND_Y)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": y.id, "person": "Nana"}, blocking=True)

    hass.bus.async_fire("tag_scanned", {"tag_id": "0453652AC05F80", "device_id": reader_device.id})
    await hass.async_block_till_done()
    _beacon(hass, BAND_X, rssi=-70)
    _beacon(hass, BAND_Y, rssi=-72)
    freezer.tick(timedelta(minutes=21))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert y.band_uid == "0453652AC05F80" and x.band_uid is None


def _band_devices(hass: HomeAssistant) -> dict[str, dr.DeviceEntry]:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    out = {}
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        for domain, ident in device.identifiers:
            if domain == DOMAIN and ident.startswith(("band_", "bluetooth_")):
                out[ident] = device
    return out


def _entities_on(hass: HomeAssistant, device: dr.DeviceEntry) -> list[str]:
    from homeassistant.helpers import entity_registry as er

    return sorted(e.entity_id for e in er.async_entries_for_device(er.async_get(hass), device.id))


async def test_linking_makes_one_band_device(hass: HomeAssistant, setup_integration, reader_device) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Nana"}, blocking=True)
    hass.bus.async_fire("tag_scanned", {"tag_id": "0453652AC05F80", "device_id": reader_device.id})
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "assign_band", {"band": "last", "person": "Nana", "label": "Nana's blue band"}, blocking=True)
    band = _beacon(hass, BAND_X)
    await hass.async_block_till_done()

    devices = _band_devices(hass)
    assert set(devices) == {"band_0453652AC05F80", f"bluetooth_{band.id}"}
    assert len(_entities_on(hass, devices["band_0453652AC05F80"])) == 2  # Last tap, Band type

    # Link: the Bluetooth entities join the NFC band's device; the Bluetooth-only device goes.
    await hass.services.async_call(
        DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "band": "0453652AC05F80"}, blocking=True
    )
    await hass.async_block_till_done()
    devices = _band_devices(hass)
    assert set(devices) == {"band_0453652AC05F80"}
    device = devices["band_0453652AC05F80"]
    assert device.name == "Nana's blue band" and device.model == "MagicBand+"
    entities = _entities_on(hass, device)
    assert len(entities) == 8
    assert any(e.endswith("_nearby") for e in entities) and any(e.endswith("_last_tap") for e in entities)

    result = await hass.services.async_call(DOMAIN, "list", {}, blocking=True, return_response=True)
    assert result["bands"][0]["bluetooth"]["id"] == band.id

    # Unlink: they split again.
    await hass.services.async_call(DOMAIN, "unlink_bluetooth", {"bluetooth_band": band.id}, blocking=True)
    await hass.async_block_till_done()
    devices = _band_devices(hass)
    assert set(devices) == {"band_0453652AC05F80", f"bluetooth_{band.id}"}
    assert len(_entities_on(hass, devices[f"bluetooth_{band.id}"])) == 6
    assert devices["band_0453652AC05F80"].model == "MagicBand"


async def test_removing_the_nfc_band_keeps_the_bluetooth_side(hass: HomeAssistant, setup_integration, reader_device) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": "0453652AC05F80", "device_id": reader_device.id})
    band = _beacon(hass, BAND_X)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "band": "last"}, blocking=True)
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "remove_band", {"band": "0453652AC05F80"}, blocking=True)
    await hass.async_block_till_done()
    devices = _band_devices(hass)
    assert set(devices) == {f"bluetooth_{band.id}"}
    assert len(_entities_on(hass, devices[f"bluetooth_{band.id}"])) == 6


async def test_longer_beacon_form_is_a_band_too(hass: HomeAssistant, setup_integration) -> None:
    _beacon(hass, BAND_X)
    _beacon(hass, BAND_Y)
    for payload in BAND_Z:
        _beacon(hass, payload)
    await hass.async_block_till_done()
    tracker = _tracker(hass)
    assert len(tracker.bands) == 3
    z = tracker.find("182d")
    assert z is not None and z.beacons == 2 and z.forms == ["C0 13"] and z.level == 0x32


async def test_heard_by_and_closest_use_bridge_names(
    hass: HomeAssistant, setup_integration, freezer: FrozenDateTimeFactory
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    # A bridge (ESPHome device): registered by its Wi-Fi MAC; its Bluetooth
    # address (the scanner's source) is that + 2.
    esphome = MockConfigEntry(domain="esphome", title="Kitchen")
    esphome.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=esphome.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "10:b4:1d:d0:b0:74")},
        name="Kitchen MagicBand Bridge",
    )
    # A USB adapter: registered with its Bluetooth address.
    adapter = MockConfigEntry(domain="bluetooth", title="hci1")
    adapter.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=adapter.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, "AA:BB:CC:00:11:22")},
        name="TP-Link UB500 Adapter (AA:BB:CC:00:11:22)",
    )
    from custom_components.magicband.beacons import adapter_name

    assert adapter_name(hass, "AA:BB:CC:00:11:22") == "TP-Link UB500 Adapter"

    band = _beacon(hass, BAND_X, rssi=-58, source="10:B4:1D:D0:B0:76")
    _beacon(hass, BAND_X.replace("C8 00 35", "C0 00 35"), rssi=-75, source="6C:4C:BC:F7:C5:D5")
    await hass.async_block_till_done()

    states = {s.entity_id: s for s in hass.states.async_all("sensor")}
    heard_by = next(s for e, s in states.items() if e.endswith("_heard_by"))
    closest = next(s for e, s in states.items() if e.endswith("_closest"))
    assert heard_by.state == "6C:4C:BC:F7:C5:D5"  # unknown adapter: its address
    assert closest.state == "Kitchen MagicBand Bridge"  # strongest in the last 20 minutes
    assert closest.attributes["heard_in_last_20_minutes"]["Kitchen MagicBand Bridge"] == -58

    # 20 minutes on, only beacons since then count.
    freezer.tick(timedelta(minutes=21))
    _beacon(hass, BAND_X, rssi=-80, source="6C:4C:BC:F7:C5:D5")
    await hass.async_block_till_done()
    assert hass.states.get(closest.entity_id).state == "6C:4C:BC:F7:C5:D5"
    assert band.closest() == ("6C:4C:BC:F7:C5:D5", -80)


async def test_renamed_bluetooth_band_keeps_its_name(hass: HomeAssistant, setup_integration, reader_device) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": "0453652AC05F80", "device_id": reader_device.id})
    band = _beacon(hass, BAND_X)
    await hass.async_block_till_done()
    dev_reg = dr.async_get(hass)
    ble_device = dev_reg.async_get_device(identifiers={(DOMAIN, f"bluetooth_{band.id}")})
    dev_reg.async_update_device(ble_device.id, name_by_user="Jackie's purple band")
    tracker = _tracker(hass)

    # The rename is what the link screen, events and lookups use.
    assert tracker.display_name(band) == "Jackie's purple band"
    assert tracker.find("jackie's purple band") is band

    # Linking to the NFC band carries the name over to the merged device.
    await hass.services.async_call(
        DOMAIN, "link_bluetooth", {"bluetooth_band": "Jackie's purple band", "band": "0453652AC05F80"}, blocking=True
    )
    await hass.async_block_till_done()
    merged = dev_reg.async_get_device(identifiers={(DOMAIN, "band_0453652AC05F80")})
    assert merged is not None and merged.name_by_user == "Jackie's purple band"
    assert dev_reg.async_get_device(identifiers={(DOMAIN, f"bluetooth_{band.id}")}) is None
    assert tracker.display_name(band) == "Jackie's purple band"


async def test_linking_passes_the_owner_to_an_unowned_nfc_band(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Andrew"}, blocking=True)
    band = _beacon(hass, BAND_Z[0])
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "person": "Andrew"}, blocking=True)
    hass.bus.async_fire("tag_scanned", {"tag_id": "04A99C52BE2290", "device_id": reader_device.id})
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "band": "04A99C52BE2290"}, blocking=True
    )
    await hass.async_block_till_done()
    registry = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.registry
    assert registry.get_person(registry.get_band("04A99C52BE2290").person_id).name == "Andrew"
    assert "04A99C52BE2290" in registry.allowed_uids()
    assert _tracker(hass).owner(band)[0].name == "Andrew"


async def test_linking_keeps_the_nfc_bands_existing_owner(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    for name in ("Andrew", "Jackie"):
        await hass.services.async_call(DOMAIN, "add_person", {"name": name}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": "04A99C52BE2290", "person": "Jackie"}, blocking=True)
    band = _beacon(hass, BAND_Z[0])
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "person": "Andrew"}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "band": "04A99C52BE2290"}, blocking=True
    )
    assert _tracker(hass).owner(band)[0].name == "Jackie"


async def test_reader_shows_the_band_name(hass: HomeAssistant, setup_integration, reader_device) -> None:
    from homeassistant.helpers import entity_registry as er

    await hass.services.async_call(DOMAIN, "add_person", {"name": "Jackie"}, blocking=True)
    hass.bus.async_fire("tag_scanned", {"tag_id": "04B0ABDAB61D90", "device_id": reader_device.id})
    await hass.async_block_till_done()
    entity = next(
        e for e in er.async_entries_for_device(er.async_get(hass), reader_device.id) if e.unique_id.endswith("_last_band")
    )
    assert hass.states.get(entity.entity_id).state == "MagicBand 1D90"   # unassigned: its default name

    await hass.services.async_call(DOMAIN, "assign_band", {"band": "last", "person": "Jackie"}, blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "Jackie's MagicBand"
    assert state.attributes["band"] == "04-B0-AB-DA-B6-1D-90" and state.attributes["allowed"] is False
    # On the reader's own device; no extra device for it.
    assert entity.device_id == reader_device.id
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    ours = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [d.id for d in ours if not d.identifiers] == [reader_device.id]   # only the shared reader device


async def test_stray_reader_device_is_cleaned_up(hass: HomeAssistant, reader_device) -> None:
    """A 'Last band name' left on its own device by 0.9.10-0.9.13 moves back to the reader."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.helpers import entity_registry as er
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "persistent_notification", {})
    entry = MockConfigEntry(domain=DOMAIN, title="MagicBand", data={})
    entry.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    stray = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, connections={("bluetooth", "00:11:22:33:44:55")}, name="MagicBand")
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"reader_{reader_device.id}_last_band", config_entry=entry, device_id=stray.id
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert dev_reg.async_get(stray.id) is None
    moved = ent_reg.async_get_entity_id("sensor", DOMAIN, f"reader_{reader_device.id}_last_band")
    assert ent_reg.async_get(moved).device_id == reader_device.id
    assert entry.title == "MagicbHAnds"


async def test_disabled_reader_sensor_is_not_written(hass: HomeAssistant, setup_integration, reader_device) -> None:
    from homeassistant.helpers import entity_registry as er

    hass.bus.async_fire("tag_scanned", {"tag_id": "04B0ABDAB61D90", "device_id": reader_device.id})
    await hass.async_block_till_done()
    ent_reg = er.async_get(hass)
    entity = next(e for e in er.async_entries_for_device(ent_reg, reader_device.id) if e.unique_id.endswith("_last_band"))
    ent_reg.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done()
    # Another tap while it's disabled: no state is written, and nothing fails.
    hass.bus.async_fire("tag_scanned", {"tag_id": "04B0ABDAB61D90", "device_id": reader_device.id})
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id) is None


async def test_management_page_and_sidebar(hass: HomeAssistant, setup_integration, hass_client) -> None:
    from unittest.mock import AsyncMock, patch

    client = await hass_client()
    resp = await client.get("/api/magicband/page")
    assert resp.status == 200
    html = await resp.text()
    assert "window.hdHA" in html and "MagicbHAnds" in html and "/*COMMON*/" not in html and "Sarver" not in html

    # With the frontend loaded, the sidebar entry is added; turning it off removes it.
    from custom_components.magicband import panel

    hass.config.components.add("frontend")
    panels: dict = {}
    with patch.object(panel.panel_custom, "async_register_panel", AsyncMock(side_effect=lambda h, **kw: panels.__setitem__(kw["frontend_url_path"], kw))), \
         patch.object(panel.frontend, "async_remove_panel", side_effect=lambda h, p: panels.pop(p, None)), \
         patch.dict(hass.data, {panel.frontend.DATA_PANELS: panels}):
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        hass.config_entries.async_update_entry(entry, options={"show_in_sidebar": True})
        await hass.async_block_till_done()
        assert panels["magicbhands"]["sidebar_title"] == "MagicbHAnds"
        assert panels["magicbhands"]["require_admin"] is True  # it manages who the readers let in
        hass.config_entries.async_update_entry(entry, options={"show_in_sidebar": False})
        await hass.async_block_till_done()
        assert "magicbhands" not in panels


def _type_select(hass: HomeAssistant, uid: str) -> str:
    from homeassistant.helpers import entity_registry as er

    return er.async_get(hass).async_get_entity_id("select", DOMAIN, f"nfc_{uid}_type")


async def test_standard_band_is_never_paired_over_bluetooth(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": "04-53-65-2A-C0-5F-80", "device_id": reader_device.id})
    await hass.async_block_till_done()
    entity_id = _type_select(hass, "0453652AC05F80")
    assert hass.states.get(entity_id).state == "unknown"

    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "classic"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "classic"
    assert hass.states.get(entity_id).attributes["band_type_set_by"] == "you"

    # an unlinked MagicBand+ is around when the standard band is tapped: it must not be linked to it
    band = _beacon(hass, BAND_X)
    hass.bus.async_fire("tag_scanned", {"tag_id": "04-53-65-2A-C0-5F-80", "device_id": reader_device.id})
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=10))
    _beacon(hass, BAND_X, rssi=-45)
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert band.band_uid is None

    result = await hass.services.async_call(DOMAIN, "list", {}, blocking=True, return_response=True)
    assert result["bands"][0]["band_type"] == "classic"


async def test_linked_band_is_a_magicband_plus(hass: HomeAssistant, setup_integration, reader_device) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": "04A99C52BE2290", "device_id": reader_device.id})
    await hass.async_block_till_done()
    entity_id = _type_select(hass, "04A99C52BE2290")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "classic"}, blocking=True
    )
    band = _beacon(hass, BAND_Z[0])
    await hass.services.async_call(
        DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "band": "04A99C52BE2290"}, blocking=True
    )
    await hass.async_block_till_done()
    # linking proves it has Bluetooth, so the wrong "standard" is corrected
    assert hass.states.get(entity_id).state == "plus"
