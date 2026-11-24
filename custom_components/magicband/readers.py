"""MagicBand readers: which devices are readers, keeping their allowed lists current, and their health.

A reader is an ESPHome device built from esphome/magicband-reader.yaml. Only
readers count for taps and only readers get the allowed list. Everything here
uses the device and entity registries and the reader's own entities, never
other integrations' configuration.

Each reader keeps its own copy of the allowed list (so it works with Home
Assistant offline) and, from 0.10.4, of its owners' welcome colours. They're
sent on every change, when a reader connects, every few minutes, and when a
band's schedule opens or closes. Readers from 0.10.4 reply whether they
applied the list; failures, a list too long for the readers, and readers
that stay offline show in Home Assistant's Repairs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
import re
import time
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, READER_MODEL, READER_SET_SERVICE_SUFFIX
from .registry import MagicBandRegistry

_LOGGER = logging.getLogger(__name__)

# The reader stores its allowed list as ",UID,UID," in 3,200 characters
# including the terminator (esphome/magicband-reader.yaml, known_list): 213
# bands with 7-byte IDs. Readers on 0.10.3 or earlier hold 1,600 (106 bands).
READER_LIST_CAPACITY = 3199
# The reader's other two lists (same file): band_colours ",UID=Colour,..." in 4,096 characters and band_sounds
# ",UID,..." in 1,600, both including the terminator. A list that doesn't fit is refused whole, so only what fits
# is sent (whole entries) and a repair names the reader.
COLOURS_CAPACITY = 4095
SOUNDS_CAPACITY = 1599
COLOURS_SERVICE_SUFFIX = "_set_band_colours"
SOUNDS_SERVICE_SUFFIX = "_set_band_sounds"  # reader firmware 0.10.26+: bands with their own welcome sound
# The reader firmware (0.10.4+) reports its ESPHome node name in this diagnostic text sensor.
NODE_NAME_SENSOR = "ESPHome name"
OFFLINE_REPAIR_AFTER = timedelta(minutes=15)
CONFIRMING_FIRMWARE = (0, 10, 4)  # readers that reply whether they applied the list
SIGNAL_READER_STATUS = f"{DOMAIN}_reader_status"

# The readers' light shows (0.10.17+), as in components/magicband/shows.h.
SHOW_NAMES = (
    "Rainbow rush", "Fireworks", "Comet chase", "Colour parade", "Twinkle", "Heartbeat",
    "Ocean", "Fire", "Pinwheel", "Confetti", "Penguins", "Goal",
    "Aurora", "Candy cane", "Thunderstorm", "Sunrise", "Disco",
    # celebrations (holidays.py) and the passport's Stamp (reader firmware 0.10.24 or later)
    "Birthday", "New Year", "Valentine", "St Patrick", "Easter", "Stars and Stripes", "Halloween",
    "Thanksgiving", "Hanukkah", "Christmas", "Stamp",
)
SHOW_SERVICE_SUFFIX = "_play_show"
PAIR_SERVICE_SUFFIX = "_pair"
PAIRING_BUSY = "PAIRING_BUSY"  # another key's pairing request is waiting on the reader (someone else is pairing it)
PAIRING_COOLDOWN = "PAIRING_COOLDOWN"  # our own request expired without a tap: it may ask again 2 minutes later
PAIRING_RETRY = 120  # seconds before a busy or cooling-down reader is asked again
NO_REPLY_RETRY = 30  # seconds before a reader that didn't reply (e.g. still starting) is synced again
NO_REPLY_REPAIR = 3  # failed syncs in a row with no reply before the "didn't take the list" repair shows
PAIRING_PENDING = "PAIRING_PENDING"  # the reader's reply while a first pairing waits for its tap  # readers from 0.10.20: the protected actions then need the key
PAIRING_WINDOW = 120  # seconds the reader waits for the tap that confirms a pairing request (PAIR_CONFIRM_MS)
PAIRING_STORE_KEY = f"{DOMAIN}.pairing"  # when our waiting pairing requests end, kept over a restart or reload
PAIRED_ELSEWHERE = "paired with another key"  # the reader's refusal once another key has been confirmed
# A reader's repairs, removed with the reader (or when it is released).
READER_ISSUES = ("reader_offline", "reader_sync_failed", "reader_pairing", "reader_pairing_busy",
                 "reader_paired_elsewhere", "colours_too_long", "sounds_too_long")
CONF_READER_KEY = "reader_key"

# States of a reader's "Allowed list" sensor.
UP_TO_DATE = "up_to_date"
FAILED = "failed"
UNCONFIRMED = "unconfirmed"  # sent to older firmware, which can't say whether it applied it
OFFLINE = "offline"
WAITING = "waiting"


def _esphome_entities(hass: HomeAssistant, device_id: str) -> list[er.RegistryEntry]:
    return [e for e in er.async_entries_for_device(er.async_get(hass), device_id) if e.platform == "esphome"]


def is_reader_device(hass: HomeAssistant, device_id: str | None) -> bool:
    """True if the device is a MagicBand reader: an ESPHome device built from the reader firmware.

    The model alone isn't enough: other integrations (a phone registered with
    the mobile app, for example) let any logged-in user pick a device's model
    and name, and send tag scans from it. So the device must also have
    ESPHome entities.
    """
    if not device_id:
        return False
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return False
    entities = _esphome_entities(hass, device_id)
    if not entities:
        return False
    if (device.model or "").lower() == READER_MODEL:
        return True
    # A reader built with another project name: an ESPHome device with the reader's "Known bands" sensor.
    return any(e.domain == "sensor" and e.entity_id.endswith("_known_bands") for e in entities)


def reader_devices(hass: HomeAssistant) -> list[dr.DeviceEntry]:
    """Every reader: among the ESPHome config entries' devices (readers are always ESPHome devices)."""
    dev_reg, seen, out = dr.async_get(hass), set(), []
    for esphome_entry in hass.config_entries.async_entries("esphome"):
        for device in dr.async_entries_for_config_entry(dev_reg, esphome_entry.entry_id):
            if device.id not in seen and is_reader_device(hass, device.id):
                seen.add(device.id)
                out.append(device)
    return out


def node_name(hass: HomeAssistant, device: dr.DeviceEntry) -> str | None:
    """The reader's ESPHome node name, which its actions are named after (esphome.<node>_set_known_bands)."""
    for entity in _esphome_entities(hass, device.id):
        if entity.original_name == NODE_NAME_SENSOR and (state := hass.states.get(entity.entity_id)) is not None:
            if state.state not in ("unknown", "unavailable", ""):
                return state.state
    # Older firmware: the name the reader firmware gives itself, magicband-reader-<end of its MAC>.
    for kind, value in device.connections:
        if kind == dr.CONNECTION_NETWORK_MAC:
            return f"magicband-reader-{value.replace(':', '').lower()[-6:]}"
    return None


def _no_reply(err: Exception) -> bool:
    """Whether a failed reader action only got no reply (a timeout, or the reader not connected yet), rather
    than an answer refusing it."""
    text = str(err).lower()
    return isinstance(err, TimeoutError) or any(
        word in text for word in ("timeout", "timed out", "not connected", "unavailable", "no response")
    )


def _service_for(node: str, suffix: str) -> str:
    return f"{node.replace('-', '_')}{suffix}"


def firmware_version(device: dr.DeviceEntry) -> tuple[int, ...] | None:
    """The reader firmware's project version, from the device's software version ("0.10.4 (ESPHome ...)")."""
    m = re.match(r"\s*v?(\d+)\.(\d+)\.(\d+)", device.sw_version or "")
    return tuple(int(x) for x in m.groups()) if m else None


def list_size(uids: list[str]) -> int:
    """Characters the reader needs for this list (",UID,UID,")."""
    return 1 + sum(len(u) + 1 for u in uids)


def fit_entries(entries: list[str], capacity: int) -> list[str]:
    """The leading entries whose reader form (",a,b,") fits in `capacity` characters."""
    kept: list[str] = []
    size = 1
    for entry in entries:
        size += len(entry) + 1
        if size > capacity:
            break
        kept.append(entry)
    return kept


def _manager(hass: HomeAssistant) -> "ReaderManager | None":
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data.readers if entries else None


MAX_SHOWS_PER_MINUTE = 12  # per reader: play_show is open to every user


async def async_play_show(
    hass: HomeAssistant, show: str, device_ids: list[str] | None = None, context: Context | None = None
) -> dict[str, Any]:
    """Plays a light show ("Random" or one of SHOW_NAMES) on the readers (all of them, or these devices).

    Returns {"played": [reader names], "skipped": [names of readers that are offline, too old,
    busy (more than MAX_SHOWS_PER_MINUTE) or that failed]}.
    """
    played: list[str] = []
    skipped: list[str] = []
    times: dict[str, deque[float]] = hass.data.setdefault(f"{DOMAIN}_show_times", {})
    now = time.monotonic()
    for device in reader_devices(hass):
        if device_ids and device.id not in device_ids:
            continue
        if (manager := _manager(hass)) and manager.registry.reader_released(device.id):
            continue
        name = device.name_by_user or device.name or "MagicBand reader"
        node = node_name(hass, device)
        service = _service_for(node, SHOW_SERVICE_SUFFIX) if node else None
        if service is None or not hass.services.has_service("esphome", service):
            skipped.append(name)
            continue
        recent = times.setdefault(device.id, deque())
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= MAX_SHOWS_PER_MINUTE:
            skipped.append(name)
            continue
        recent.append(now)
        try:
            await hass.services.async_call("esphome", service, {"show": show}, blocking=True, context=context)
        except Exception as err:  # noqa: BLE001 - one reader shouldn't stop the rest
            _LOGGER.warning("Reader %s didn't play the light show: %s", name, err)
            skipped.append(name)
        else:
            played.append(name)
    return {"played": played, "skipped": skipped}


@dataclass
class ReaderStatus:
    device_id: str
    name: str
    state: str = WAITING
    error: str | None = None
    last_sync: str | None = None
    bands: int | None = None
    colours: bool | None = None  # whether it takes welcome colours (0.10.4+)
    sounds: bool | None = None  # whether it took the list of bands with their own welcome sound (0.10.26+)


class ReaderManager:
    """Sends readers their allowed list and keeps track of how each one is doing."""

    def __init__(self, hass: HomeAssistant, registry: MagicBandRegistry, key: str | None = None) -> None:
        self.hass = hass
        self.registry = registry
        self.key = key
        self.statuses: dict[str, ReaderStatus] = {}
        self._offline_since: dict[str, datetime] = {}
        self._last_sent: tuple | None = None
        self.sounds_left_out: set[str] = set()  # bands with a sound that didn't fit in the readers' list
        self._retry_at: float | None = None  # when a reader that couldn't pair yet is asked again (monotonic)
        # Failed syncs in a row per reader that were only "no reply" (a timeout, or the reader not connected
        # yet, e.g. just after it restarted). Those usually sort themselves out, so the error repair waits for
        # NO_REPLY_REPAIR of them in a row; a reader that answers and refuses gets the repair at once.
        self._no_reply: dict[str, int] = {}
        # Readers on which MagicbHAnds' own pairing request is waiting for its tap: device -> cancels the
        # scheduled end of that request's 2-minute window. "Tap a band" shows only while one is here.
        self._pair_windows: dict[str, CALLBACK_TYPE] = {}
        # When each of those requests' windows ends (UTC, ISO), saved: the reader answers PAIRING_PENDING to the
        # same key while an older request waits and doesn't say how long is left, so after a restart or reload in
        # the middle of a wait "Tap a band" keeps that request's end instead of starting a fresh 2 minutes.
        self._pair_ends: dict[str, str] = {}
        self._pair_store: Store[dict] = Store(hass, 1, PAIRING_STORE_KEY)
        # People whose own welcome sound couldn't be played (file missing, playback failed): their bands are left
        # out of the readers' own-sound list, so the readers chime for them, until the sound is uploaded again.
        self.sounds_failing: set[str] = set()

    async def async_load(self) -> None:
        """The ends of pairing windows saved before a restart or reload (ones already over are dropped)."""
        stored = await self._pair_store.async_load() or {}
        now = dt_util.utcnow()
        for device_id, end in (stored.get("ends") or {}).items():
            when = dt_util.parse_datetime(end) if isinstance(end, str) else None
            if when is not None and when > now:
                self._pair_ends[device_id] = end

    @callback
    def _save_pair_end(self, device_id: str, end: datetime | None) -> None:
        if end is None:
            if self._pair_ends.pop(device_id, None) is None:
                return
        else:
            self._pair_ends[device_id] = end.isoformat()
        self.hass.async_create_task(self._pair_store.async_save({"ends": dict(self._pair_ends)}))

    # ------------------------------------------------------------------ sync

    async def async_sync(self) -> dict[str, Any]:
        """Send the allowed list (and welcome colours) to every reader that's online.

        Returns {"readers", "applied", "failed"} (failed: reader names).
        """
        now = dt_util.now()
        uids = self.registry.allowed_uids(now)
        colours = self.registry.welcome_colours(now)
        all_sounds = [uid for uid in self.registry.sound_uids(now)
                      if (band := self.registry.get_band(uid)) is None or band.person_id not in self.sounds_failing]
        sound_uids = fit_entries(all_sounds, SOUNDS_CAPACITY)
        self.sounds_left_out = set(all_sounds) - set(sound_uids)
        sound_list = ",".join(sound_uids)
        bands = ",".join(uids)
        all_colours = [f"{uid}={colour}" for uid, colour in colours.items()]
        colour_entries = fit_entries(all_colours, COLOURS_CAPACITY)
        colour_list = ",".join(colour_entries)
        if len(colour_entries) < len(all_colours):
            _LOGGER.warning("The welcome colours of %d band(s) don't fit in a reader (room for %d of %d): "
                            "they're welcomed in the reader's Welcome colour",
                            len(all_colours) - len(colour_entries), len(colour_entries), len(all_colours))
        if self.sounds_left_out:
            _LOGGER.warning("%d band(s) with their own welcome sound don't fit in a reader's list (room for %d of %d): "
                            "they get the reader's tap-in sound", len(self.sounds_left_out), len(sound_uids),
                            len(all_sounds))
        self._last_sent = (tuple(uids), tuple(sorted(colours.items())))
        too_long = list_size(uids) > READER_LIST_CAPACITY
        self._issue("list_too_long", too_long, "list_too_long", {"bands": str(len(uids)), "capacity": "213"})

        sent = failed = 0
        failed_names: list[str] = []
        known_services = {_service_for(n, READER_SET_SERVICE_SUFFIX) for d in reader_devices(self.hass) if (n := node_name(self.hass, d))}
        for name in sorted(self.hass.services.async_services_for_domain("esphome")):
            if name.endswith(READER_SET_SERVICE_SUFFIX) and name not in known_services:
                _LOGGER.warning("Not sending the allowed list to esphome.%s: not a MagicBand reader", name)

        for device in reader_devices(self.hass):
            status = self._status(device)
            if self.registry.reader_released(device.id):
                # Released with unpair_reader: left alone (no list, no pairing) so another
                # Home Assistant can pair it. magicband.pair_reader takes it back.
                status.state, status.error = OFFLINE, "Released: not managed by this Home Assistant"
                self._delete_issues(device.id)
                continue
            node = node_name(self.hass, device)
            service = _service_for(node, READER_SET_SERVICE_SUFFIX) if node else None
            if service is None or not self.hass.services.has_service("esphome", service):
                status.state, status.error = OFFLINE, None
                continue
            sent += 1
            keyed = self._keyed(node)
            try:
                if keyed:
                    await self._pair_or_wait(device, status.name, node)
                await self.hass.services.async_call(
                    "esphome", service, {"bands": bands, **({"key": self.key} if keyed else {})}, blocking=True
                )
            except Exception as err:  # noqa: BLE001 - one reader shouldn't stop the rest
                failed += 1
                failed_names.append(status.name)
                status.state, status.error = FAILED, str(err) or type(err).__name__
                if _no_reply(err):
                    self._no_reply[device.id] = self._no_reply.get(device.id, 0) + 1
                    self._schedule_retry(NO_REPLY_RETRY)
                else:
                    self._no_reply.pop(device.id, None)
                _LOGGER.warning("Reader %s didn't take the allowed list: %s", status.name, status.error)
            else:
                version = firmware_version(device)
                status.state = UP_TO_DATE if version is None or version >= CONFIRMING_FIRMWARE else UNCONFIRMED
                status.error, status.bands = None, len(uids)
                self._no_reply.pop(device.id, None)
                status.last_sync = dt_util.utcnow().isoformat()
            colour_service = _service_for(node, COLOURS_SERVICE_SUFFIX)
            status.colours = self.hass.services.has_service("esphome", colour_service)
            if status.colours and status.state != FAILED:
                try:
                    await self.hass.services.async_call(
                        "esphome", colour_service, {"colours": colour_list, **({"key": self.key} if keyed else {})},
                        blocking=True,
                    )
                except Exception as err:  # noqa: BLE001 - colours are cosmetic
                    _LOGGER.warning("Reader %s didn't take the welcome colours: %s", status.name, err)
            self._issue(f"colours_too_long_{device.id}", bool(status.colours) and len(colour_entries) < len(all_colours),
                        "colours_too_long", {"reader": status.name, "kept": str(len(colour_entries)),
                                             "total": str(len(all_colours))})
            # Which bands have their own welcome sound. Until a reader has taken it, MagicbHAnds doesn't
            # play people's sounds there (the reader would play its tap-in sound as well).
            sound_service = _service_for(node, SOUNDS_SERVICE_SUFFIX)
            status.sounds = False
            if self.hass.services.has_service("esphome", sound_service) and status.state != FAILED:
                try:
                    await self.hass.services.async_call(
                        "esphome", sound_service, {"bands": sound_list, **({"key": self.key} if keyed else {})},
                        blocking=True,
                    )
                    status.sounds = True
                except Exception as err:  # noqa: BLE001 - sounds are cosmetic
                    _LOGGER.warning("Reader %s didn't take the welcome sounds: %s", status.name, err)
            self._issue(f"sounds_too_long_{device.id}", status.sounds and bool(self.sounds_left_out),
                        "sounds_too_long", {"reader": status.name, "kept": str(len(sound_uids)),
                                            "total": str(len(all_sounds))})
            self._issue(
                f"reader_sync_failed_{device.id}",
                status.state == FAILED and not 0 < self._no_reply.get(device.id, 0) < NO_REPLY_REPAIR,
                "reader_sync_failed",
                {"reader": status.name, "error": status.error or ""},
                severity=ir.IssueSeverity.ERROR,
            )
        async_dispatcher_send(self.hass, SIGNAL_READER_STATUS)
        _LOGGER.debug("Synced %d allowed band(s) to %d reader(s), %d failed", len(uids), sent, failed)
        return {"readers": sent, "applied": sent - failed, "failed": failed_names}

    def _keyed(self, node: str) -> bool:
        """Whether this reader's firmware supports pairing (0.10.20+): then its protected actions need the key."""
        return bool(self.key) and self.hass.services.has_service("esphome", _service_for(node, PAIR_SERVICE_SUFFIX))

    async def _pair(self, node: str) -> None:
        """Pair the reader with this integration's key (a no-op if it already has it)."""
        await self.hass.services.async_call(
            "esphome", _service_for(node, PAIR_SERVICE_SUFFIX), {"key": self.key}, blocking=True
        )

    async def _pair_or_wait(self, device: dr.DeviceEntry, name: str, node: str) -> None:
        """Pair the reader. A reader that's never been paired waits for a band tap on it to confirm
        (reader_key.h): while MagicbHAnds' own request waits, a repair asks for that tap, and the list is
        sent anyway (an unpaired reader takes it). Any other refusal is raised.

        "Tap a band" shows only from the moment the reader accepts our request until that request's 2-minute
        window ends (or the tap confirms it): outside it another key's request may be the one waiting, and a
        tap would pair the reader with them."""
        asked = time.monotonic()
        busy, tap = f"reader_pairing_busy_{device.id}", f"reader_pairing_{device.id}"
        try:
            await self._pair(node)
        except Exception as err:
            text = str(err)
            if PAIRING_PENDING in text:  # ours is the request waiting (asking again doesn't extend it)
                self._issue(busy, False, "reader_pairing_busy", {"reader": name})
                if device.id not in self._pair_windows:
                    now = dt_util.utcnow()
                    end = dt_util.parse_datetime(self._pair_ends.get(device.id) or "")
                    if end is not None and end > now:
                        # Our request from before a restart or reload is the one waiting: its window keeps its end
                        # (SEC-021/BUG-024), so "Tap a band" never outlasts the reader's own wait.
                        left = max(1.0, (end - now).total_seconds())
                    else:
                        left = max(1.0, PAIRING_WINDOW - (time.monotonic() - asked))
                        self._save_pair_end(device.id, now + timedelta(seconds=left))
                    self._pair_windows[device.id] = async_call_later(
                        self.hass, left, callback(lambda _now, d=device.id: self._pair_window_ended(d)))
                    self._issue(tap, True, "reader_pairing", {"reader": name})
                return
            self._end_pair_window(device.id)
            if PAIRING_BUSY in text:
                # Someone else's pairing request is waiting on it: a tap now would pair it with them. Say so,
                # don't ask for a tap, and ask again after their request has run out.
                self._issue(busy, True, "reader_pairing_busy", {"reader": name})
                self._retry_later()
                return
            if PAIRING_COOLDOWN in text:
                # Our wait ran out without a tap; for 2 minutes the reader won't take our key again, and any other
                # key may ask meanwhile, so no "Tap a band" now: asked again after the gap.
                self._issue(busy, False, "reader_pairing_busy", {"reader": name})
                self._retry_later()
                return
            self._issue(busy, False, "reader_pairing_busy", {"reader": name})
            if PAIRED_ELSEWHERE in text:
                _LOGGER.warning("Reader %s is paired with another key, not MagicbHAnds'", name)
                self._issue(f"reader_paired_elsewhere_{device.id}", True, "reader_paired_elsewhere", {"reader": name},
                            severity=ir.IssueSeverity.ERROR)
            raise
        self._end_pair_window(device.id)
        self._issue(busy, False, "reader_pairing_busy", {"reader": name})
        self._issue(f"reader_paired_elsewhere_{device.id}", False, "reader_paired_elsewhere", {})

    @callback
    def _end_pair_window(self, device_id: str) -> None:
        """Our pairing request on this reader is no longer waiting: "Tap a band" goes."""
        if (cancel := self._pair_windows.pop(device_id, None)) is not None:
            cancel()
        self._save_pair_end(device_id, None)
        ir.async_delete_issue(self.hass, DOMAIN, f"reader_pairing_{device_id}")

    @callback
    def _pair_window_ended(self, device_id: str) -> None:
        """Our request's 2 minutes are up without a tap: stop asking for one, and ask the reader again later."""
        self._pair_windows.pop(device_id, None)
        self._save_pair_end(device_id, None)
        ir.async_delete_issue(self.hass, DOMAIN, f"reader_pairing_{device_id}")
        self._retry_later()

    @callback
    def pairing_confirmed(self, device_id: str) -> None:
        """The reader's "Paired with MagicbHAnds" sensor turned on (a tap confirmed a pairing): "Tap a band" goes
        now. The sync that follows checks that the reader took MagicbHAnds' key, not another one."""
        self._end_pair_window(device_id)

    def _retry_later(self) -> None:
        self._schedule_retry(PAIRING_RETRY)

    def _schedule_retry(self, seconds: float) -> None:
        """Sync again after `seconds` (checked every minute), keeping an earlier retry if one is due sooner."""
        at = time.monotonic() + seconds
        if self._retry_at is None or at < self._retry_at:
            self._retry_at = at

    def retry_due(self) -> bool:
        """Whether a reader that was busy pairing (or cooling down) should be asked again now (checked every minute)."""
        if self._retry_at is None or time.monotonic() < self._retry_at:
            return False
        self._retry_at = None
        return True

    async def async_unpair(self, device_id: str, context: Context | None = None) -> None:
        """Release a reader from this integration's key (to move it to another Home Assistant)."""
        device = dr.async_get(self.hass).async_get(device_id)
        node = node_name(self.hass, device) if device and is_reader_device(self.hass, device_id) else None
        if node is None:
            raise ServiceValidationError("That device isn't a MagicBand reader")
        if not self._keyed(node):
            raise ServiceValidationError("The reader isn't connected, or its firmware can't be paired")
        # Its own-sound list goes first (with the key, while it still needs it): released, MagicbHAnds no longer
        # plays anyone's sound there, so the reader chimes for every band again.
        await self._clear_sounds(device, node, keyed=True)
        await self.hass.services.async_call(
            "esphome", _service_for(node, "_unpair"), {"key": self.key}, blocking=True, context=context
        )
        # Stop syncing it, or the next sync would ask to pair it again (and, while that request
        # waits, block the Home Assistant it's moving to).
        self.registry.set_reader_released(device_id, True)
        self._delete_issues(device_id)

    async def async_reclaim(self, device_id: str) -> dict[str, Any]:
        """Manage a released reader again (pair_reader): it pairs on this sync (a band tap confirms)."""
        if not is_reader_device(self.hass, device_id):
            raise ServiceValidationError("That device isn't a MagicBand reader")
        self.registry.set_reader_released(device_id, False)
        return await self.async_sync()

    async def async_answer(self, device_id: str, allow: bool, context: Context | None = None) -> None:
        """Answer a reader in "Ask Home Assistant" mode (its accept / deny action, with the key)."""
        device = dr.async_get(self.hass).async_get(device_id)
        node = node_name(self.hass, device) if device and is_reader_device(self.hass, device_id) else None
        if node is None:
            raise ServiceValidationError("That device isn't a MagicBand reader")
        if self.registry.reader_released(device_id):
            raise ServiceValidationError("This reader was released (unpair_reader); pair_reader takes it back")
        service = _service_for(node, "_accept" if allow else "_deny")
        if not self.hass.services.has_service("esphome", service):
            raise ServiceValidationError("The reader isn't connected")
        data = {"key": self.key} if self._keyed(node) else {}
        await self.hass.services.async_call("esphome", service, data, blocking=True, context=context)

    def schedule_changed(self, now: datetime | None = None) -> bool:
        """Whether the allowed list or colours differ from what was last sent (a schedule opened or closed)."""
        now = now or dt_util.now()
        current = (tuple(self.registry.allowed_uids(now)), tuple(sorted(self.registry.welcome_colours(now).items())))
        return self._last_sent is not None and current != self._last_sent

    # ------------------------------------------------------------------ health

    @callback
    def check_health(self, now: datetime | None = None) -> None:
        """Readers that have been offline (no actions in Home Assistant) for a while get a repair."""
        now = now or dt_util.utcnow()
        devices = {d.id: d for d in reader_devices(self.hass)}
        for device_id, device in devices.items():
            status = self._status(device)
            if self.registry.reader_released(device_id):  # another Home Assistant's now: no repairs here
                self._offline_since.pop(device_id, None)
                ir.async_delete_issue(self.hass, DOMAIN, f"reader_offline_{device_id}")
                continue
            node = node_name(self.hass, device)
            online = node is not None and self.hass.services.has_service(
                "esphome", _service_for(node, READER_SET_SERVICE_SUFFIX)
            )
            if online:
                self._offline_since.pop(device_id, None)
                if status.state == OFFLINE:
                    status.state = WAITING
            else:
                self._offline_since.setdefault(device_id, now)
                status.state = OFFLINE
            since = self._offline_since.get(device_id)
            self._issue(
                f"reader_offline_{device_id}",
                since is not None and now - since >= OFFLINE_REPAIR_AFTER,
                "reader_offline",
                {"reader": status.name, "since": dt_util.as_local(since).strftime("%H:%M") if since else ""},
            )
        for device_id in list(self.statuses):
            if device_id not in devices:
                self.statuses.pop(device_id)
                self._offline_since.pop(device_id, None)
                self._delete_issues(device_id)
        async_dispatcher_send(self.hass, SIGNAL_READER_STATUS)

    def status_of(self, device_id: str) -> ReaderStatus | None:
        return self.statuses.get(device_id)

    def takes_sounds(self, device_id: str) -> bool:
        """Whether the reader's firmware knows about people's own sounds (has set_band_sounds, 0.10.26+).

        Such a reader keeps the last list it took across restarts (Home Assistant's too), so it skips its own
        tap-in sound for those bands even before this Home Assistant's first sync: HA plays theirs.
        """
        device = dr.async_get(self.hass).async_get(device_id)
        node = node_name(self.hass, device) if device else None
        return bool(node) and self.hass.services.has_service("esphome", _service_for(node, SOUNDS_SERVICE_SUFFIX))

    def report(self) -> list[dict[str, Any]]:
        return [asdict(s) for s in self.statuses.values()]

    # ------------------------------------------------------------------ own sounds

    @callback
    def sound_failed(self, person_id: str) -> bool:
        """A person's own sound couldn't be played: their bands come off the readers' own-sound list at the next
        sync (the reader chimes for them from then on). True if that's news (a sync is needed)."""
        if person_id in self.sounds_failing:
            return False
        self.sounds_failing.add(person_id)
        return True

    @callback
    def sound_ok(self, person_id: str) -> bool:
        """The person's sound was uploaded again (or played): back on the list. True if it had been taken off."""
        if person_id not in self.sounds_failing:
            return False
        self.sounds_failing.discard(person_id)
        return True

    async def _clear_sounds(self, device: dr.DeviceEntry, node: str, keyed: bool | None = None) -> None:
        """Send the reader an empty own-sound list, so it plays its own tap-in sound for every band again."""
        service = _service_for(node, SOUNDS_SERVICE_SUFFIX)
        if not self.hass.services.has_service("esphome", service):
            return
        if keyed is None:
            keyed = self._keyed(node)
        try:
            await self.hass.services.async_call(
                "esphome", service, {"bands": "", **({"key": self.key} if keyed else {})}, blocking=True)
        except Exception as err:  # noqa: BLE001 - best effort: the reader may be going too
            _LOGGER.warning("Couldn't clear %s's list of bands with their own sound: %s",
                            device.name_by_user or device.name, err)

    async def async_release_sounds(self) -> None:
        """MagicbHAnds is unloading (disabled, removed, reloaded): it stops playing people's own sounds, so every
        managed reader that's online gets an empty own-sound list and chimes for every band again."""
        for device in reader_devices(self.hass):
            if self.registry.reader_released(device.id):
                continue
            if node := node_name(self.hass, device):
                await self._clear_sounds(device, node)

    # ------------------------------------------------------------------ helpers

    @callback
    def _delete_issues(self, device_id: str) -> None:
        """A reader removed or released: none of its repairs stays."""
        if (cancel := self._pair_windows.pop(device_id, None)) is not None:
            cancel()
        self._save_pair_end(device_id, None)
        for issue in READER_ISSUES:
            ir.async_delete_issue(self.hass, DOMAIN, f"{issue}_{device_id}")

    @callback
    def async_shutdown(self) -> None:
        """Unloaded (reload, disable, remove, Home Assistant stopping): nobody ends the pairing windows now, so
        "Tap a band" goes with them (BUG-024). Their saved ends stay for the next start."""
        for device_id, cancel in self._pair_windows.items():
            cancel()
            ir.async_delete_issue(self.hass, DOMAIN, f"reader_pairing_{device_id}")
        self._pair_windows.clear()

    def _status(self, device: dr.DeviceEntry) -> ReaderStatus:
        status = self.statuses.setdefault(device.id, ReaderStatus(device_id=device.id, name=""))
        status.name = device.name_by_user or device.name or "MagicBand reader"
        return status

    def _issue(
        self,
        issue_id: str,
        active: bool,
        key: str,
        placeholders: dict[str, str],
        severity: ir.IssueSeverity = ir.IssueSeverity.WARNING,
    ) -> None:
        if active:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=severity,
                translation_key=key,
                translation_placeholders=placeholders,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
