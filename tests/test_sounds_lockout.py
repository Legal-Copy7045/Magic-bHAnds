"""Each person's own welcome sound, and the readers' refused-tap lockout."""

from __future__ import annotations

from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from custom_components.magicband import sounds
from custom_components.magicband.const import DOMAIN

TAG = "04AABBCCDDEEFF"
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64


def _data(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data


async def _person_with_band(hass: HomeAssistant, name: str = "Alice") -> str:
    await hass.services.async_call(DOMAIN, "add_person", {"name": name}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": TAG, "person": name}, blocking=True)
    return _data(hass).registry.find_person(name).id


def _reader_services(hass: HomeAssistant, node: str = "lounge-reader") -> list[ServiceCall]:
    sound_calls: list[ServiceCall] = []
    prefix = node.replace("-", "_")
    hass.services.async_register("esphome", f"{prefix}_set_known_bands", lambda c: None)
    hass.services.async_register("esphome", f"{prefix}_set_band_colours", lambda c: None)
    hass.services.async_register("esphome", f"{prefix}_set_band_sounds", lambda c: sound_calls.append(c))
    return sound_calls


def _reader_entity(hass: HomeAssistant, device, domain: str, name: str | None, uid: str) -> str:
    return er.async_get(hass).async_get_or_create(
        domain, "esphome", uid, device_id=device.id, original_name=name,
        suggested_object_id=f"lounge_{(name or domain).lower().replace(' ', '_')}",
    ).entity_id


def _give_sound(hass: HomeAssistant, person_id: str) -> None:
    folder = Path(hass.config.path(sounds.FOLDER))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{person_id}.mp3").write_bytes(MP3)
    _data(hass).registry.set_welcome_sound(person_id, "mp3", "hello.mp3")


def test_sound_files_are_recognised_by_their_contents() -> None:
    assert sounds.kind_of(MP3, "hello.mp3") == "mp3"
    assert sounds.kind_of(b"RIFF\x00\x00\x00\x00WAVEfmt ", "x.wav") == "wav"
    assert sounds.kind_of(b"fLaC\x00", None) == "flac"
    assert sounds.kind_of(b"OggS\x00", "a.ogg") == "ogg"
    assert sounds.kind_of(b"<html>not a sound</html>", "evil.mp3") is None
    assert sounds._PERSON_ID.match("0123456789ab") and not sounds._PERSON_ID.match("../../secret")


async def test_readers_learn_which_bands_have_their_own_sound(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    calls = _reader_services(hass)
    person_id = await _person_with_band(hass)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls[-1].data["bands"] == ""
    _give_sound(hass, person_id)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls[-1].data["bands"] == TAG
    assert _data(hass).readers.status_of(reader_device.id).sounds is True
    response = await hass.services.async_call(DOMAIN, "list", {}, blocking=True, return_response=True)
    assert response["people"][0]["welcome_sound"] == "hello.mp3"
    _data(hass).registry.set_welcome_sound(person_id, None)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls[-1].data["bands"] == ""


async def test_own_sound_plays_when_the_reader_welcomes(
    hass: HomeAssistant, setup_integration, reader_device, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reader_services(hass)
    person_id = await _person_with_band(hass)
    _give_sound(hass, person_id)
    player = _reader_entity(hass, reader_device, "media_player", "Speaker", "mp1")
    scan = _reader_entity(hass, reader_device, "event", "Band scan", "ev1")
    sound_switch = _reader_entity(hass, reader_device, "switch", "Sound", "sw1")
    played: list[ServiceCall] = []
    hass.services.async_register("media_player", "play_media", lambda c: played.append(c))
    monkeypatch.setattr(sounds, "async_sign_path", lambda hass, path, *a, **k: path + "?authSig=abc")
    monkeypatch.setattr(sounds, "_base_url", lambda hass: "http://ha.local:8123")
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)

    hass.bus.async_fire("tag_scanned", {"tag_id": TAG, "device_id": reader_device.id})
    await hass.async_block_till_done()
    assert played == []  # not before the reader says it welcomed them
    hass.states.async_set(scan, "2026-11-22T10:00:00", {"event_type": "welcomed"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(played) == 1
    assert played[0].data["entity_id"] == player
    assert played[0].data["announce"] is True
    assert played[0].data["media_content_id"] == f"http://ha.local:8123/api/magicband/sound/{person_id}?authSig=abc"

    # The reader's Sound switch off: nothing plays.
    hass.states.async_set(sound_switch, "off")
    hass.bus.async_fire("tag_scanned", {"tag_id": TAG, "device_id": reader_device.id})
    await hass.async_block_till_done()
    hass.states.async_set(scan, "2026-11-22T10:01:00", {"event_type": "welcomed"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(played) == 1


async def test_upload_play_and_remove_a_sound(hass: HomeAssistant, setup_integration, hass_client) -> None:
    person_id = await _person_with_band(hass)
    client = await hass_client()
    url = f"/api/magicband/sound/{person_id}"
    resp = await client.post(url + "?name=nope.mp3", data=b"<html>not a sound</html>")
    assert resp.status == 400
    resp = await client.post(url + "?name=hello.mp3", data=MP3)
    assert resp.status == 200
    person = _data(hass).registry.get_person(person_id)
    assert (person.welcome_sound, person.welcome_sound_name) == ("mp3", "hello.mp3")
    resp = await client.get(url)
    assert resp.status == 200 and await resp.read() == MP3
    resp = await client.post(f"/api/magicband/sound/{'f' * 12}", data=MP3)
    assert resp.status == 404  # not a person
    resp = await client.delete(url)
    assert resp.status == 200
    assert _data(hass).registry.get_person(person_id).welcome_sound is None
    assert not Path(hass.config.path(sounds.FOLDER), f"{person_id}.mp3").exists()


async def test_lockout_notifies_and_fires_an_event(hass: HomeAssistant, setup_integration, reader_device) -> None:
    lockout = _reader_entity(hass, reader_device, "binary_sensor", "Tap lockout", "bs1")
    events = []
    hass.bus.async_listen("magicband_lockout", lambda e: events.append(e.data))
    hass.states.async_set(lockout, "off")
    await hass.async_block_till_done()
    assert events == []  # its first state isn't a change
    hass.states.async_set(lockout, "on")
    await hass.async_block_till_done()
    assert events[-1]["locked"] is True and events[-1]["reader_device_id"] == reader_device.id
    hass.states.async_set(lockout, "off")
    await hass.async_block_till_done()
    assert events[-1]["locked"] is False


async def test_lockout_after_a_reader_restart(hass: HomeAssistant, setup_integration, reader_device) -> None:
    """BUG-002: unknown -> on is a lockout; on -> unavailable/unknown changes nothing; back off dismisses."""
    from homeassistant.components import persistent_notification

    def note():
        return persistent_notification._async_get_or_create_notifications(hass).get(
            f"{DOMAIN}_lockout_{reader_device.id}")

    lockout = _reader_entity(hass, reader_device, "binary_sensor", "Tap lockout", "bs1")
    events = []
    hass.bus.async_listen("magicband_lockout", lambda e: events.append(e.data["locked"]))
    hass.states.async_set(lockout, "unknown")  # a reader that hasn't published the sensor since it started
    await hass.async_block_till_done()
    hass.states.async_set(lockout, "on")
    await hass.async_block_till_done()
    assert events == [True] and note() is not None
    for state in ("unavailable", "unknown", "on"):  # it restarts (or reconnects) while still locked out
        hass.states.async_set(lockout, state)
        await hass.async_block_till_done()
    assert events == [True] and note() is not None
    for state in ("unavailable", "unknown", "off"):  # restarts and comes back not locked out
        hass.states.async_set(lockout, state)
        await hass.async_block_till_done()
    assert events == [True, False] and note() is None


async def test_lockout_across_a_reconnect_is_announced(hass: HomeAssistant, setup_integration, reader_device) -> None:
    """BUG-014: a reader that reconnects goes unavailable -> on/off directly (it publishes Tap lockout at boot).
    A lockout that began, or ended, while it was cut off is announced; one already announced isn't repeated."""
    from homeassistant.components import persistent_notification

    def note():
        return persistent_notification._async_get_or_create_notifications(hass).get(
            f"{DOMAIN}_lockout_{reader_device.id}")

    lockout = _reader_entity(hass, reader_device, "binary_sensor", "Tap lockout", "bs1")
    events = []
    hass.bus.async_listen("magicband_lockout", lambda e: events.append(e.data["locked"]))

    async def to(*states):
        for state in states:
            hass.states.async_set(lockout, state)
            await hass.async_block_till_done()

    await to("off", "on")
    assert events == [True] and note() is not None
    await to("unavailable", "on")  # reconnects still locked out: already announced
    assert events == [True] and note() is not None
    await to("unavailable", "off")  # restarted to clear it: the lockout ended
    assert events == [True, False] and note() is None
    await to("unavailable", "on")  # locked out while cut off from Home Assistant (the lockout works offline)
    assert events == [True, False, True] and note() is not None
    await to("unavailable", "unknown", "on")  # still the same lockout
    assert events == [True, False, True]


async def test_lockout_while_offline_after_a_start_is_announced(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    """BUG-014: after Home Assistant starts (or MagicbHAnds reloads) the reader's Tap lockout goes unavailable -> off.
    That first state is kept, so a lockout that starts while the reader is offline later is announced; a lockout
    first seen at the start (it may have been announced before) isn't, and nor is its end (INT-092)."""
    lockout = _reader_entity(hass, reader_device, "binary_sensor", "Tap lockout", "bs1")
    events = []
    hass.bus.async_listen("magicband_lockout", lambda e: events.append(e.data["locked"]))

    async def to(*states):
        for state in states:
            hass.states.async_set(lockout, state)
            await hass.async_block_till_done()

    await to("unavailable", "off", "unavailable", "on")
    assert events == [True]
    await to("unavailable", "off")
    assert events == [True, False]


async def test_lockout_state_is_seeded_at_setup(hass: HomeAssistant, setup_integration, reader_device) -> None:
    """BUG-014: a reload while the reader shows "off": a lockout that starts while it's offline afterwards is announced."""
    lockout = _reader_entity(hass, reader_device, "binary_sensor", "Tap lockout", "bs1")
    hass.states.async_set(lockout, "off")
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    events = []
    hass.bus.async_listen("magicband_lockout", lambda e: events.append(e.data["locked"]))
    for state in ("unavailable", "on"):
        hass.states.async_set(lockout, state)
        await hass.async_block_till_done()
    assert events == [True]


# ---------------------------------------------------------------------------- BUG-021: own sounds the integration can't play


async def test_unloading_sends_the_readers_an_empty_sound_list(hass: HomeAssistant, setup_integration, reader_device) -> None:
    """BUG-021: MagicbHAnds disabled, removed or reloaded: the readers chime for every band again."""
    calls = _reader_services(hass)
    person_id = await _person_with_band(hass)
    _give_sound(hass, person_id)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls[-1].data["bands"] == TAG
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert calls[-1].data["bands"] == ""


async def test_restarting_home_assistant_keeps_the_readers_sound_list(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    from homeassistant.core import CoreState

    calls = _reader_services(hass)
    person_id = await _person_with_band(hass)
    _give_sound(hass, person_id)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    n = len(calls)
    hass.set_state(CoreState.stopping)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.set_state(CoreState.running)
    assert len(calls) == n  # the readers keep it: MagicbHAnds plays the sounds again once it's back


async def test_releasing_a_reader_clears_its_sound_list_with_the_key(
    hass: HomeAssistant, setup_integration, reader_device
) -> None:
    calls = _reader_services(hass)
    order: list[str] = []
    hass.services.async_register("esphome", "lounge_reader_pair", lambda c: None)
    hass.services.async_register("esphome", "lounge_reader_set_band_sounds", lambda c: (calls.append(c), order.append("sounds")))
    hass.services.async_register("esphome", "lounge_reader_unpair", lambda c: order.append("unpair"))
    person_id = await _person_with_band(hass)
    _give_sound(hass, person_id)
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    order.clear()
    await hass.services.async_call(DOMAIN, "unpair_reader", {"device_id": reader_device.id}, blocking=True)
    key = hass.config_entries.async_entries(DOMAIN)[0].data["reader_key"]
    assert order == ["sounds", "unpair"] and calls[-1].data == {"bands": "", "key": key}


@pytest.mark.parametrize("problem", ["missing", "failed"])
async def test_a_sound_that_cant_play_goes_back_to_the_readers_chime(
    hass: HomeAssistant, setup_integration, reader_device, monkeypatch: pytest.MonkeyPatch, caplog, problem: str,
    hass_client, freezer,
) -> None:
    """BUG-021: the person's sound file is missing, or playing it fails: their band comes off the readers'
    own-sound list at once (so the reader chimes for them), until the sound is uploaded again."""
    from datetime import timedelta

    from homeassistant.exceptions import HomeAssistantError
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    calls = _reader_services(hass)
    person_id = await _person_with_band(hass)
    _give_sound(hass, person_id)
    _reader_entity(hass, reader_device, "media_player", "Speaker", "mp1")
    scan = _reader_entity(hass, reader_device, "event", "Band scan", "ev1")

    def play(call):
        raise HomeAssistantError("The media proxy failed")

    hass.services.async_register("media_player", "play_media", play if problem == "failed" else (lambda c: None))
    monkeypatch.setattr(sounds, "async_sign_path", lambda hass, path, *a, **k: path + "?authSig=abc")
    monkeypatch.setattr(sounds, "_base_url", lambda hass: "http://ha.local:8123")
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    assert calls[-1].data["bands"] == TAG
    if problem == "missing":
        Path(hass.config.path(sounds.FOLDER), f"{person_id}.mp3").unlink()

    hass.bus.async_fire("tag_scanned", {"tag_id": TAG, "device_id": reader_device.id})
    await hass.async_block_till_done()
    hass.states.async_set(scan, "2026-11-22T10:00:00", {"event_type": "welcomed"})
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.tick(timedelta(seconds=5))  # the sync it asks for (debounced)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert calls[-1].data["bands"] == ""  # the reader chimes for them from now on
    assert "the readers play their own tap-in sound" in caplog.text
    # The next welcome isn't queued for Home Assistant to play.
    hass.bus.async_fire("tag_scanned", {"tag_id": TAG, "device_id": reader_device.id})
    await hass.async_block_till_done()
    assert reader_device.id not in _data(hass).pending_sounds

    client = await hass_client()
    resp = await client.post(f"/api/magicband/sound/{person_id}?name=hello.mp3", data=MP3)
    assert resp.status == 200
    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert calls[-1].data["bands"] == TAG  # uploaded again: back on the list
