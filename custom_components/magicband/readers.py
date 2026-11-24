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

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
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
PAIRING_PENDING = "PAIRING_PENDING"  # the reader's reply while a first pairing waits for its tap  # readers from 0.10.20: the protected actions then need the key
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

    # ------------------------------------------------------------------ sync

    async def async_sync(self) -> dict[str, Any]:
        """Send the allowed list (and welcome colours) to every reader that's online.

        Returns {"readers", "applied", "failed"} (failed: reader names).
        """
        now = dt_util.now()
        uids = self.registry.allowed_uids(now)
        colours = self.registry.welcome_colours(now)
        all_sounds = self.registry.sound_uids(now)
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
                _LOGGER.warning("Reader %s didn't take the allowed list: %s", status.name, status.error)
            else:
                version = firmware_version(device)
                status.state = UP_TO_DATE if version is None or version >= CONFIRMING_FIRMWARE else UNCONFIRMED
                status.error, status.bands = None, len(uids)
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
                status.state == FAILED,
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
        (reader_key.h): until then a repair says so, and the list is sent anyway (an unpaired reader
        takes it). Any other refusal is raised."""
        try:
            await self._pair(node)
        except Exception as err:
            text = str(err)
            if PAIRING_BUSY in text:
                # Someone else's pairing request is waiting on it: a tap now would pair it with them. Say so,
                # don't ask for a tap, and ask again after their request has run out.
                self._issue(f"reader_pairing_{device.id}", False, "reader_pairing", {"reader": name})
                self._issue(f"reader_pairing_busy_{device.id}", True, "reader_pairing_busy", {"reader": name})
                self._retry_later()
                return
            if PAIRING_COOLDOWN in text:  # our wait ran out without a tap: asked again in 2 minutes
                self._issue(f"reader_pairing_busy_{device.id}", False, "reader_pairing_busy", {"reader": name})
                self._issue(f"reader_pairing_{device.id}", True, "reader_pairing", {"reader": name})
                self._retry_later()
                return
            if PAIRING_PENDING not in text:
                raise
            self._issue(f"reader_pairing_busy_{device.id}", False, "reader_pairing_busy", {"reader": name})
            self._issue(f"reader_pairing_{device.id}", True, "reader_pairing", {"reader": name})
            return
        self._issue(f"reader_pairing_{device.id}", False, "reader_pairing", {"reader": name})
        self._issue(f"reader_pairing_busy_{device.id}", False, "reader_pairing_busy", {"reader": name})

    def _retry_later(self) -> None:
        if self._retry_at is None:
            self._retry_at = time.monotonic() + PAIRING_RETRY

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
        await self.hass.services.async_call(
            "esphome", _service_for(node, "_unpair"), {"key": self.key}, blocking=True, context=context
        )
        # Stop syncing it, or the next sync would ask to pair it again (and, while that request
        # waits, block the Home Assistant it's moving to).
        self.registry.set_reader_released(device_id, True)
        self._issue(f"reader_pairing_{device_id}", False, "reader_pairing", {})
        self._issue(f"reader_pairing_busy_{device_id}", False, "reader_pairing_busy", {})
        self._issue(f"reader_sync_failed_{device_id}", False, "reader_sync_failed", {})

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
                for issue in (f"reader_offline_{device_id}", f"reader_sync_failed_{device_id}", f"reader_pairing_{device_id}",
                              f"reader_pairing_busy_{device_id}"):
                    ir.async_delete_issue(self.hass, DOMAIN, issue)
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

    # ------------------------------------------------------------------ helpers

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
