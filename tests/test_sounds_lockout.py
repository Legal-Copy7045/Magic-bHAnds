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
