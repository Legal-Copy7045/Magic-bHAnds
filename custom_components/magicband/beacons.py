"""MagicBand+ Bluetooth beacons: which band is which, who owns it, and what it says.

Every MagicBand+ sends a status beacon every few minutes (6-15 seen), on
its own (not in reply to anything), with Disney's company ID (0x0183):

    C0 0F 01 01  LL  B1 B2 B3 B4 B5 B6 B7 B8  00 35 33 00
    C0 13 01 01  LL  B1 B2 B3 B4 B5 B6 B7 B8  00 36 31 00 00 00 00 00

The second byte is the length of what follows (0x0F or 0x13); the longer
form came from a band just switched on. Both are handled the same way.

Worked out from real beacons (see docs/protocol.md, "Band beacons"):

- The Bluetooth address changes with every beacon (a private address), so
  it can't identify a band.
- In B1-B8, the same bit positions change from beacon to beacon in every band
  heard so far (``VARIABLE_BITS``); every other bit never changed. Those
  fixed bits are the band's **signature**: two bands differed in 16 of them,
  while each band's signature stayed identical across 33 beacons.
- ``LL`` is the **battery level** in percent, in steps (5, 15, 50, 60, 72,
  80, 98, 100 seen): it fell over a day and rose when the bands were charged.
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
import re
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEFAULT_BATTERY_LEVEL, DOMAIN, EVENT_BEACON, SIGNAL_BEACON, SIGNAL_BEACON_NEW

EVENT_BATTERY_LOW = "magicband_battery_low"
# A band counts as charged again this far above the reminder level (levels come in steps).
BATTERY_RECOVER_MARGIN = 10
from .registry import MagicBandRegistry, normalize_uid

_LOGGER = logging.getLogger(__name__)

STORE_KEY = "magicband.bluetooth"
STORE_VERSION = 1

BEACON_TYPE = 0xC0
MIN_BEACON_LEN = 13  # C0 LL 01 01, level, B1-B8
# Bits of B1-B8 that changed between beacons from the same band.
VARIABLE_BITS = bytes.fromhex("8342 40C0 8C04 104A")
SIGNATURE_MASK = bytes(~b & 0xFF for b in VARIABLE_BITS)
# A beacon belongs to a known band if its signature differs in at most this
# many bits (0 in practice; the margin covers bits not yet seen changing).
MATCH_BITS = 4
ENCRYPTED_PREFIX = bytes.fromhex("0F1101")

AWAY_AFTER = timedelta(minutes=35)  # two missed beacons
CLOSEST_WINDOW = timedelta(minutes=20)  # beacons that count towards "closest"
PAIRING_WINDOW = timedelta(minutes=20)  # covers at least one beacon
CLEAR_WINNER_DB = 10
SAMPLES = 50
LEVEL_HISTORY = 100
# Bluetooth bands nobody has claimed (not linked to an NFC band, not given to
# a person). Anyone can broadcast made-up beacons, so these are capped: when
# full, the longest-unheard one is dropped if it's been away a while, and
# otherwise new signatures are ignored until there's room.
MAX_UNCLAIMED = 25
MAX_FORMS = 8
MAX_PAIRING_WINDOWS = 10
# A band beacons every few minutes. The same beacon is usually heard by
# several adapters/proxies at once, so the limit is per band and per adapter:
# anything more often is a replay (or a flood) and is ignored.
MIN_BEACON_INTERVAL = timedelta(seconds=30)


@dataclass
class Beacon:
    """One decoded status beacon."""

    level: int
    body: bytes
    signature: bytes
    tail: bytes
    form: str  # "C0 0F", "C0 13"


def parse(payload: bytes) -> Beacon | None:
    """Decode a status beacon (C0 <length> 01 01 ...), or None if it isn't one."""
    if (
        len(payload) < MIN_BEACON_LEN
        or payload[0] != BEACON_TYPE
        or payload[1] != len(payload) - 2
        or payload[2:4] != b"\x01\x01"
    ):
        return None
    body = payload[5:13]
    return Beacon(
        level=payload[4],
        body=body,
        signature=bytes(b & m for b, m in zip(body, SIGNATURE_MASK)),
        tail=payload[13:],
        form=f"C0 {payload[1]:02X}",
    )


_MAC_IN_NAME = re.compile(r"\s*\(([0-9A-Fa-f:]{17})\)\s*$")


def find_device(
    hass: HomeAssistant,
    identifiers: set[tuple[str, str]] | None = None,
    connections: set[tuple[str, str]] | None = None,
) -> dr.DeviceEntry | None:
    """A device with any of these identifiers or connections.

    Searches the device registry's entries directly rather than calling
    DeviceRegistry.async_get_device, which Home Assistant has deprecated.
    """
    want_ids = set(identifiers or ())
    want_conn = {(t, v.lower()) for t, v in (connections or ())}
    for device in dr.async_get(hass).devices.values():
        if want_ids & device.identifiers:
            return device
        if want_conn and want_conn & {(t, v.lower()) for t, v in device.connections}:
            return device
    return None


def _shift_mac(address: str, offset: int) -> str | None:
    try:
        value = int(address.replace(":", ""), 16) + offset
    except ValueError:
        return None
    if not 0 <= value < 1 << 48:
        return None
    raw = f"{value:012x}"
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def adapter_name(hass: HomeAssistant, source: str | None) -> str | None:
    """A friendly name for a Bluetooth adapter or proxy ("Kitchen MagicBand Bridge").

    `source` is the scanner's address (or an older "name (address)" string).
    Uses the name of its device in Home Assistant, including any rename,
    looked up in the device registry only (never other integrations'
    settings):

    - a local adapter (USB dongle) has a device with its Bluetooth address;
    - an ESPHome proxy's device carries its Wi-Fi MAC, and an ESP32's
      Bluetooth address is its base MAC + 2 (Ethernet boards: + 3), so the
      device is found by stepping the address back.
    """
    if not source:
        return None
    m = _MAC_IN_NAME.search(source)
    address = (m.group(1) if m else source).upper()
    device = find_device(hass, connections={(dr.CONNECTION_BLUETOOTH, address)})
    if device is None:
        for offset in (-2, -3, -1):
            mac = _shift_mac(address, offset)
            if mac and (device := find_device(hass, connections={(dr.CONNECTION_NETWORK_MAC, mac)})):
                break
    if device is not None:
        name = device.name_by_user or device.name or source
        return _MAC_IN_NAME.sub("", name).removeprefix("Unknown ").strip()
    try:
        from homeassistant.components import bluetooth

        scanner = bluetooth.async_scanner_by_source(hass, address)
        if scanner is not None and getattr(scanner, "name", None):
            return _MAC_IN_NAME.sub("", scanner.name).strip()
    except Exception:  # noqa: BLE001 - the name is cosmetic
        pass
    return _MAC_IN_NAME.sub("", source).strip() or source


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
    heard: dict[str, list] = field(default_factory=dict)  # source -> [rssi, iso time]
    forms: list[str] = field(default_factory=list)  # beacon forms seen, e.g. "C0 0F"
    level_history: list[list] = field(default_factory=list)  # [iso time, level]
    samples: list[list] = field(default_factory=list)  # [iso time, payload hex, rssi, source]
    battery_low: bool = False  # a reminder was sent and the band hasn't been charged since

    @property
    def short(self) -> str:
        return self.id[:4].upper()

    @property
    def battery(self) -> int | None:
        return battery_from_level(self.level)

    def closest(self, now: datetime | None = None) -> tuple[str | None, int | None]:
        """The adapter that heard this band strongest in the last 20 minutes."""
        now = now or dt_util.utcnow()
        recent = [
            (rssi, source)
            for source, (rssi, when) in self.heard.items()
            if (seen := dt_util.parse_datetime(when)) is not None and now - seen <= CLOSEST_WINDOW
        ]
        if not recent:
            return None, None
        rssi, source = max(recent)
        return source, rssi

    def nearby(self, now: datetime | None = None) -> bool:
        seen = dt_util.parse_datetime(self.last_seen)
        return seen is not None and (now or dt_util.utcnow()) - seen <= AWAY_AFTER

    def variable_bits(self) -> str:
        """Bits of B1-B8 seen changing in this band's samples, as hex."""
        bodies = [b.body for s in self.samples if (b := parse(bytes.fromhex(s[1]))) is not None]
        if not bodies:
            return ""
        acc = bytearray(8)
        for b in bodies[1:]:
            for i in range(8):
                acc[i] |= b[i] ^ bodies[0][i]
        return acc.hex(" ").upper()


_BAND_FIELDS = set(BluetoothBand.__dataclass_fields__)


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
        self._full_warned: datetime | None = None
        self.battery_low_level: int = DEFAULT_BATTERY_LEVEL  # 0 = no reminders

    # ------------------------------------------------------------------ storage

    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        if not isinstance(raw, dict):
            raw = {}
        self.bands = {}
        for item in raw.get("bands", []) or []:
            try:
                band = BluetoothBand(**{k: v for k, v in item.items() if k in _BAND_FIELDS})
                bytes.fromhex(band.id)
            except (AttributeError, TypeError, ValueError) as err:
                _LOGGER.warning("Skipping a damaged Bluetooth band in the MagicbHAnds store: %s", err)
                continue
            self.bands[band.id] = band
        encrypted = raw.get("encrypted", [])
        self.encrypted = encrypted[:SAMPLES] if isinstance(encrypted, list) else []
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

    def linked_nfc(self, band: BluetoothBand):
        """The NFC band this Bluetooth band is linked to, if it still exists."""
        return self.registry.get_band(band.band_uid) if band.band_uid else None

    def owner(self, band: BluetoothBand):
        """(person, NFC band) for a Bluetooth band; either may be None."""
        nfc = self.linked_nfc(band)
        person_id = nfc.person_id if nfc else band.person_id
        return self.registry.get_person(person_id), nfc

    def name(self, band: BluetoothBand) -> str:
        """The name the integration gives the band's device (before any rename)."""
        return self.band_name(self.linked_nfc(band), band)

    def device_key(self, band: BluetoothBand) -> str:
        """Identifier of the device the band's entities are on (see band_entity.py)."""
        nfc = self.linked_nfc(band)
        return f"band_{nfc.uid}" if nfc is not None else f"bluetooth_{band.id}"

    def display_name(self, band: BluetoothBand) -> str:
        """The band's name as shown in Home Assistant, including a rename of its device."""
        device = find_device(self.hass, identifiers={(DOMAIN, self.device_key(band))})
        if device is not None and device.name_by_user:
            return device.name_by_user
        return self.name(band)

    def band_display_name(self, uid: str) -> str:
        """A band's name as shown in Home Assistant, by its NFC ID."""
        nfc = self.registry.get_band(uid)
        if nfc is None:
            return uid
        return self.nfc_display_name(nfc) or self.band_name(nfc, self.for_nfc(nfc.uid))

    def nfc_display_name(self, nfc) -> str | None:
        """A renamed NFC band device's name, if it has one."""
        device = find_device(self.hass, identifiers={(DOMAIN, f"band_{nfc.uid}")})
        return device.name_by_user if device is not None and device.name_by_user else None

    def band_name(self, nfc, ble: BluetoothBand | None) -> str:
        """The name of one physical band: its NFC side, its Bluetooth side, or both."""
        if nfc is not None and nfc.label:
            return nfc.label
        kind = "MagicBand+" if ble is not None else "MagicBand"
        short = ble.short if ble is not None else nfc.uid[-4:]
        person = self.registry.get_person(nfc.person_id if nfc is not None else ble.person_id)
        if person is None:
            return f"{kind} {short}"
        # Count this person's physical bands: NFC bands, plus Bluetooth bands not linked to one.
        count = len(self.registry.bands_for(person.id)) + sum(
            1 for b in self.bands.values() if b.person_id == person.id and self.linked_nfc(b) is None
        )
        return f"{person.name}'s {kind}" + (f" {short}" if count > 1 else "")

    def find(self, value: str) -> BluetoothBand | None:
        """By ID (or its first characters), name, or 'last'."""
        value = value.strip()
        if value.lower() == "last":
            return max(self.bands.values(), key=lambda b: b.last_seen, default=None)
        lower = value.lower()
        for band in self.bands.values():
            if band.id == lower or lower in (self.name(band).lower(), self.display_name(band).lower()):
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
        if band is not None and (last := band.heard.get(source)):
            seen = dt_util.parse_datetime(last[1]) if isinstance(last, list) and len(last) > 1 else None
            if seen is not None and dt_util.utcnow() - seen < MIN_BEACON_INTERVAL:
                return band  # heard from this adapter moments ago
        is_new = band is None
        if band is None:
            if not self._make_room():
                return None
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
        band.heard[source] = [rssi, now]
        if beacon.form not in band.forms:
            band.forms = [*band.forms, beacon.form][-MAX_FORMS:]
        if beacon.level != band.level:
            band.level_history = [*band.level_history, [now, beacon.level]][-LEVEL_HISTORY:]
            band.level = beacon.level
        self._check_battery(band)
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
                "name": self.display_name(band),
                "person": person.name if person else None,
                "band": nfc.display if nfc else None,
                "battery": band.battery,
                "level": band.level,
                "rssi": rssi,
                "heard_by": adapter_name(self.hass, source),
                "new": is_new,
            },
        )
        if is_new:
            async_dispatcher_send(self.hass, SIGNAL_BEACON_NEW)
        async_dispatcher_send(self.hass, SIGNAL_BEACON)
        return band

    @callback
    def _check_battery(self, band: BluetoothBand) -> None:
        """Remind once when a band's battery drops to the reminder level; clear it once it's charged."""
        battery, level = band.battery, self.battery_low_level
        issue_id = f"battery_low_{band.id}"
        if battery is None or not level:
            if band.battery_low:
                band.battery_low = False
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        if battery <= level and not band.battery_low:
            band.battery_low = True
            person, _ = self.owner(band)
            name = self.display_name(band)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="battery_low",
                translation_placeholders={"band": name, "battery": str(battery)},
            )
            self.hass.bus.async_fire(
                EVENT_BATTERY_LOW,
                {"bluetooth_band": band.id, "name": name, "person": person.name if person else None, "battery": battery},
            )
            _LOGGER.info("%s needs charging (%d%%)", name, battery)
        elif battery >= level + BATTERY_RECOVER_MARGIN and band.battery_low:
            band.battery_low = False
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _unclaimed(self) -> list[BluetoothBand]:
        """Bands nobody owns: not given to a person, and not linked to an NFC band that has an owner.

        A band linked automatically to a tag nobody owns still counts, so tapping
        made-up tags can't lift bands out of the cap.
        """
        return [b for b in self.bands.values() if self.owner(b)[0] is None]

    @callback
    def unlink_nfc(self, uid: str) -> None:
        """An NFC band was removed: drop links to it."""
        key = normalize_uid(uid)
        changed = False
        for band in self.bands.values():
            if band.band_uid == key:
                band.band_uid = None
                changed = True
        if changed:
            self._save()
            async_dispatcher_send(self.hass, SIGNAL_BEACON)

    def _make_room(self) -> bool:
        """Whether a new Bluetooth band may be added (dropping a long-unheard unclaimed one if needed)."""
        unclaimed = self._unclaimed()
        if len(unclaimed) < MAX_UNCLAIMED:
            return True
        stalest = min(unclaimed, key=lambda b: b.last_seen)
        if stalest.nearby():
            now = dt_util.utcnow()
            if self._full_warned is None or now - self._full_warned > timedelta(hours=1):
                self._full_warned = now
                _LOGGER.warning(
                    "%d unclaimed Bluetooth bands are being heard; ignoring new ones until one goes away. "
                    "Link or give them to people, or forget ones that aren't yours",
                    MAX_UNCLAIMED,
                )
            return False
        _LOGGER.info("Forgetting unclaimed Bluetooth band %s (not heard since %s) to make room", stalest.short, stalest.last_seen)
        self.forget(stalest)
        return True

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
        """Link to an NFC band (taking its owner) or give to a person; both None = unlink.

        Linking: the NFC band's owner wins. If the NFC band has no owner yet,
        the Bluetooth band's person becomes its owner, so linking never drops
        who a band belongs to (and the readers' allowed list follows).
        """
        if nfc_uid is not None:
            key = normalize_uid(nfc_uid)
            nfc = self.registry.get_band(key)
            if nfc is not None and nfc.band_type == "classic":
                self.registry.set_band_type(key, "plus")  # it's been heard over Bluetooth, so it is one
            if nfc is not None and nfc.person_id is None and band.person_id is not None:
                self.registry.assign_band(key, band.person_id)
                persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_unknown_{key}")
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
        ir.async_delete_issue(self.hass, DOMAIN, f"battery_low_{band.id}")
        self._save()
        async_dispatcher_send(self.hass, SIGNAL_BEACON_NEW)

    # ------------------------------------------------------------------ pairing with NFC

    @callback
    def async_start_pairing(self, uid: str, reader: str | None) -> bool:
        """A band was tapped: watch for its beacon if it isn't linked yet."""
        key = normalize_uid(uid)
        if self.for_nfc(key) is not None or not self._unlinked() or self.band_type(key) == "classic":
            return False
        old = self._windows.pop(key, None)
        if old and old.cancel:
            old.cancel()
        while len(self._windows) >= MAX_PAIRING_WINDOWS:  # oldest tap first
            stale = self._windows.pop(next(iter(self._windows)))
            if stale.cancel:
                stale.cancel()
        window = _Window(uid=key, reader=reader)
        @callback
        def _done(_now: datetime) -> None:
            self._finish_pairing(key)

        window.cancel = async_call_later(self.hass, PAIRING_WINDOW.total_seconds(), _done)
        self._windows[key] = window
        _LOGGER.debug("Watching for the Bluetooth beacon of band %s", key)
        return True

    def band_type(self, uid: str) -> str:
        """What a tapped band is: plus, classic, or unknown (not said and never heard over Bluetooth)."""
        nfc = self.registry.get_band(uid)
        if nfc is not None and nfc.band_type in ("plus", "classic"):
            return nfc.band_type
        return "plus" if self.for_nfc(uid) is not None else "unknown"

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
        if chosen is not None and chosen.person_id is not None and (nfc is None or nfc.person_id != chosen.person_id):
            # Linking would give the NFC band the Bluetooth band's owner, i.e. let a tag in that nobody
            # approved. Anyone can tap a tag and broadcast a beacon, so that's never done automatically.
            owner = self.registry.get_person(chosen.person_id)
            persistent_notification.async_create(
                self.hass,
                (
                    f"After **{display}** was tapped, only **{self.display_name(chosen)}** was heard over "
                    f"Bluetooth. It belongs to {owner.name if owner else 'someone'}, so linking it would "
                    "let this NFC band in as theirs. It wasn't linked automatically.\n\n"
                    "If it is the same band, link it by hand: **Settings → Devices & services → MagicbHAnds → "
                    "Configure → Link a band's Bluetooth**."
                ),
                title="MagicbHAnds: confirm this band",
                notification_id=f"{DOMAIN}_pair_{key}",
            )
            _LOGGER.warning("Not linking band %s to %s's Bluetooth band %s automatically", display,
                            owner.name if owner else "someone", chosen.short)
            return
        if chosen is not None:
            self.link(chosen, nfc_uid=key)
            _LOGGER.info("Linked band %s to Bluetooth band %s", display, chosen.short)
            persistent_notification.async_create(
                self.hass,
                (
                    f"**{display}** was linked to the MagicBand+ heard over Bluetooth "
                    f"(**{self.display_name(chosen)}**) after it was tapped. If that's the wrong band, "
                    "unlink it under **Settings → Devices & services → MagicbHAnds → Configure**."
                ),
                title="MagicbHAnds: band linked",
                notification_id=f"{DOMAIN}_pair_{key}",
            )
            return
        if not window.candidates:
            _LOGGER.info("No unlinked Bluetooth band heard within %s of tapping %s", PAIRING_WINDOW, display)
            return
        names = ", ".join(self.display_name(self.bands[i]) for i in window.candidates if i in self.bands)
        persistent_notification.async_create(
            self.hass,
            (
                f"After **{display}** was tapped, more than one unlinked MagicBand+ was heard over "
                f"Bluetooth ({names}), so it couldn't tell which is this band.\n\n"
                "Tap it again with the other bands out of range (or in a metal tin), or link it by hand: "
                "**Settings → Devices & services → MagicbHAnds → Configure → Link a band's Bluetooth**."
            ),
            title="MagicbHAnds: which Bluetooth band?",
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
            "name": self.display_name(band),
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
            "heard_by": adapter_name(self.hass, band.last_source),
            "closest": adapter_name(self.hass, band.closest()[0]),
            "rssi_by_source": {adapter_name(self.hass, s) or s: r for s, r in band.rssi_by_source.items()},
            "variable_bits": band.variable_bits(),
            "forms": band.forms,
            "samples": band.samples,
        }

    def report(self) -> dict[str, Any]:
        return {
            "bluetooth_bands": [self.as_dict(b) for b in sorted(self.bands.values(), key=lambda b: b.first_seen)],
            "encrypted_messages": self.encrypted,
            "pairing": [{"band": w.uid, "reader": w.reader, "candidates": list(w.candidates)} for w in self._windows.values()],
        }
