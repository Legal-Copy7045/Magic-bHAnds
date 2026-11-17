"""MagicBand+ Bluetooth beacons: recognising bands, presence, battery and pairing with NFC."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
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
    assert len(_entities_on(hass, devices["band_0453652AC05F80"])) == 1  # Last tap

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
    assert len(entities) == 5
    assert any(e.endswith("_nearby") for e in entities) and any(e.endswith("_last_tap") for e in entities)

    result = await hass.services.async_call(DOMAIN, "list", {}, blocking=True, return_response=True)
    assert result["bands"][0]["bluetooth"]["id"] == band.id

    # Unlink: they split again.
    await hass.services.async_call(DOMAIN, "unlink_bluetooth", {"bluetooth_band": band.id}, blocking=True)
    await hass.async_block_till_done()
    devices = _band_devices(hass)
    assert set(devices) == {"band_0453652AC05F80", f"bluetooth_{band.id}"}
    assert len(_entities_on(hass, devices[f"bluetooth_{band.id}"])) == 4
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
    assert len(_entities_on(hass, devices[f"bluetooth_{band.id}"])) == 4


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
