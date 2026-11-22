"""Each person's own welcome sound (optional).

A sound uploaded for a person on the MagicbHAnds page is stored in
``<config>/magicbhands_sounds/<person id>.<type>`` (not ``www``, which is
public) and served by an authenticated view. The readers are told which allowed
bands have a sound of their own (``set_band_sounds``, reader firmware 0.10.26
or later) and don't play their tap-in sound for them; when the reader welcomes
one of those bands, MagicbHAnds plays the owner's sound on that reader's
speaker through a short-lived signed link. The reader's Sound switch and its
"Sound at night" setting still apply.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
import re

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.network import NoURLAvailableError, get_url

_LOGGER = logging.getLogger(__name__)

FOLDER = "magicbhands_sounds"
URL = "/api/magicband/sound"
MAX_BYTES = 2 * 1024 * 1024  # a welcome sound is a few seconds; this is plenty
SIGNED_FOR = timedelta(minutes=5)
# File type -> (content type, how the file starts). Home Assistant converts it for the reader as it plays.
KINDS: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "mp3": ("audio/mpeg", (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3")),
    "wav": ("audio/wav", (b"RIFF",)),
    "flac": ("audio/flac", (b"fLaC",)),
    "ogg": ("audio/ogg", (b"OggS",)),
}
_PERSON_ID = re.compile(r"^[0-9a-f]{12}$")


def _root(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(FOLDER))


def sound_path(hass: HomeAssistant, person_id: str, kind: str) -> Path | None:
    if not _PERSON_ID.match(person_id or "") or kind not in KINDS:
        return None
    return _root(hass) / f"{person_id}.{kind}"


def kind_of(data: bytes, filename: str | None) -> str | None:
    """The file's type from how it starts (the name's extension only decides between look-alikes)."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    matches = [k for k, (_, magic) in KINDS.items() if any(data.startswith(m) for m in magic)]
    if ext in matches:
        return ext
    return matches[0] if matches else None


def _remove_all(hass: HomeAssistant, person_id: str) -> None:
    for kind in KINDS:
        if (path := sound_path(hass, person_id, kind)) is not None:
            path.unlink(missing_ok=True)


async def async_remove(hass: HomeAssistant, person_id: str) -> None:
    """Delete a person's sound files (when the sound is removed, or the person)."""
    await hass.async_add_executor_job(_remove_all, hass, person_id)


def _registry(hass: HomeAssistant):
    from . import _get_registry  # noqa: PLC0415 - avoids an import cycle

    return _get_registry(hass)


class SoundView(HomeAssistantView):
    """/api/magicband/sound/<person id>: GET plays it (signed link or admin); POST uploads; DELETE removes."""

    url = URL + "/{person_id}"
    name = "api:magicband:sound"
    requires_auth = True

    async def get(self, request: web.Request, person_id: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        user = request.get("hass_user")
        if "authSig" not in request.query and not (user and user.is_admin):
            raise web.HTTPForbidden
        person = _registry(hass).get_person(person_id)
        path = sound_path(hass, person_id, person.welcome_sound) if person and person.welcome_sound else None
        if path is None or not await hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(path, headers={"Content-Type": KINDS[person.welcome_sound][0],
                                               "Cache-Control": "private, no-cache"})

    async def post(self, request: web.Request, person_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        user = request.get("hass_user")
        if not (user and user.is_admin):
            raise web.HTTPForbidden
        registry = _registry(hass)
        if registry.get_person(person_id) is None or not _PERSON_ID.match(person_id):
            raise web.HTTPNotFound
        data = await request.content.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return self.json_message(f"That file is over {MAX_BYTES // (1024 * 1024)} MB: use a shorter sound", 413)
        name = request.query.get("name", "")
        kind = kind_of(data, name)
        if kind is None:
            return self.json_message("That isn't an MP3, WAV, FLAC or Ogg sound file", 400)

        def _write() -> None:
            _root(hass).mkdir(parents=True, exist_ok=True)
            _remove_all(hass, person_id)
            sound_path(hass, person_id, kind).write_bytes(data)

        await hass.async_add_executor_job(_write)
        person = registry.set_welcome_sound(person_id, kind, name or f"sound.{kind}")
        _LOGGER.info("Welcome sound for %s: %s (%d bytes)", person.name, person.welcome_sound_name, len(data))
        return self.json({"person": person.name, "sound": person.welcome_sound_name})

    async def delete(self, request: web.Request, person_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        user = request.get("hass_user")
        if not (user and user.is_admin):
            raise web.HTTPForbidden
        registry = _registry(hass)
        if registry.get_person(person_id) is None:
            raise web.HTTPNotFound
        await async_remove(hass, person_id)
        registry.set_welcome_sound(person_id, None)
        return self.json({"removed": True})


@callback
def async_register_view(hass: HomeAssistant) -> None:
    key = f"{FOLDER}_view"
    if not hass.data.get(key):
        hass.http.register_view(SoundView())
        hass.data[key] = True


def _reader_entity(hass: HomeAssistant, device_id: str, domain: str, name: str | None = None) -> str | None:
    """One of the reader's ESPHome entities: by domain, and by its name if given."""
    for entry in er.async_entries_for_device(er.async_get(hass), device_id):
        if entry.platform == "esphome" and entry.domain == domain and (name is None or entry.original_name == name):
            return entry.entity_id
    return None


def reader_sound_allowed(hass: HomeAssistant, device_id: str) -> bool:
    """Whether the reader would play a sound now: its Sound switch on, and not night with Sound at night Off."""
    def state(domain: str, name: str) -> str | None:
        eid = _reader_entity(hass, device_id, domain, name)
        st = hass.states.get(eid) if eid else None
        return st.state if st else None

    if state("switch", "Sound") == "off":
        return False
    return not (state("binary_sensor", "Night now") == "on" and state("select", "Sound at night") == "Off")


def _base_url(hass: HomeAssistant) -> str:
    try:
        return get_url(hass, allow_external=False, allow_ip=True)
    except NoURLAvailableError:
        return get_url(hass)


async def async_play(hass: HomeAssistant, person, device_id: str, *, check_settings: bool = True) -> bool:
    """Play `person`'s welcome sound on the reader's speaker. False if it couldn't (no sound, no speaker, muted)."""
    if not person.welcome_sound:
        return False
    player = _reader_entity(hass, device_id, "media_player")
    if player is None:
        _LOGGER.warning("No speaker found on the reader to play %s's welcome sound", person.name)
        return False
    if check_settings and not reader_sound_allowed(hass, device_id):
        return False
    path = sound_path(hass, person.id, person.welcome_sound)
    if path is None or not await hass.async_add_executor_job(path.is_file):
        _LOGGER.warning("%s's welcome sound file is missing; upload it again", person.name)
        return False
    signed = async_sign_path(hass, f"{URL}/{person.id}", SIGNED_FOR, use_content_user=True)
    try:
        await hass.services.async_call(
            "media_player", "play_media",
            {"entity_id": player, "media_content_id": _base_url(hass) + signed,
             "media_content_type": "music", "announce": True},
            blocking=True,
        )
    except Exception as err:  # noqa: BLE001 - a missing sound mustn't affect the tap
        _LOGGER.warning("Couldn't play %s's welcome sound on %s: %s", person.name, player, err)
        return False
    return True
