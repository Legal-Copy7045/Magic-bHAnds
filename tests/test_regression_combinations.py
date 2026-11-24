"""Regression suite: feature combinations and gaps not covered elsewhere (regression/catalogue/integration.yaml).

Made-up people only (Morgan, Casey, Alex, Jordan, Sam). A test that shows a real product bug is marked
``xfail(strict=True)`` with the reason: CI stays green, the regression runner (regression/integration/run.py)
reports it as a failure, and once the bug is fixed the strict xfail turns red so the marker is removed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import voluptuous as vol

from custom_components.magicband import sounds
from custom_components.magicband.const import DOMAIN
from tests.conftest import make_esphome_device

TAG = "04AABBCCDDEEFF"
OTHER = "04AABBCCDD0001"
UNKNOWN = "04AABBCCDD0002"
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64
BAND_X = "C0 0F 01 01 48 9E 24 36 F8 EF A8 42 C8 00 35 33 00"


def _data(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data


async def _call(hass: HomeAssistant, service: str, data: dict | None = None, response: bool = False):
    return await hass.services.async_call(DOMAIN, service, data or {}, blocking=True, return_response=response)


async def _person_with_band(hass: HomeAssistant, name: str, uid: str = TAG, **extra) -> str:
    await _call(hass, "add_person", {"name": name, **extra})
    await _call(hass, "assign_band", {"band": uid, "person": name})
    return _data(hass).registry.find_person(name).id


async def _tap(hass: HomeAssistant, uid: str, device_id: str) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": uid, "device_id": device_id})
    await hass.async_block_till_done(wait_background_tasks=True)


def _taps(hass: HomeAssistant) -> list[dict]:
    taps: list[dict] = []
    hass.bus.async_listen("magicband_tap", lambda e: taps.append(e.data))
    return taps


def _reader_services(hass: HomeAssistant, node: str = "lounge-reader") -> dict[str, list[ServiceCall]]:
    calls: dict[str, list[ServiceCall]] = {"bands": [], "colours": [], "sounds": []}
    prefix = node.replace("-", "_")
    hass.services.async_register("esphome", f"{prefix}_set_known_bands", lambda c: calls["bands"].append(c))
    hass.services.async_register("esphome", f"{prefix}_set_band_colours", lambda c: calls["colours"].append(c))
    hass.services.async_register("esphome", f"{prefix}_set_band_sounds", lambda c: calls["sounds"].append(c))
    return calls


def _reader_entity(hass: HomeAssistant, device, domain: str, name: str | None, uid: str) -> str:
    return er.async_get(hass).async_get_or_create(
        domain, "esphome", uid, device_id=device.id, original_name=name,
        suggested_object_id=f"rt_{(name or domain).lower().replace(' ', '_')}_{uid}",
    ).entity_id


def _give_sound(hass: HomeAssistant, person_id: str) -> Path:
    folder = Path(hass.config.path(sounds.FOLDER))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{person_id}.mp3"
    path.write_bytes(MP3)
    _data(hass).registry.set_welcome_sound(person_id, "mp3", "hello.mp3")
    return path


def _notification(hass: HomeAssistant, notification_id: str):
    from homeassistant.components import persistent_notification

    return persistent_notification._async_get_or_create_notifications(hass).get(notification_id)


def _local(*args) -> datetime:
    return datetime(*args, tzinfo=dt_util.get_default_time_zone())


# ---------------------------------------------------------------------------- guest pass + band hours + lockdown


async def test_guest_pass_band_hours_and_lockdown_combine(hass: HomeAssistant, setup_integration) -> None:
    """A guest's pass, the band's own hours and lockdown all have to allow a tap."""
    await _person_with_band(hass, "Casey", guest=True)
    registry = _data(hass).registry
    await _call(hass, "set_guest_pass", {"person": "Casey", "from": "09:00", "until": "17:00",
                                         "days": ["mon", "tue", "wed", "thu", "fri"]})
    await _call(hass, "set_band_access", {"band": TAG, "from": "12:00", "until": "20:00"})
    tue = lambda h: _local(2026, 11, 24, h, 0)  # noqa: E731 - 24 Nov 2026 is a Tuesday
    assert not registry.band_allowed(TAG, tue(10))  # pass yes, band hours no
    assert registry.band_allowed(TAG, tue(13))  # both
    assert not registry.band_allowed(TAG, tue(18))  # band hours yes, pass no
    assert not registry.band_allowed(TAG, _local(2026, 11, 28, 13, 0))  # Saturday: not a pass day
    casey = registry.find_person("Casey")
    assert registry.person_allowed_now(casey, tue(10))  # the person-level answer ignores band hours

    await _call(hass, "set_settings", {"lockdown": True})
    assert not registry.band_allowed(TAG, tue(13))
    await _call(hass, "update_person", {"person": "Casey", "lockdown_exempt": True})
    assert registry.band_allowed(TAG, tue(13))
    assert not registry.band_allowed(TAG, tue(18))  # exempt from lockdown, not from the pass


async def test_denied_guest_tap_in_lockdown_uses_nothing(hass: HomeAssistant, setup_integration, reader_device) -> None:
    await _person_with_band(hass, "Casey", guest=True)
    await _call(hass, "set_guest_pass", {"person": "Casey", "uses": 2})
    await _call(hass, "set_settings", {"lockdown": True})
    taps = _taps(hass)
    await _tap(hass, TAG, reader_device.id)
    registry = _data(hass).registry
    assert taps[-1]["allowed"] is False and taps[-1]["known"] is True
    assert registry.find_person("Casey").uses_left == 2  # a denied tap isn't a use
    await _call(hass, "update_person", {"person": "Casey", "lockdown_exempt": True})
    await _tap(hass, TAG, reader_device.id)
    assert taps[-1]["allowed"] is True
    assert registry.find_person("Casey").uses_left == 1
    assert _data(hass).passport.get(registry.find_person("Casey").id)["taps"] == 0  # guests: no passport


async def test_used_up_pass_leaves_the_readers_list_and_guest_off_restores_it(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    calls = _reader_services(hass)
    await _person_with_band(hass, "Casey", guest=True)
    await _call(hass, "set_guest_pass", {"person": "Casey", "uses": 0, "from": "08:00", "until": "09:00"})
    await _call(hass, "sync", response=True)
    assert TAG not in calls["bands"][-1].data["bands"]
    await _call(hass, "update_person", {"person": "Casey", "guest": False})
    casey = _data(hass).registry.find_person("Casey")
    assert not casey.guest and not casey.has_pass and casey.uses_left is None and casey.access_from is None
    await _call(hass, "sync", response=True)
    assert calls["bands"][-1].data["bands"] == TAG


async def test_overnight_band_window_belongs_to_the_day_it_started(hass: HomeAssistant, setup_integration) -> None:
    await _person_with_band(hass, "Jordan")
    await _call(hass, "set_band_access", {"band": TAG, "from": "22:00", "until": "06:00", "days": ["fri"]})
    registry = _data(hass).registry
    assert registry.band_allowed(TAG, _local(2026, 11, 27, 23, 0))  # Friday night
    assert registry.band_allowed(TAG, _local(2026, 11, 28, 5, 0))  # early Saturday: Friday's window
    assert not registry.band_allowed(TAG, _local(2026, 11, 28, 23, 0))  # Saturday night
    assert not registry.band_allowed(TAG, _local(2026, 11, 27, 12, 0))


# ---------------------------------------------------------------------------- lockdown


async def test_lockdown_at_night_follows_the_clock_and_resyncs(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    calls = _reader_services(hass)
    freezer.move_to(_local(2026, 11, 24, 22, 58))
    await _person_with_band(hass, "Morgan")
    await _call(hass, "set_settings", {"lockdown_night": True, "lockdown_from": "23:00", "lockdown_until": "06:00"})
    await _call(hass, "sync", response=True)
    assert calls["bands"][-1].data["bands"] == TAG
    assert hass.states.get("binary_sensor.magicbhands_lockdown").state == "off"
    for _ in range(4):  # into the night hours; the minute timer notices, then the sync debouncer runs
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls["bands"][-1].data["bands"] == ""
    state = hass.states.get("binary_sensor.magicbhands_lockdown")
    assert state.state == "on" and state.attributes["reasons"] == ["Night hours (23:00–06:00)"]


async def test_lockdown_alarm_triggered_and_bad_settings_refused(hass: HomeAssistant, setup_integration) -> None:
    registry = _data(hass).registry
    await _call(hass, "set_settings", {"lockdown_alarm": "alarm_control_panel.lakeview"})
    hass.states.async_set("alarm_control_panel.lakeview", "triggered", {"friendly_name": "House alarm"})
    assert registry.lockdown_reasons() == ["House alarm is triggered"]
    hass.states.async_set("alarm_control_panel.lakeview", "armed_night", {"friendly_name": "House alarm"})
    assert registry.lockdown_reasons() == ["House alarm is armed night"]
    hass.states.async_set("alarm_control_panel.lakeview", "disarmed", {"friendly_name": "House alarm"})
    assert registry.lockdown_reasons() == []
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(hass, "set_settings", {"lockdown_alarm": "light.hall"})
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(hass, "set_settings", {"lockdown_from": "25:00"})
    with pytest.raises(ValueError):
        registry.set_settings(nonsense=True)
    await _call(hass, "set_settings", {"lockdown_alarm": ""})
    assert registry.settings["lockdown_alarm"] is None


async def test_colours_and_sounds_follow_lockdown(hass: HomeAssistant, setup_integration, reader_device) -> None:
    """A band left off the list in lockdown also leaves the welcome colour and own-sound lists."""
    calls = _reader_services(hass)
    morgan = await _person_with_band(hass, "Morgan", welcome_colour="Blue")
    _give_sound(hass, morgan)
    await _call(hass, "sync", response=True)
    assert calls["colours"][-1].data["colours"] == f"{TAG}=Blue" and calls["sounds"][-1].data["bands"] == TAG
    await _call(hass, "set_settings", {"lockdown": True})
    await _call(hass, "sync", response=True)
    assert calls["bands"][-1].data["bands"] == ""
    assert calls["colours"][-1].data["colours"] == "" and calls["sounds"][-1].data["bands"] == ""


async def test_disallowed_person_is_known_but_denied(hass: HomeAssistant, setup_integration, reader_device) -> None:
    await _person_with_band(hass, "Sam")
    await _call(hass, "update_person", {"person": "Sam", "allowed": False})
    taps = _taps(hass)
    await _tap(hass, TAG, reader_device.id)
    assert taps[-1]["known"] is True and taps[-1]["allowed"] is False and taps[-1]["person"] == "Sam"
    assert _data(hass).passport.get(_data(hass).registry.find_person("Sam").id)["taps"] == 0


# ---------------------------------------------------------------------------- refused-tap lockout


async def test_lockout_while_in_lockdown(hass: HomeAssistant, setup_integration, reader_device) -> None:
    """A reader's lockout and the house's lockdown are independent: each reports and clears on its own."""
    lockout = _reader_entity(hass, reader_device, "binary_sensor", "Tap lockout", "lo1")
    await _call(hass, "set_settings", {"lockdown": True})
    events: list[dict] = []
    hass.bus.async_listen("magicband_lockout", lambda e: events.append(e.data))
    hass.states.async_set(lockout, "off")
    await hass.async_block_till_done()
    hass.states.async_set(lockout, "on")
    await hass.async_block_till_done()
    note = f"{DOMAIN}_lockout_{reader_device.id}"
    assert events == [{"reader": "Lounge reader", "reader_device_id": reader_device.id, "locked": True}]
    assert _notification(hass, note) is not None
    assert hass.states.get("binary_sensor.magicbhands_lockdown").state == "on"
    hass.states.async_set(lockout, "off")
    await hass.async_block_till_done()
    assert events[-1]["locked"] is False and _notification(hass, note) is None
    assert hass.states.get("binary_sensor.magicbhands_lockdown").state == "on"  # lockdown is still on


async def test_lockout_ignores_unavailable_and_non_readers(hass: HomeAssistant, setup_integration, reader_device) -> None:
    lockout = _reader_entity(hass, reader_device, "binary_sensor", "Tap lockout", "lo2")
    other = make_esphome_device(hass, "garage-gadget", "some-other-project", "Garage gadget")
    fake = _reader_entity(hass, other, "binary_sensor", "Tap lockout", "lo3")
    events: list[dict] = []
    hass.bus.async_listen("magicband_lockout", lambda e: events.append(e.data))
    for state in ("unavailable", "on", "unavailable", "off"):
        hass.states.async_set(lockout, state)
        await hass.async_block_till_done()
    hass.states.async_set(fake, "off")
    hass.states.async_set(fake, "on")
    await hass.async_block_till_done()
    assert events == []  # going to/from unavailable isn't a lockout, and only readers count


# ---------------------------------------------------------------------------- welcome sounds


async def _sound_setup(hass: HomeAssistant, reader_device, monkeypatch) -> tuple[str, list[ServiceCall], str]:
    _reader_services(hass)
    person_id = await _person_with_band(hass, "Morgan")
    _give_sound(hass, person_id)
    _reader_entity(hass, reader_device, "media_player", "Speaker", "mp9")
    scan = _reader_entity(hass, reader_device, "event", "Band scan", "ev9")
    played: list[ServiceCall] = []
    hass.services.async_register("media_player", "play_media", lambda c: played.append(c))
    monkeypatch.setattr(sounds, "async_sign_path", lambda hass, path, *a, **k: path + "?authSig=abc")
    monkeypatch.setattr(sounds, "_base_url", lambda hass: "http://ha.local:8123")
    await _call(hass, "sync", response=True)
    return person_id, played, scan


async def _welcome(hass: HomeAssistant, reader_device, scan: str, stamp: str) -> None:
    await _tap(hass, TAG, reader_device.id)
    hass.states.async_set(scan, stamp, {"event_type": "welcomed"})
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_welcome_sound_respects_sound_at_night(
    hass: HomeAssistant, setup_integration, reader_device, monkeypatch
) -> None:
    _, played, scan = await _sound_setup(hass, reader_device, monkeypatch)
    night = _reader_entity(hass, reader_device, "binary_sensor", "Night now", "nn9")
    at_night = _reader_entity(hass, reader_device, "select", "Sound at night", "sn9")
    hass.states.async_set(night, "on")
    hass.states.async_set(at_night, "Off")
    await _welcome(hass, reader_device, scan, "2026-11-24T23:00:00")
    assert played == []  # night, and Sound at night is Off
    hass.states.async_set(at_night, "Quieter")
    await _welcome(hass, reader_device, scan, "2026-11-24T23:01:00")
    assert len(played) == 1  # Quieter still plays (the reader sets the volume)
    hass.states.async_set(night, "off")
    hass.states.async_set(at_night, "Off")
    await _welcome(hass, reader_device, scan, "2026-11-24T23:02:00")
    assert len(played) == 2  # day: Sound at night doesn't apply


async def test_try_out_plays_even_with_the_reader_muted(
    hass: HomeAssistant, setup_integration, reader_device, monkeypatch
) -> None:
    _, played, _ = await _sound_setup(hass, reader_device, monkeypatch)
    sound_switch = _reader_entity(hass, reader_device, "switch", "Sound", "sw9")
    hass.states.async_set(sound_switch, "off")
    result = await _call(hass, "play_welcome_sound", {"person": "Morgan"}, response=True)
    assert result == {"played": ["Lounge reader"], "skipped": []} and len(played) == 1
    result = await _call(hass, "play_welcome_sound", {"person": "Morgan", "device_id": "not-a-reader"}, response=True)
    assert result == {"played": [], "skipped": []}
    await _call(hass, "add_person", {"name": "Alex"})
    with pytest.raises(ServiceValidationError):
        await _call(hass, "play_welcome_sound", {"person": "Alex"}, response=True)


async def test_welcome_sound_only_after_a_recent_welcome(
    hass: HomeAssistant, setup_integration, reader_device, monkeypatch
) -> None:
    _, played, scan = await _sound_setup(hass, reader_device, monkeypatch)
    await _tap(hass, TAG, reader_device.id)
    device_id = reader_device.id
    pid, when = _data(hass).pending_sounds[device_id]
    _data(hass).pending_sounds[device_id] = (pid, when - 20)  # the reader took longer than 15 s to say so
    hass.states.async_set(scan, "2026-11-24T10:00:00", {"event_type": "welcomed"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert played == []
    await _tap(hass, TAG, reader_device.id)
    hass.states.async_set(scan, "2026-11-24T10:01:00", {"event_type": "denied"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert played == []  # the reader denied it after all
    await _call(hass, "set_settings", {"lockdown": True})
    await _tap(hass, TAG, reader_device.id)
    assert device_id not in _data(hass).pending_sounds  # a denied tap never queues a sound


async def test_sound_not_queued_for_a_reader_without_the_sound_list(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    """Older readers (no set_band_sounds) play their own tap-in sound; Home Assistant mustn't add a second one."""
    hass.services.async_register("esphome", "lounge_reader_set_known_bands", lambda c: None)
    person_id = await _person_with_band(hass, "Morgan")
    _give_sound(hass, person_id)
    await _call(hass, "sync", response=True)
    assert _data(hass).readers.status_of(reader_device.id).sounds is False
    await _tap(hass, TAG, reader_device.id)
    assert reader_device.id not in _data(hass).pending_sounds


# ---------------------------------------------------------------------------- removing people


async def _morgan_with_everything(hass: HomeAssistant, reader_device) -> tuple[str, Path]:
    morgan = await _person_with_band(hass, "Morgan")
    path = _give_sound(hass, morgan)
    await _tap(hass, TAG, reader_device.id)  # a welcomed tap: a passport
    await _call(hass, "set_guest_pass", {"person": "Morgan", "uses": 5})
    assert _data(hass).passport.get(morgan)["taps"] == 1 and path.is_file()
    return morgan, path


async def test_removing_a_person_with_a_sound_and_a_pass(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    calls = _reader_services(hass)
    morgan, path = await _morgan_with_everything(hass, reader_device)
    assert hass.states.get("sensor.magicband_morgan_last_tap") is not None
    await _call(hass, "remove_person", {"person": "Morgan"})
    await hass.async_block_till_done()
    registry = _data(hass).registry
    assert registry.find_person("Morgan") is None
    assert registry.get_band(TAG).person_id is None and not registry.band_allowed(TAG)  # band kept, unassigned
    assert not path.exists()  # the sound file goes
    assert _data(hass).passport.get(morgan)["taps"] == 0  # and the passport
    assert registry.sound_uids() == []
    assert er.async_get(hass).async_get("sensor.magicband_morgan_last_tap") is None
    await _call(hass, "sync", response=True)
    assert calls["bands"][-1].data["bands"] == "" and calls["sounds"][-1].data["bands"] == ""


@pytest.mark.xfail(
    strict=True,
    reason="BUG: Configure -> Remove a person (config_flow.async_step_remove_person) only calls registry.remove_person: "
    "the person's welcome sound file stays in magicbhands_sounds and their passport stays in .storage "
    "(magicband.remove_person does both)",
)
async def test_removing_a_person_in_configure_also_removes_sound_and_passport(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    morgan, path = await _morgan_with_everything(hass, reader_device)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "remove_person"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"person": morgan})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert _data(hass).registry.find_person("Morgan") is None
    assert not path.exists(), "the removed person's welcome sound file is left behind"
    assert _data(hass).passport.get(morgan)["taps"] == 0, "the removed person's passport is left behind"


# ---------------------------------------------------------------------------- unknown bands, assigning, linking


async def test_unknown_band_then_assign_then_link(hass: HomeAssistant, setup_integration, reader_device) -> None:
    taps = _taps(hass)
    await _tap(hass, UNKNOWN, reader_device.id)
    note = f"{DOMAIN}_unknown_{UNKNOWN}"
    assert taps[-1]["known"] is False and taps[-1]["allowed"] is False and taps[-1]["person"] is None
    assert _notification(hass, note) is not None
    assert hass.states.get("sensor.magicband_unknown_bands").state == "1"
    await _call(hass, "add_person", {"name": "Jordan"})
    await _call(hass, "assign_band", {"band": "last", "person": "Jordan", "label": "green"})
    await hass.async_block_till_done()
    assert _notification(hass, note) is None
    assert hass.states.get("sensor.magicband_unknown_bands").state == "0"
    await _tap(hass, UNKNOWN, reader_device.id)
    assert taps[-1]["allowed"] is True and taps[-1]["person"] == "Jordan" and taps[-1]["label"] == "green"
    band = _data(hass).beacons.async_beacon("11:22:33:44:55:66", -60, "hci0", bytes.fromhex(BAND_X))
    await hass.async_block_till_done()
    await _call(hass, "link_bluetooth", {"bluetooth_band": band.id, "band": "last"})
    assert _data(hass).beacons.for_nfc(UNKNOWN) is band
    response = await _call(hass, "list", response=True)
    listed = next(b for b in response["bands"] if b["band"] == "04-AA-BB-CC-DD-00-02")
    assert listed["bluetooth"]["id"] == band.id and listed["band_type"] == "plus"


async def test_unknown_band_given_an_owner_by_linking(hass: HomeAssistant, setup_integration, reader_device) -> None:
    """Linking a person's Bluetooth band to an unknown NFC band gives it the owner and clears the notification."""
    await _tap(hass, UNKNOWN, reader_device.id)
    await _call(hass, "add_person", {"name": "Alex"})
    band = _data(hass).beacons.async_beacon("11:22:33:44:55:66", -60, "hci0", bytes.fromhex(BAND_X))
    await hass.async_block_till_done()
    await _call(hass, "link_bluetooth", {"bluetooth_band": band.id, "person": "Alex"})
    await _call(hass, "link_bluetooth", {"bluetooth_band": band.id, "band": UNKNOWN})
    await hass.async_block_till_done()
    registry = _data(hass).registry
    assert registry.get_band(UNKNOWN).person_id == registry.find_person("Alex").id
    assert registry.band_allowed(UNKNOWN)
    assert _notification(hass, f"{DOMAIN}_unknown_{UNKNOWN}") is None


async def test_enrolment_during_lockdown(hass: HomeAssistant, setup_integration, reader_device) -> None:
    await _person_with_band(hass, "Morgan")
    await _call(hass, "add_person", {"name": "Sam"})
    await _call(hass, "set_settings", {"lockdown": True})
    await _call(hass, "enrol", {"person": "Sam", "minutes": 2})
    taps = _taps(hass)
    await _tap(hass, UNKNOWN, reader_device.id)
    assert taps[-1]["enrolled"] is True and taps[-1]["allowed"] is False
    await _tap(hass, TAG, reader_device.id)  # Morgan's band: never taken by enrolment
    assert taps[-1]["enrolled"] is False and taps[-1]["person"] == "Morgan"
    await _tap(hass, UNKNOWN, reader_device.id)
    assert taps[-1]["enrolled"] is False and taps[-1]["allowed"] is False  # Sam's now, but lockdown
    await _call(hass, "set_settings", {"lockdown": False})
    await _tap(hass, UNKNOWN, reader_device.id)
    assert taps[-1]["allowed"] is True and taps[-1]["person"] == "Sam"
    sam = _data(hass).registry.find_person("Sam")
    assert _data(hass).passport.get(sam.id)["taps"] == 1  # only the welcomed tap counts


async def test_enrolment_for_a_removed_person_takes_nothing(hass: HomeAssistant, setup_integration, reader_device) -> None:
    await _call(hass, "add_person", {"name": "Casey"})
    await _call(hass, "enrol", {"person": "Casey"})
    await _call(hass, "remove_person", {"person": "Casey"})
    taps = _taps(hass)
    await _tap(hass, UNKNOWN, reader_device.id)
    assert taps[-1]["enrolled"] is False and taps[-1]["known"] is False


# ---------------------------------------------------------------------------- web views: auth and uploads


async def test_sound_view_needs_an_admin_or_a_signed_link(
    hass: HomeAssistant, setup_integration, hass_client, hass_client_no_auth, hass_read_only_access_token
) -> None:
    from homeassistant.components.http.auth import async_sign_path

    morgan = await _person_with_band(hass, "Morgan")
    casey = await _person_with_band(hass, "Casey", OTHER)
    _give_sound(hass, morgan)
    _give_sound(hass, casey)
    url = f"/api/magicband/sound/{morgan}"
    anon = await hass_client_no_auth()
    user = await hass_client(hass_read_only_access_token)
    assert (await anon.get(url)).status == 401
    assert (await user.get(url)).status == 403
    assert (await user.post(url + "?name=x.mp3", data=MP3)).status == 403
    assert (await user.delete(url)).status == 403
    assert _data(hass).registry.get_person(morgan).welcome_sound == "mp3"
    signed = async_sign_path(hass, url, timedelta(minutes=5), use_content_user=True)
    resp = await anon.get(signed)
    assert resp.status == 200 and await resp.read() == MP3
    # A link signed for one person's sound doesn't open another's.
    tampered = signed.replace(morgan, casey)
    assert (await anon.get(tampered)).status == 401


_PARTIAL_READ = (
    "BUG: sounds.SoundView.post reads the body with request.content.read(MAX_BYTES + 1), which returns only the "
    "bytes already buffered (one chunk), not up to that many: a large upload is stored cut short and the 2 MB "
    "limit is never reached. Not strict: how much arrives in the first read depends on buffering."
)


async def test_sound_upload_name_is_only_a_label(hass: HomeAssistant, setup_integration, hass_client) -> None:
    morgan = await _person_with_band(hass, "Morgan")
    client = await hass_client()
    resp = await client.post(f"/api/magicband/sound/{morgan}?name=sub%2Fdir%2Fevil.mp3", data=MP3)
    assert resp.status == 200
    assert sorted(p.name for p in Path(hass.config.path(sounds.FOLDER)).iterdir()) == [f"{morgan}.mp3"]


@pytest.mark.xfail(strict=False, reason=_PARTIAL_READ)
async def test_sound_over_2mb_is_refused(hass: HomeAssistant, setup_integration, hass_client) -> None:
    morgan = await _person_with_band(hass, "Morgan")
    client = await hass_client()
    big = b"ID3" + b"\x00" * (sounds.MAX_BYTES + 10)
    resp = await client.post(f"/api/magicband/sound/{morgan}?name=big.mp3", data=big)
    assert resp.status == 413, f"a {len(big)}-byte upload got HTTP {resp.status}"
    assert _data(hass).registry.get_person(morgan).welcome_sound is None


@pytest.mark.xfail(strict=False, reason=_PARTIAL_READ)
async def test_a_large_sound_is_stored_whole(hass: HomeAssistant, setup_integration, hass_client) -> None:
    """A 1.5 MB upload (under the 2 MB limit) must be stored in full, however the body arrives."""
    morgan = await _person_with_band(hass, "Morgan")
    client = await hass_client()
    data = b"ID3" + bytes(range(256)) * 6000  # ~1.5 MB

    async def chunks():
        for i in range(0, len(data), 65536):
            yield data[i:i + 65536]

    resp = await client.post(f"/api/magicband/sound/{morgan}?name=long.mp3", data=chunks())
    assert resp.status == 200
    stored = Path(hass.config.path(sounds.FOLDER), f"{morgan}.mp3").read_bytes()
    assert len(stored) == len(data), f"stored {len(stored)} of {len(data)} bytes"


async def test_snapshot_view_needs_an_admin_or_a_signed_link(
    hass: HomeAssistant, setup_integration, reader_device, hass_client, hass_client_no_auth,
    hass_read_only_access_token, monkeypatch,
) -> None:
    from custom_components.magicband import snapshots

    snap_id = "20261124/" + "b" * 32
    path = Path(hass.config.path(snapshots.FOLDER), "20261124", "b" * 32 + ".jpg")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xd8\xff fake jpeg")

    async def fake_capture(hass_, camera):
        return snap_id

    monkeypatch.setattr(snapshots, "async_capture", fake_capture)
    await _call(hass, "set_reader_camera", {"device_id": reader_device.id, "camera": "camera.porch"})
    await _tap(hass, TAG, reader_device.id)
    taps = (await _call(hass, "history", response=True))["taps"]
    url = taps[0]["snapshot_url"]
    plain = f"/api/magicband/snapshot/{snap_id}"
    anon = await hass_client_no_auth()
    assert (await anon.get(plain)).status == 401
    assert (await (await hass_client(hass_read_only_access_token)).get(plain)).status == 403
    assert (await (await hass_client()).get(plain)).status == 200
    resp = await anon.get(url)
    assert resp.status == 200 and (await resp.read()).startswith(b"\xff\xd8")
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(hass, "set_reader_camera", {"device_id": reader_device.id, "camera": "light.porch"})
    with pytest.raises(ServiceValidationError):
        await _call(hass, "set_reader_camera", {"device_id": "not-a-reader", "camera": "camera.porch"})


async def test_page_view_needs_a_login(hass: HomeAssistant, setup_integration, hass_client_no_auth) -> None:
    anon = await hass_client_no_auth()
    assert (await anon.get("/api/magicband/page")).status == 401


# ---------------------------------------------------------------------------- the page's shim allowlist


def _shim() -> str:
    return (Path(__file__).resolve().parents[1] / "custom_components/magicband/frontend/shim.js").read_text()


def _js_object(name: str) -> dict[str, list[str]]:
    import re

    text = _shim()
    body = re.search(rf"var {name} = (\{{.*?\}});", text, re.S).group(1)
    return {k: re.findall(r"'([^']+)'", v) for k, v in re.findall(r"(\w+):\s*\[([^\]]*)\]", body)}


async def test_shim_allowlist(hass: HomeAssistant, setup_integration) -> None:
    import re

    ctrl, svc = _js_object("CTRL"), _js_object("SVC")
    # Entity controls: only the readers' and bridges' own settings; never locks, covers, alarms...
    assert set(ctrl) == {"light", "switch", "media_player", "select", "number", "button"}
    assert ctrl["media_player"] == ["volume_set"]
    assert set(svc) == {"magicband"}
    services = set(hass.services.async_services_for_domain(DOMAIN))
    assert set(svc["magicband"]) <= services, set(svc["magicband"]) - services
    # The reader key's own actions are never callable from the page.
    assert not {"answer", "pair_reader", "unpair_reader"} & set(svc["magicband"])
    text = _shim()
    assert re.search(r"NOPRESS = /factory_reset\|safe_mode\|forget_all/", text)
    assert "['history/history_during_period', 'logbook/get_events']" in text
    assert "/^[0-9a-f]{12}$/" in text  # the sound helper only reaches /api/magicband/sound/<person id>


async def test_services_yaml_matches_registered_actions(hass: HomeAssistant, setup_integration) -> None:
    import yaml

    described = set(yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "custom_components/magicband/services.yaml").read_text()
    ))
    assert described == set(hass.services.async_services_for_domain(DOMAIN))


# ---------------------------------------------------------------------------- what admins' tools reveal


async def test_reader_key_and_names_stay_out_of_list_and_diagnostics(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    from custom_components.magicband.diagnostics import async_get_config_entry_diagnostics
    from custom_components.magicband.readers import CONF_READER_KEY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    key = entry.data[CONF_READER_KEY]
    assert len(key) == 64
    morgan = await _person_with_band(hass, "Morgan", ha_person="person.morgan")
    await _call(hass, "update_person", {"person": "Morgan", "birthday": "07-14"})
    _give_sound(hass, morgan)
    await _tap(hass, TAG, reader_device.id)
    listed = json.dumps(await _call(hass, "list", response=True), default=str)
    assert key not in listed
    diag = json.dumps(await async_get_config_entry_diagnostics(hass, entry), default=str)
    for secret in (key, "Morgan", "person.morgan", "hello.mp3", "07-14", TAG, "04-AA-BB-CC-DD-EE-FF", morgan):
        assert secret not in diag, secret


# ---------------------------------------------------------------------------- Configure (options flow)


async def _options(hass: HomeAssistant, step: str, data: dict | None = None):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": step})
    if data is not None:
        result = await hass.config_entries.options.async_configure(result["flow_id"], data)
    return result


async def test_configure_settings_apply(hass: HomeAssistant, setup_integration) -> None:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await _options(hass, "settings", {"show_in_sidebar": False, "battery_reminder_level": 35, "snapshot_days": 7})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {"show_in_sidebar": False, "battery_reminder_level": 35, "snapshot_days": 7}
    assert _data(hass).beacons.battery_low_level == 35
    history = await _call(hass, "history", response=True)
    assert history["snapshot_days"] == 7
    with pytest.raises(vol.Invalid):
        await _call(hass, "set_snapshot_days", {"days": 366})


async def test_configure_people_and_bands(hass: HomeAssistant, setup_integration, reader_device) -> None:
    await _tap(hass, UNKNOWN, reader_device.id)
    result = await _options(hass, "add_person", {"name": "Jordan", "allowed": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    result = await _options(hass, "add_person", {"name": "jordan", "allowed": True})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"name": "name_taken"}
    registry = _data(hass).registry
    jordan = registry.find_person("Jordan")
    result = await _options(hass, "assign_band", {"band": UNKNOWN, "person": jordan.id, "label": "spare"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert registry.band_allowed(UNKNOWN) and _notification(hass, f"{DOMAIN}_unknown_{UNKNOWN}") is None
    # Edit: Allowed in off blocks all their bands.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_person"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"person": jordan.id})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"name": "Jordan", "allowed": False})
    assert flow["type"] is FlowResultType.CREATE_ENTRY and not registry.band_allowed(UNKNOWN)
    result = await _options(hass, "remove_band", {"band": UNKNOWN})
    assert result["type"] is FlowResultType.CREATE_ENTRY and registry.get_band(UNKNOWN) is None


async def test_configure_link_bluetooth(hass: HomeAssistant, setup_integration, reader_device) -> None:
    result = await _options(hass, "link_bluetooth")
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "no_bluetooth_bands"
    await _call(hass, "add_person", {"name": "Alex"})
    band = _data(hass).beacons.async_beacon("11:22:33:44:55:66", -60, "hci0", bytes.fromhex(BAND_X))
    await hass.async_block_till_done()
    alex = _data(hass).registry.find_person("Alex")
    result = await _options(hass, "link_bluetooth", {"bluetooth_band": band.id, "owner": f"person:{alex.id}"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _data(hass).beacons.owner(band)[0] is alex


# ---------------------------------------------------------------------------- history and passport


async def test_history_keeps_the_last_300_and_survives_a_reload(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    await _person_with_band(hass, "Morgan")
    history = _data(hass).history
    for i in range(305):
        history.add(band="04-AA-BB-CC-DD-EE-FF", name="x", person="Morgan", reader="r", allowed=True, enrolled=False,
                    n=i)
    assert len(history.taps) == 300 and history.taps[0]["n"] == 304
    assert len((await _call(hass, "history", {"count": 300}, response=True))["taps"]) == 300
    with pytest.raises(vol.Invalid):
        await _call(hass, "history", {"count": 301}, response=True)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(_data(hass).history.taps) == 300 and _data(hass).history.taps[0]["n"] == 304


async def test_passport_and_celebrations_can_be_turned_off(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    shows: list[ServiceCall] = []
    hass.services.async_register("esphome", "lounge_reader_play_show", lambda c: shows.append(c))
    freezer.move_to(_local(2026, 12, 25, 10, 0))  # Christmas
    await _person_with_band(hass, "Morgan")
    await _call(hass, "set_settings", {"passport": False, "holiday_shows": False})
    taps = _taps(hass)
    await _tap(hass, TAG, reader_device.id)
    assert taps[-1]["badges"] == [] and taps[-1]["celebration"] is None and shows == []
    assert _data(hass).passport.get(_data(hass).registry.find_person("Morgan").id)["taps"] == 0
    await _call(hass, "set_settings", {"holiday_shows": True})
    await _tap(hass, TAG, reader_device.id)
    assert taps[-1]["celebration"] == "Christmas" and shows[-1].data == {"show": "Christmas"}
