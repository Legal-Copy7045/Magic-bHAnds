"""Schedules, enrolment, personal welcome colours, history, charge reminders, repairs, reader health, diagnostics."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.magicband.const import DOMAIN
from custom_components.magicband.registry import Band
from tests.conftest import make_esphome_device

TAG = "04AABBCCDDEEFF"
BAND_X = "C0 0F 01 01 48 9E 24 36 F8 EF A8 42 C8 00 35 33 00"


def _data(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data


async def _person_with_band(hass: HomeAssistant, name: str = "Alice", uid: str = TAG) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": name}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": uid, "person": name}, blocking=True)


def _tap(hass: HomeAssistant, uid: str, device_id: str) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": uid, "device_id": device_id})


def _reader_calls(hass: HomeAssistant, node: str = "lounge-reader") -> dict[str, list[ServiceCall]]:
    calls: dict[str, list[ServiceCall]] = {"bands": [], "colours": []}
    prefix = node.replace("-", "_")
    hass.services.async_register("esphome", f"{prefix}_set_known_bands", lambda c: calls["bands"].append(c))
    hass.services.async_register("esphome", f"{prefix}_set_band_colours", lambda c: calls["colours"].append(c))
    return calls


# ---------------------------------------------------------------------------- schedules and expiry


def test_band_schedule_rules() -> None:
    tz = dt_util.get_default_time_zone()
    monday_10 = datetime(2026, 11, 16, 10, 0, tzinfo=tz)
    band = Band(uid=TAG, access_from="07:00", access_until="21:00")
    assert band.in_schedule(monday_10)
    assert not band.in_schedule(monday_10.replace(hour=22))
    band = Band(uid=TAG, access_from="22:00", access_until="06:00", access_days=["fri"])
    assert band.in_schedule(datetime(2026, 11, 20, 23, 0, tzinfo=tz))  # Friday night
    assert band.in_schedule(datetime(2026, 11, 21, 2, 0, tzinfo=tz))  # ...into Saturday morning
    assert not band.in_schedule(datetime(2026, 11, 21, 23, 0, tzinfo=tz))  # Saturday night
    band = Band(uid=TAG, access_days=["sat", "sun"])
    assert not band.in_schedule(monday_10) and band.in_schedule(datetime(2026, 11, 22, 10, 0, tzinfo=tz))
    band = Band(uid=TAG, expires=(monday_10 + timedelta(hours=1)).isoformat())
    assert band.in_schedule(monday_10) and not band.in_schedule(monday_10 + timedelta(hours=2))


async def test_expired_band_is_denied_and_leaves_the_readers_list(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    calls = _reader_calls(hass)
    await _person_with_band(hass)
    expires = dt_util.now() + timedelta(minutes=30)
    await hass.services.async_call(
        DOMAIN, "set_band_access", {"band": TAG, "expires": expires.isoformat()}, blocking=True
    )
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert TAG in calls["bands"][-1].data["bands"]

    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)  # the minute check notices the list changed...
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=3))
    async_fire_time_changed(hass)  # ...and the debounced sync runs
    await hass.async_block_till_done()
    assert calls["bands"][-1].data["bands"] == ""

    taps = []
    hass.bus.async_listen("magicband_tap", lambda e: taps.append(e.data["allowed"]))
    _tap(hass, TAG, reader_device.id)
    await hass.async_block_till_done()
    assert taps == [False]

    await hass.services.async_call(DOMAIN, "set_band_access", {"band": TAG, "clear": True}, blocking=True)
    assert _data(hass).registry.band_allowed(TAG)


async def test_set_band_access_needs_a_known_band(hass: HomeAssistant, setup_integration) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_band_access", {"band": TAG, "from": "07:00"}, blocking=True)


# ---------------------------------------------------------------------------- enrolment


async def test_enrolment_gives_the_next_unowned_bands_to_one_person(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    await _person_with_band(hass, "Bob", "04C1D2E3F40590")
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Alice"}, blocking=True)
    state = await hass.services.async_call(
        DOMAIN, "enrol", {"person": "Alice", "minutes": 2, "label": "Alice's band"}, blocking=True, return_response=True
    )
    assert state["person"] == "Alice"
    assert hass.states.get("sensor.magicband_unknown_bands").attributes["enrolling"]["person"] == "Alice"

    for uid in ("04AABBCCDD0001", "04AABBCCDD0002", "04C1D2E3F40590"):  # the last is Bob's
        _tap(hass, uid, reader_device.id)
        await hass.async_block_till_done()
    registry = _data(hass).registry
    alice = registry.find_person("Alice")
    assert sorted(b.uid for b in registry.bands_for(alice.id)) == ["04AABBCCDD0001", "04AABBCCDD0002"]
    assert registry.get_band("04AABBCCDD0002").label == "Alice's band 2"
    assert registry.get_person(registry.get_band("04C1D2E3F40590").person_id).name == "Bob"  # never taken

    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _data(hass).enrolment is None
    _tap(hass, "04AABBCCDD0003", reader_device.id)
    await hass.async_block_till_done()
    assert registry.get_band("04AABBCCDD0003").person_id is None


async def test_the_enrolling_tap_never_counts_as_allowed(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    taps = []
    hass.bus.async_listen("magicband_tap", lambda e: taps.append(e.data))
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Alice"}, blocking=True)
    await hass.services.async_call(DOMAIN, "enrol", {"person": "Alice"}, blocking=True)
    _tap(hass, "04AABBCCDD0001", reader_device.id)
    await hass.async_block_till_done()
    assert taps[-1]["enrolled"] is True and taps[-1]["allowed"] is False  # it was unknown a moment ago
    _tap(hass, "04AABBCCDD0001", reader_device.id)
    await hass.async_block_till_done()
    assert taps[-1]["enrolled"] is False and taps[-1]["allowed"] is True  # its next tap is let in


async def test_enrolment_can_be_limited_to_one_reader(hass: HomeAssistant, setup_integration, reader_device) -> None:
    door = make_esphome_device(hass, "door-reader", "magicband-reader", "Front door")
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Alice"}, blocking=True)
    await hass.services.async_call(DOMAIN, "enrol", {"person": "Alice", "device_id": reader_device.id}, blocking=True)
    _tap(hass, "04AABBCCDD0009", door.id)  # someone at the front door
    await hass.async_block_till_done()
    registry = _data(hass).registry
    assert registry.get_band("04AABBCCDD0009").person_id is None
    _tap(hass, "04AABBCCDD0001", reader_device.id)
    await hass.async_block_till_done()
    assert registry.get_band("04AABBCCDD0001").person_id is not None
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "enrol", {"person": "Alice", "device_id": "not-a-reader"}, blocking=True)


async def test_enrolment_is_limited_and_can_be_stopped(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Alice"}, blocking=True)
    with pytest.raises(Exception):  # noqa: B017 - voluptuous refuses more than 15 minutes
        await hass.services.async_call(DOMAIN, "enrol", {"person": "Alice", "minutes": 60}, blocking=True)
    await hass.services.async_call(DOMAIN, "enrol", {"person": "Alice"}, blocking=True)
    await hass.services.async_call(DOMAIN, "stop_enrolment", {}, blocking=True)
    assert _data(hass).enrolment is None


# ---------------------------------------------------------------------------- personal welcome


async def test_welcome_colours_go_to_readers(hass: HomeAssistant, setup_integration, reader_device) -> None:
    calls = _reader_calls(hass)
    await _person_with_band(hass)
    await hass.services.async_call(DOMAIN, "update_person", {"person": "Alice", "welcome_colour": "Purple"}, blocking=True)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls["colours"][-1].data["colours"] == f"{TAG}=Purple"
    with pytest.raises(Exception):  # noqa: B017 - not a reader colour
        await hass.services.async_call(DOMAIN, "update_person", {"person": "Alice", "welcome_colour": "Plaid"}, blocking=True)
    await hass.services.async_call(DOMAIN, "update_person", {"person": "Alice", "welcome_colour": ""}, blocking=True)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls["colours"][-1].data["colours"] == ""


# ---------------------------------------------------------------------------- history


async def test_tap_history_and_logbook(hass: HomeAssistant, setup_integration, reader_device) -> None:
    await _person_with_band(hass)
    _tap(hass, TAG, reader_device.id)
    _tap(hass, "04AABBCCDD0009", reader_device.id)
    await hass.async_block_till_done()
    result = await hass.services.async_call(DOMAIN, "history", {"count": 10}, blocking=True, return_response=True)
    taps = result["taps"]
    assert [t["allowed"] for t in taps] == [False, True]
    assert taps[1]["person"] == "Alice" and taps[1]["reader"] == "Lounge reader"

    from custom_components.magicband import logbook

    described = {}
    logbook.async_describe_events(hass, lambda domain, event_type, fn: described.setdefault(event_type, fn))

    class _Event:
        data = {"name": "Alice's MagicBand", "allowed": True, "reader": "Front Door"}

    assert described["magicband_tap"](_Event()) == {"name": "Alice's MagicBand", "message": "welcomed at Front Door"}


# ---------------------------------------------------------------------------- charge me


async def test_low_battery_repair_and_event(hass: HomeAssistant, setup_integration) -> None:
    events = []
    hass.bus.async_listen("magicband_battery_low", lambda e: events.append(e.data))
    beacons = _data(hass).beacons

    def beacon(level: int, source: str) -> None:
        p = bytearray(bytes.fromhex(BAND_X))
        p[4] = level
        beacons.async_beacon("11:22:33:44:55:66", -60, source, bytes(p))

    beacon(50, "a")
    beacon(15, "b")
    beacon(15, "c")  # still low: only one reminder
    await hass.async_block_till_done()
    band = next(iter(beacons.bands.values()))
    assert len(events) == 1 and events[0]["battery"] == 15
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"battery_low_{band.id}") is not None
    beacon(80, "d")  # charged
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"battery_low_{band.id}") is None


async def test_charge_me_blueprint_ships(hass: HomeAssistant, setup_integration) -> None:
    from pathlib import Path

    path = Path(hass.config.config_dir) / "blueprints" / "automation" / "magicband" / "magicband_charge_me.yaml"
    assert path.is_file() and "magicband_battery_low" in path.read_text()


# ---------------------------------------------------------------------------- reader health and repairs


async def test_reader_status_and_offline_repair(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    calls = _reader_calls(hass)
    await _person_with_band(hass)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    await hass.async_block_till_done()
    sensor = next(
        s for s in hass.states.async_all("sensor") if "allowed_list" in s.entity_id
    )
    assert sensor.state == "up_to_date" and sensor.attributes["bands"] == 1 and sensor.attributes["welcome_colours"]
    assert calls["bands"]

    hass.services.async_remove("esphome", "lounge_reader_set_known_bands")  # the reader went offline
    for _ in range(16):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert hass.states.get(sensor.entity_id).state == "offline"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"reader_offline_{reader_device.id}") is not None

    hass.services.async_register("esphome", "lounge_reader_set_known_bands", lambda c: None)
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"reader_offline_{reader_device.id}") is None


async def test_older_reader_firmware_is_unconfirmed(hass: HomeAssistant, setup_integration) -> None:
    from homeassistant.helpers import device_registry as dr

    device = make_esphome_device(hass, "old-reader", "magicband-reader")
    dr.async_get(hass).async_update_device(device.id, sw_version="0.10.3 (ESPHome 2026.10.2)")
    _reader_calls(hass, "old-reader")
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert _data(hass).readers.status_of(device.id).state == "unconfirmed"


async def test_readers_found_by_mac_without_the_name_sensor(hass: HomeAssistant, setup_integration) -> None:
    """Firmware before 0.10.4 has no "ESPHome name" sensor: its default name comes from its MAC."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    device = make_esphome_device(hass, "x", "magicband-reader")
    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_device(ent_reg, device.id):
        hass.states.async_remove(entity.entity_id)
    mac = next(v for k, v in device.connections if k == dr.CONNECTION_NETWORK_MAC).replace(":", "")[-6:]
    calls = _reader_calls(hass, f"magicband-reader-{mac}")
    await _person_with_band(hass)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls["bands"]


# ---------------------------------------------------------------------------- settings and diagnostics


async def test_battery_reminder_setting(hass: HomeAssistant, setup_integration) -> None:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "settings"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"show_in_sidebar": True, "battery_reminder_level": 40}
    )
    await hass.async_block_till_done()
    assert _data(hass).beacons.battery_low_level == 40


async def test_diagnostics_hide_ids_and_names(hass: HomeAssistant, setup_integration, reader_device) -> None:
    from custom_components.magicband.diagnostics import async_get_config_entry_diagnostics

    await _person_with_band(hass, "Alice Example")
    _data(hass).beacons.async_beacon("11:22:33:44:55:66", -60, "hci0", bytes.fromhex(BAND_X))
    diag = await async_get_config_entry_diagnostics(hass, hass.config_entries.async_entries(DOMAIN)[0])
    text = str(diag)
    assert TAG not in text and "AA-BB-CC-DD-EE-FF" not in text
    assert "Alice" not in text
    assert next(iter(_data(hass).beacons.bands)) not in text  # no Bluetooth signature
    assert diag["bands"][0]["band"].endswith("EE-FF") and diag["allowed_count"] == 1


# ---------------------------------------------------------------------------- light shows


async def test_play_show_goes_to_every_online_reader(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    shows: list[ServiceCall] = []
    hass.services.async_register("esphome", "lounge_reader_play_show", lambda c: shows.append(c))
    make_esphome_device(hass, "hall-reader", "magicband-reader", "Hall reader")  # offline: no actions
    result = await hass.services.async_call(
        DOMAIN, "play_show", {"show": "Fireworks"}, blocking=True, return_response=True
    )
    assert [c.data["show"] for c in shows] == ["Fireworks"]
    assert shows[0].context is not None
    assert result["skipped"] == ["Hall reader"] and len(result["played"]) == 1
    await hass.services.async_call(DOMAIN, "play_show", {"device_id": [reader_device.id]}, blocking=True)
    assert shows[-1].data["show"] == "Random"
    with pytest.raises(Exception):
        await hass.services.async_call(DOMAIN, "play_show", {"show": "Not a show"}, blocking=True)


def test_show_names_match_the_firmware() -> None:
    from custom_components.magicband.readers import SHOW_NAMES

    header = (Path(__file__).parents[1] / "components" / "magicband" / "shows.h").read_text()
    names = re.search(r"NAMES\[COUNT\] = \{(.*?)\};", header, re.S).group(1)
    assert tuple(re.findall(r'"([^"]+)"', names)) == SHOW_NAMES



async def test_play_show_is_limited_per_reader(hass: HomeAssistant, setup_integration, reader_device) -> None:
    shows: list[ServiceCall] = []
    hass.services.async_register("esphome", "lounge_reader_play_show", lambda c: shows.append(c))
    for _ in range(14):
        await hass.services.async_call(DOMAIN, "play_show", {}, blocking=True)
    assert len(shows) == 12  # MAX_SHOWS_PER_MINUTE: the rest are skipped



# ---------------------------------------------------------------------------- pairing (0.10.20+ readers)


def _paired_reader(hass: HomeAssistant, node: str = "lounge-reader") -> dict[str, list[ServiceCall]]:
    calls: dict[str, list[ServiceCall]] = {"pair": [], "bands": [], "colours": [], "accept": [], "deny": []}
    prefix = node.replace("-", "_")
    for name, suffix in (("pair", "pair"), ("bands", "set_known_bands"), ("colours", "set_band_colours"),
                         ("accept", "accept"), ("deny", "deny")):
        hass.services.async_register("esphome", f"{prefix}_{suffix}", lambda c, n=name: calls[n].append(c))
    return calls


async def test_readers_are_paired_and_get_the_key(hass: HomeAssistant, setup_integration, reader_device) -> None:
    calls = _paired_reader(hass)
    await _person_with_band(hass)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    key = hass.config_entries.async_entries(DOMAIN)[0].data["reader_key"]
    assert len(key) == 64
    assert calls["pair"][-1].data == {"key": key}
    assert calls["bands"][-1].data["key"] == key and calls["colours"][-1].data["key"] == key


async def test_older_readers_get_no_key(hass: HomeAssistant, setup_integration, reader_device) -> None:
    calls = _reader_calls(hass)  # no pair action: firmware before 0.10.20
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert "key" not in calls["bands"][-1].data


async def test_answer_uses_the_key(hass: HomeAssistant, setup_integration, reader_device) -> None:
    calls = _paired_reader(hass)
    await hass.services.async_call(DOMAIN, "answer", {"device_id": reader_device.id, "allow": True}, blocking=True)
    await hass.services.async_call(DOMAIN, "answer", {"device_id": reader_device.id, "allow": False}, blocking=True)
    key = hass.config_entries.async_entries(DOMAIN)[0].data["reader_key"]
    assert calls["accept"][-1].data == {"key": key} and calls["deny"][-1].data == {"key": key}
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "answer", {"device_id": "nope", "allow": True}, blocking=True)


async def test_unpair_reader_uses_the_key(hass: HomeAssistant, setup_integration, reader_device) -> None:
    unpairs: list[ServiceCall] = []
    _paired_reader(hass)
    hass.services.async_register("esphome", "lounge_reader_unpair", lambda c: unpairs.append(c))
    await hass.services.async_call(DOMAIN, "unpair_reader", {"device_id": reader_device.id}, blocking=True)
    assert unpairs[-1].data == {"key": hass.config_entries.async_entries(DOMAIN)[0].data["reader_key"]}



async def test_a_released_reader_is_left_alone_until_taken_back(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    calls = _paired_reader(hass)
    hass.services.async_register("esphome", "lounge_reader_unpair", lambda c: None)
    shows: list[ServiceCall] = []
    hass.services.async_register("esphome", "lounge_reader_play_show", lambda c: shows.append(c))
    await hass.services.async_call(DOMAIN, "unpair_reader", {"device_id": reader_device.id}, blocking=True)
    pairs, lists = len(calls["pair"]), len(calls["bands"])
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    await hass.services.async_call(DOMAIN, "play_show", {}, blocking=True)
    assert len(calls["pair"]) == pairs and len(calls["bands"]) == lists and not shows  # no re-pairing
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "answer", {"device_id": reader_device.id, "allow": True}, blocking=True)
    await hass.services.async_call(DOMAIN, "pair_reader", {"device_id": reader_device.id}, blocking=True, return_response=True)
    assert len(calls["pair"]) == pairs + 1 and len(calls["bands"]) == lists + 1



async def test_first_pairing_asks_for_a_tap(hass: HomeAssistant, setup_integration, reader_device) -> None:
    from homeassistant.exceptions import HomeAssistantError

    calls = _paired_reader(hass)

    def pending(call):
        raise HomeAssistantError("PAIRING_PENDING: tap any band on the reader within 2 minutes to finish pairing")

    hass.services.async_register("esphome", "lounge_reader_pair", pending)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"reader_pairing_{reader_device.id}") is not None
    assert calls["bands"]  # the list still goes to the (unpaired) reader
    hass.services.async_register("esphome", "lounge_reader_pair", lambda c: None)  # tapped: now paired
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"reader_pairing_{reader_device.id}") is None



@pytest.mark.parametrize("reply", ["PAIRING_BUSY", "PAIRING_COOLDOWN"])
async def test_pairing_busy_or_cooling_down_tries_again(
    hass: HomeAssistant, setup_integration, reader_device, reply: str, freezer
) -> None:
    """PAIRING_BUSY (another key's request is waiting: don't tap) and PAIRING_COOLDOWN (ours ran out) aren't
    failures: the list still goes and the reader is asked again. Neither shows "Tap a band" (SEC-005, changed in
    round 2: during our cooldown any other key may be the one waiting, so a tap then could pair it with them)."""
    import time as _time

    from homeassistant.exceptions import HomeAssistantError

    from custom_components.magicband import readers as readers_mod

    calls = _paired_reader(hass)
    asked: list[ServiceCall] = []

    def refuse(call):
        asked.append(call)
        raise HomeAssistantError(f"{reply}: the reader says not now")

    hass.services.async_register("esphome", "lounge_reader_pair", refuse)
    result = await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    issues = ir.async_get(hass)
    busy = issues.async_get_issue(DOMAIN, f"reader_pairing_busy_{reader_device.id}")
    tap = issues.async_get_issue(DOMAIN, f"reader_pairing_{reader_device.id}")
    assert result["failed"] == [] and calls["bands"]  # not a failed sync; the (unpaired) reader takes the list
    assert issues.async_get_issue(DOMAIN, f"reader_sync_failed_{reader_device.id}") is None
    if reply == "PAIRING_BUSY":
        assert busy is not None and tap is None  # don't tap: it would pair it with them
        assert busy.translation_placeholders["reader"] == reader_device.name
    else:
        assert tap is None and busy is None
    n = len(asked)
    data = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    wait = data.readers._retry_at - _time.monotonic()
    assert readers_mod.PAIRING_RETRY - 5 < wait <= readers_mod.PAIRING_RETRY  # asked again in 2 minutes
    assert not data.readers.retry_due()  # not yet
    data.readers._retry_at -= readers_mod.PAIRING_RETRY  # ...2 minutes on
    hass.services.async_register("esphome", "lounge_reader_pair", lambda c: asked.append(c))  # now it pairs
    for _ in range(2):  # the minute check, then past the sync debounce
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert len(asked) > n  # asked again by itself
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_busy_{reader_device.id}") is None
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_{reader_device.id}") is None
    assert not data.readers.retry_due()


def _pair_replies(hass: HomeAssistant, replies: list[str]) -> list[ServiceCall]:
    """The reader's pair action answers with the first reply in `replies` ("" = paired) until it's changed."""
    from homeassistant.exceptions import HomeAssistantError

    asked: list[ServiceCall] = []

    def pair(call):
        asked.append(call)
        if replies[0]:
            raise HomeAssistantError(replies[0])

    hass.services.async_register("esphome", "lounge_reader_pair", pair)
    return asked


PENDING = "PAIRING_PENDING: tap any band on the reader within 2 minutes to finish pairing"
ELSEWHERE = ("This reader is paired with another key. Release it from the Home Assistant that paired it "
             "(magicband.unpair_reader), or erase it over USB with the web installer (Erase device) and add it again")


async def _tick(hass: HomeAssistant, freezer, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_tap_a_band_shows_only_while_our_request_waits(
    hass: HomeAssistant, setup_integration, reader_device, freezer
) -> None:
    """BUG-017/SEC-005: "Tap a band" goes when our request's 2 minutes are up (another key may pend after that),
    asking again inside the window doesn't extend it, and the reader is asked again after its cooldown."""
    _paired_reader(hass)
    replies = [PENDING]
    asked = _pair_replies(hass, replies)
    issues = ir.async_get(hass)
    tap = f"reader_pairing_{reader_device.id}"
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, tap) is not None
    await _tick(hass, freezer, 90)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)  # still PENDING
    assert issues.async_get_issue(DOMAIN, tap) is not None
    await _tick(hass, freezer, 31)  # 121 s after the reader took our request: its window is over
    assert issues.async_get_issue(DOMAIN, tap) is None
    replies[0] = "PAIRING_COOLDOWN: this key's pairing request expired without a tap"
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, tap) is None  # cooling down: someone else's request may be waiting
    data = _data(hass)
    assert data.readers._retry_at is not None  # asked again once the cooldown is over
    n = len(asked)
    replies[0] = PENDING
    data.readers._retry_at -= 1000
    await _tick(hass, freezer, 60)
    await _tick(hass, freezer, 60)
    assert len(asked) > n and issues.async_get_issue(DOMAIN, tap) is not None  # a new request: tap now


async def test_tap_a_band_keeps_its_end_over_a_reload(hass: HomeAssistant, setup_integration, reader_device, freezer) -> None:
    """SEC-021/BUG-024: the reader answers PAIRING_PENDING to our key while our older request waits, without saying
    how long is left. After a reload (or restart) 90 s into the wait, "Tap a band" ends when that request does
    (120 s), not a fresh 2 minutes later; a request made after it has run out gets its full 2 minutes."""
    _paired_reader(hass)
    replies = [PENDING]
    _pair_replies(hass, replies)
    issues = ir.async_get(hass)
    tap = f"reader_pairing_{reader_device.id}"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, tap) is not None
    await _tick(hass, freezer, 90)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await _tick(hass, freezer, 3)  # the sync after the reload: still PENDING (the same request)
    assert issues.async_get_issue(DOMAIN, tap) is not None
    await _tick(hass, freezer, 28)  # 121 s after the reader took our request: its wait is over
    assert issues.async_get_issue(DOMAIN, tap) is None
    replies[0] = "PAIRING_COOLDOWN: this key's pairing request expired without a tap"
    await _tick(hass, freezer, 200)
    # The window's end is forgotten once it's over: a later, fresh request gets the full 2 minutes.
    replies[0] = PENDING
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, tap) is not None
    await _tick(hass, freezer, 110)
    assert issues.async_get_issue(DOMAIN, tap) is not None
    await _tick(hass, freezer, 11)
    assert issues.async_get_issue(DOMAIN, tap) is None


async def test_tap_a_band_goes_when_magicbhands_is_unloaded(
    hass: HomeAssistant, setup_integration, reader_device, freezer
) -> None:
    """BUG-024: unloading (reload, disable, Home Assistant stopping) cancels the window's timer, so the repair goes
    with it instead of staying until MagicbHAnds is loaded again."""
    _paired_reader(hass)
    _pair_replies(hass, [PENDING])
    issues = ir.async_get(hass)
    tap = f"reader_pairing_{reader_device.id}"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, tap) is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, tap) is None
    await _tick(hass, freezer, 600)
    assert issues.async_get_issue(DOMAIN, tap) is None


async def test_tap_a_band_goes_as_soon_as_the_reader_says_paired(
    hass: HomeAssistant, setup_integration, reader_device, freezer
) -> None:
    """BUG-017: the confirming tap turns the reader's Paired sensor on: the repair goes at once (not at the next
    periodic sync), and the sync that follows clears "another request is waiting" too."""
    from homeassistant.helpers import entity_registry as er

    paired = er.async_get(hass).async_get_or_create(
        "binary_sensor", "esphome", "paired1", device_id=reader_device.id, original_name="Paired with MagicbHAnds",
        suggested_object_id="lounge_paired").entity_id
    hass.states.async_set(paired, "off")
    calls = _paired_reader(hass)
    replies = [PENDING]
    _pair_replies(hass, replies)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_{reader_device.id}") is not None
    replies[0] = ""
    n = len(calls["bands"])
    hass.states.async_set(paired, "on")
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_{reader_device.id}") is None  # straight away
    await _tick(hass, freezer, 5)  # the debounced sync
    assert len(calls["bands"]) > n


async def test_paired_with_another_key_raises_a_repair_and_clears_the_pairing_ones(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    """BUG-017/SEC-005: if the confirmed pairing was someone else's, the waiting/busy repairs go (they're wrong
    now) and a repair says the reader is paired with another key and how to recover it."""
    _paired_reader(hass)
    replies = ["PAIRING_BUSY: another pairing request is already waiting on this reader (not from this key)"]
    _pair_replies(hass, replies)
    issues = ir.async_get(hass)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_busy_{reader_device.id}") is not None
    replies[0] = ELSEWHERE  # someone tapped while their request waited
    result = await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert result["failed"] == [reader_device.name]
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_busy_{reader_device.id}") is None
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_{reader_device.id}") is None
    elsewhere = issues.async_get_issue(DOMAIN, f"reader_paired_elsewhere_{reader_device.id}")
    assert elsewhere is not None and elsewhere.severity == ir.IssueSeverity.ERROR
    strings = Path(__file__).resolve().parents[1] / "custom_components/magicband/strings.json"
    import json

    text = json.loads(strings.read_text())["issues"]["reader_paired_elsewhere"]["description"]
    assert "unpair_reader" in text and "Erase device" in text
    replies[0] = ""  # released and paired with MagicbHAnds again
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, f"reader_paired_elsewhere_{reader_device.id}") is None


async def test_other_pairing_errors_clear_the_pairing_repairs(hass: HomeAssistant, setup_integration, reader_device) -> None:
    _paired_reader(hass)
    replies = ["PAIRING_BUSY: another pairing request is already waiting on this reader (not from this key)"]
    _pair_replies(hass, replies)
    issues = ir.async_get(hass)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    replies[0] = "The key must be 32 to 64 hex characters"
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert issues.async_get_issue(DOMAIN, f"reader_pairing_busy_{reader_device.id}") is None
    assert issues.async_get_issue(DOMAIN, f"reader_sync_failed_{reader_device.id}") is not None


@pytest.mark.parametrize("how", ["released", "removed"])
async def test_a_readers_repairs_go_when_it_is_released_or_removed(
    hass: HomeAssistant, setup_integration, reader_device, how: str, freezer
) -> None:
    """BUG-016 (and BUG-017): colours_too_long, sounds_too_long and the pairing repairs don't outlive the reader."""
    from homeassistant.helpers import device_registry as dr

    _paired_reader(hass)
    replies = ["PAIRING_BUSY: another pairing request is already waiting on this reader (not from this key)"]
    _pair_replies(hass, replies)
    hass.services.async_register("esphome", "lounge_reader_unpair", lambda c: None)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    readers = _data(hass).readers
    for key in ("colours_too_long", "sounds_too_long"):
        readers._issue(f"{key}_{reader_device.id}", True, key, {"reader": "Lounge reader", "kept": "1", "total": "2"})
    issues = ir.async_get(hass)
    ids = [f"{k}_{reader_device.id}" for k in ("colours_too_long", "sounds_too_long", "reader_pairing_busy")]
    assert all(issues.async_get_issue(DOMAIN, i) for i in ids)
    if how == "released":
        await hass.services.async_call(DOMAIN, "unpair_reader", {"device_id": reader_device.id}, blocking=True)
    else:
        dr.async_get(hass).async_remove_device(reader_device.id)
        await _tick(hass, freezer, 60)  # the minute check
    assert not any(issues.async_get_issue(DOMAIN, i) for i in ids)


# ---------------------------------------------------------------------------- tap snapshots (optional)


async def test_taps_on_a_reader_with_a_camera_get_a_snapshot(
    hass: HomeAssistant, setup_integration, reader_device, monkeypatch, tmp_path
) -> None:
    from custom_components.magicband import snapshots

    captured: list[str] = []

    async def fake_capture(hass_, camera):
        captured.append(camera)
        return "20261120/" + "a" * 32

    monkeypatch.setattr(snapshots, "async_capture", fake_capture)
    await _person_with_band(hass)
    _tap(hass, TAG, reader_device.id)  # no camera yet: nothing captured
    await hass.async_block_till_done()
    assert captured == []

    await hass.services.async_call(
        DOMAIN, "set_reader_camera", {"device_id": reader_device.id, "camera": "camera.front_door"}, blocking=True
    )
    _tap(hass, TAG, reader_device.id)
    await hass.async_block_till_done()
    assert captured == ["camera.front_door"]
    taps = (await hass.services.async_call(DOMAIN, "history", {}, blocking=True, return_response=True))["taps"]
    assert taps[0]["snapshot"] == "20261120/" + "a" * 32
    assert taps[0]["snapshot_url"].startswith("/api/magicband/snapshot/20261120/") and "authSig=" in taps[0]["snapshot_url"]
    assert "snapshot" not in taps[1]

    await hass.services.async_call(DOMAIN, "set_reader_camera", {"device_id": reader_device.id}, blocking=True)
    _tap(hass, TAG, reader_device.id)
    await hass.async_block_till_done()
    assert len(captured) == 1  # unlinked: no more pictures


def test_snapshot_ids_cant_escape_the_folder(hass: HomeAssistant) -> None:
    from custom_components.magicband import snapshots

    for bad in ("../../secrets", "20261120/../x", "2026112/" + "a" * 32, "20261120/" + "g" * 32, ""):
        assert snapshots._path(hass, bad) is None
    assert snapshots._path(hass, "20261120/" + "0" * 32) is not None


def test_old_snapshots_are_pruned(hass: HomeAssistant, tmp_path) -> None:
    from custom_components.magicband import snapshots

    hass.config.config_dir = str(tmp_path)
    old = tmp_path / snapshots.FOLDER / "20000101"
    old.mkdir(parents=True)
    (old / ("b" * 32 + ".jpg")).write_bytes(b"x")
    today = tmp_path / snapshots.FOLDER / dt_util.now().strftime("%Y%m%d")
    today.mkdir()
    (today / ("c" * 32 + ".jpg")).write_bytes(b"x")
    assert snapshots.prune(hass, 30) == 1
    assert not old.exists() and today.exists()



async def test_snapshot_days_can_be_set_from_the_page(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "set_snapshot_days", {"days": 7}, blocking=True)
    assert hass.config_entries.async_entries(DOMAIN)[0].options["snapshot_days"] == 7
    resp = await hass.services.async_call(DOMAIN, "history", {}, blocking=True, return_response=True)
    assert resp["snapshot_days"] == 7
