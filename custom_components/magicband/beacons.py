"""MagicBand+ Bluetooth beacons: which band is which, who owns it, and what it says.

Every MagicBand+ sends a status beacon about every 15 minutes, on its own
(not in reply to anything), with Disney's company ID (0x0183):

    C0 0F 01 01  LL  B1 B2 B3 B4 B5 B6 B7 B8  00 35 33 00

Worked out from real beacons (see docs/protocol.md, "Band beacons"):

- The Bluetooth address changes with every beacon (a private address), so
  it can't identify a band.
- In B1-B8, the same bit positions change from beacon to beacon in every band
  heard so far (``VARIABLE_BITS``); every other bit never changed. Those
  fixed bits are the band's **signature**: two bands differed in 16 of them,
  while each band's signature stayed identical across 33 beacons.
- ``LL`` only ever went down, in round decimal steps (100, 98, 80, 72, 50):
  probably the battery level in percent. *Unconfirmed*: a fully charged band
  going back to 100 would confirm it.
- A second message type, ``0F 11 01 ...`` (19 bytes), looks encrypted. It's
  counted but not decoded.

A band heard here becomes a "Bluetooth band" with its own device in Home
Assistant (nearby, last seen, signal, battery). It can be given to a person
directly, or linked to the band's NFC ID: either automatically, when a band
is tapped on a reader and exactly one unlinked band is heard in the next
20 minutes, or by hand.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_BEACON, SIGNAL_BEACON, SIGNAL_BEACON_NEW
from .registry import MagicBandRegistry, normalize_uid

_LOGGER = logging.getLogger(__name__)

STORE_KEY = "magicband.bluetooth"
STORE_VERSION = 1

PREFIX = bytes.fromhex("C00F0101")
BEACON_LEN = 17
# Bits of B1-B8 that changed between beacons from the same band.
VARIABLE_BITS = bytes.fromhex("8342 40C0 8C04 104A")
SIGNATURE_MASK = bytes(~b & 0xFF for b in VARIABLE_BITS)
# A beacon belongs to a known band if its signature differs in at most this
# many bits (0 in practice; the margin covers bits not yet seen changing).
MATCH_BITS = 4
ENCRYPTED_PREFIX = bytes.fromhex("0F1101")

AWAY_AFTER = timedelta(minutes=35)  # two missed beacons
PAIRING_WINDOW = timedelta(minutes=20)  # covers at least one beacon
CLEAR_WINNER_DB = 10
SAMPLES = 50
LEVEL_HISTORY = 100


@dataclass
class Beacon:
    """One decoded status beacon."""

    level: int
    body: bytes
    signature: bytes
    tail: bytes


def parse(payload: bytes) -> Beacon | None:
    """Decode a status beacon, or None if it isn't one."""
    if len(payload) != BEACON_LEN or not payload.startswith(PREFIX):
        return None
    body = payload[5:13]
    return Beacon(
        level=payload[4],
        body=body,
        signature=bytes(b & m for b, m in zip(body, SIGNATURE_MASK)),
        tail=payload[13:],
    )


def bit_distance(a: bytes, b: bytes) -> int:
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))


def battery_from_level(level: int | None) -> int | None:
    """The level byte as a percentage, if it looks like one."""
    return level if level is not None and 0 <= level <= 100 else None


@dataclass
class BluetoothBand:
    """A MagicBand+ recognised by its beacon signature."""

    id: str  # the signature, hex
    first_seen: str
    last_seen: str
    beacons: int = 0
    band_uid: str | None = None  # linked NFC band
    person_id: str | None = None  # owner, when not linked to an NFC band
    level: int | None = None
    last_rssi: int | None = None
    last_source: str | None = None
    last_address: str | None = None
    last_payload: str | None = None
    rssi_by_source: dict[str, int] = field(default_factory=dict)
    level_history: list[list] = field(default_factory=list)  # [iso time, level]
    samples: list[list] = field(default_factory=list)  # [iso time, payload hex, rssi, source]

    @property
    def short(self) -> str:
        return self.id[:4].upper()

    @property
    def battery(self) -> int | None:
        return battery_from_level(self.level)

    def nearby(self, now: datetime | None = None) -> bool:
        seen = dt_util.parse_datetime(self.last_seen)
        return seen is not None and (now or dt_util.utcnow()) - seen <= AWAY_AFTER

    def variable_bits(self) -> str:
        """Bits of B1-B8 seen changing in this band's samples, as hex."""
        bodies = [bytes.fromhex(s[1])[5:13] for s in self.samples if len(bytes.fromhex(s[1])) == BEACON_LEN]
        if not bodies:
            return ""
        acc = bytearray(8)
        for b in bodies[1:]:
            for i in range(8):
                acc[i] |= b[i] ^ bodies[0][i]
        return acc.hex(" ").upper()


@dataclass
class _Window:
    uid: str
    reader: str | None
    candidates: dict[str, int] = field(default_factory=dict)  # band id -> best RSSI
    cancel: Callable[[], None] | None = None


class BeaconTracker:
    """Recognises bands from their beacons, tracks them and pairs them with NFC IDs."""

    def __init__(self, hass: HomeAssistant, registry: MagicBandRegistry) -> None:
        self.hass = hass
        self.registry = registry
        self._store: Store[dict] = Store(hass, STORE_VERSION, STORE_KEY)
        self.bands: dict[str, BluetoothBand] = {}
        self.encrypted: list[list] = []  # [iso time, payload hex, rssi, source]
        self._windows: dict[str, _Window] = {}
        self._unsubs: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ storage

    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        self.bands = {b["id"]: BluetoothBand(**b) for b in raw.get("bands", [])}
        self.encrypted = raw.get("encrypted", [])
        # Presence goes stale without beacons: re-check every minute.
        @callback
        def _tick(_now: datetime) -> None:
            async_dispatcher_send(self.hass, SIGNAL_BEACON)

        self._unsubs.append(async_track_time_interval(self.hass, _tick, timedelta(minutes=1)))

    def _serialize(self) -> dict:
        return {"bands": [asdict(b) for b in self.bands.values()], "encrypted": self.encrypted}

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._serialize, 10.0)

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        for window in self._windows.values():
            if window.cancel:
                window.cancel()
        self._windows.clear()
        await self._store.async_save(self._serialize())

    # ------------------------------------------------------------------ owners

    def owner(self, band: BluetoothBand):
        """(person, NFC band) for a Bluetooth band; either may be None."""
        nfc = self.registry.get_band(band.band_uid) if band.band_uid else None
        person_id = nfc.person_id if nfc else band.person_id
        return self.registry.get_person(person_id), nfc

    def name(self, band: BluetoothBand) -> str:
        person, nfc = self.owner(band)
        if nfc and nfc.label:
            return nfc.label
        if person:
            others = [b for b in self.bands.values() if b is not band and self.owner(b)[0] is person]
            return f"{person.name}'s MagicBand+" + (f" {band.short}" if others else "")
        return f"MagicBand+ {band.short}"

    def find(self, value: str) -> BluetoothBand | None:
        """By ID (or its first characters), name, or 'last'."""
        value = value.strip()
        if value.lower() == "last":
            return max(self.bands.values(), key=lambda b: b.last_seen, default=None)
        lower = value.lower()
        for band in self.bands.values():
            if band.id == lower or self.name(band).lower() == lower:
                return band
        matches = [b for b in self.bands.values() if b.id.startswith(lower)] if len(lower) >= 4 else []
        return matches[0] if len(matches) == 1 else None

    def for_nfc(self, uid: str) -> BluetoothBand | None:
        key = normalize_uid(uid)
        return next((b for b in self.bands.values() if b.band_uid == key), None)

    # ------------------------------------------------------------------ beacons

    @callback
    def async_beacon(self, address: str, rssi: int, source: str, payload: bytes) -> BluetoothBand | None:
        """Handle a band message from the listener. Returns the band, if recognised."""
        now = dt_util.utcnow().isoformat()
        if payload.startswith(ENCRYPTED_PREFIX):
            self.encrypted = [[now, payload.hex(" ").upper(), rssi, source], *self.encrypted][:SAMPLES]
            self._save()
            return None
        beacon = parse(payload)
        if beacon is None:
            return None

        band = self._match(beacon.signature)
        is_new = band is None
        if band is None:
            band = BluetoothBand(id=beacon.signature.hex(), first_seen=now, last_seen=now)
            self.bands[band.id] = band
            _LOGGER.info("New MagicBand+ heard over Bluetooth: %s", band.short)

        band.last_seen = now
        band.beacons += 1
        band.last_rssi = rssi
        band.last_source = source
        band.last_address = address
        band.last_payload = payload.hex(" ").upper()
        band.rssi_by_source[source] = rssi
        if beacon.level != band.level:
            band.level_history = [*band.level_history, [now, beacon.level]][-LEVEL_HISTORY:]
            band.level = beacon.level
        band.samples = [[now, band.last_payload, rssi, source], *band.samples][:SAMPLES]

        if band.band_uid is None:
            for window in self._windows.values():
                window.candidates[band.id] = max(rssi, window.candidates.get(band.id, -999))

        self._save()
        person, nfc = self.owner(band)
        self.hass.bus.async_fire(
            EVENT_BEACON,
            {
                "bluetooth_band": band.id,
                "name": self.name(band),
                "person": person.name if person else None,
                "band": nfc.display if nfc else None,
                "battery": band.battery,
                "level": band.level,
                "rssi": rssi,
                "heard_by": source,
                "new": is_new,
            },
        )
        if is_new:
            async_dispatcher_send(self.hass, SIGNAL_BEACON_NEW)
        async_dispatcher_send(self.hass, SIGNAL_BEACON)
        return band

    def _match(self, signature: bytes) -> BluetoothBand | None:
        best, best_d = None, MATCH_BITS + 1
        for band in self.bands.values():
            d = bit_distance(signature, bytes.fromhex(band.id))
            if d < best_d:
                best, best_d = band, d
        return best

    # ------------------------------------------------------------------ linking

    @callback
    def link(self, band: BluetoothBand, *, nfc_uid: str | None = None, person_id: str | None = None) -> None:
        """Link to an NFC band (taking its owner) or give to a person; both None = unlink."""
        if nfc_uid is not None:
            key = normalize_uid(nfc_uid)
            for other in self.bands.values():
                if other is not band and other.band_uid == key:
                    other.band_uid = None
            band.band_uid = key
            band.person_id = None
            window = self._windows.pop(key, None)
            if window and window.cancel:
                window.cancel()
            persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_pair_{key}")
        else:
            band.band_uid = None
            band.person_id = person_id
        self._save()
        async_dispatcher_send(self.hass, SIGNAL_BEACON)

    @callback
    def forget(self, band: BluetoothBand) -> None:
        self.bands.pop(band.id, None)
        self._save()
        async_dispatcher_send(self.hass, SIGNAL_BEACON_NEW)

    # ------------------------------------------------------------------ pairing with NFC

    @callback
    def async_start_pairing(self, uid: str, reader: str | None) -> bool:
        """A band was tapped: watch for its beacon if it isn't linked yet."""
        key = normalize_uid(uid)
        if self.for_nfc(key) is not None or not self._unlinked():
            return False
        old = self._windows.pop(key, None)
        if old and old.cancel:
            old.cancel()
        window = _Window(uid=key, reader=reader)
        @callback
        def _done(_now: datetime) -> None:
            self._finish_pairing(key)

        window.cancel = async_call_later(self.hass, PAIRING_WINDOW.total_seconds(), _done)
        self._windows[key] = window
        _LOGGER.debug("Watching for the Bluetooth beacon of band %s", key)
        return True

    def _unlinked(self) -> list[BluetoothBand]:
        return [b for b in self.bands.values() if b.band_uid is None]

    @callback
    def _finish_pairing(self, key: str) -> None:
        window = self._windows.pop(key, None)
        if window is None or self.for_nfc(key) is not None:
            return
        chosen = self.choose(key, window.candidates)
        nfc = self.registry.get_band(key)
        display = nfc.display if nfc else key
        if chosen is not None:
            self.link(chosen, nfc_uid=key)
            _LOGGER.info("Linked band %s to Bluetooth band %s", display, chosen.short)
            return
        if not window.candidates:
            _LOGGER.info("No unlinked Bluetooth band heard within %s of tapping %s", PAIRING_WINDOW, display)
            return
        names = ", ".join(self.name(self.bands[i]) for i in window.candidates if i in self.bands)
        persistent_notification.async_create(
            self.hass,
            (
                f"After **{display}** was tapped, more than one unlinked MagicBand+ was heard over "
                f"Bluetooth ({names}), so it couldn't tell which is this band.\n\n"
                "Tap it again with the other bands out of range (or in a metal tin), or link it by hand: "
                "**Settings → Devices & services → MagicBand → Configure → Link a band's Bluetooth**."
            ),
            title="MagicBand: which Bluetooth band?",
            notification_id=f"{DOMAIN}_pair_{key}",
        )

    def choose(self, key: str, candidates: dict[str, int]) -> BluetoothBand | None:
        """Pick the Bluetooth band for a tapped NFC band, if it's clear which one."""
        options = [self.bands[i] for i in candidates if i in self.bands and self.bands[i].band_uid is None]
        if len(options) == 1:
            return options[0]
        if not options:
            return None
        # Already given to the same person as the NFC band?
        nfc = self.registry.get_band(key)
        if nfc and nfc.person_id:
            same = [b for b in options if b.person_id == nfc.person_id]
            if len(same) == 1:
                return same[0]
        # One much closer than the rest?
        ranked = sorted(options, key=lambda b: candidates[b.id], reverse=True)
        if candidates[ranked[0].id] - candidates[ranked[1].id] >= CLEAR_WINNER_DB:
            return ranked[0]
        return None

    # ------------------------------------------------------------------ reporting

    def as_dict(self, band: BluetoothBand) -> dict[str, Any]:
        person, nfc = self.owner(band)
        return {
            "id": band.id,
            "name": self.name(band),
            "person": person.name if person else None,
            "band": nfc.display if nfc else None,
            "nearby": band.nearby(),
            "first_seen": band.first_seen,
            "last_seen": band.last_seen,
            "beacons": band.beacons,
            "battery": band.battery,
            "level": band.level,
            "level_history": band.level_history,
            "rssi": band.last_rssi,
            "heard_by": band.last_source,
            "rssi_by_source": band.rssi_by_source,
            "variable_bits": band.variable_bits(),
            "samples": band.samples,
        }

    def report(self) -> dict[str, Any]:
        return {
            "bluetooth_bands": [self.as_dict(b) for b in sorted(self.bands.values(), key=lambda b: b.first_seen)],
            "encrypted_messages": self.encrypted,
            "pairing": [{"band": w.uid, "reader": w.reader, "candidates": list(w.candidates)} for w in self._windows.values()],
        }
