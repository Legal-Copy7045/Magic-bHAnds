"""People and bands, stored in Home Assistant's .storage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
import logging
import uuid

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import STORAGE_KEY, STORAGE_VERSION


_LOGGER = logging.getLogger(__name__)

# NFC IDs (ISO 14443-3) are 4, 7 or 10 bytes: 8, 14 or 20 hex digits.
UID_HEX_LENGTHS = (8, 14, 20)
_HEX = frozenset("0123456789ABCDEF")
_SEPARATORS = "-: "
# Bands nobody owns are kept for assigning later; beyond this many, the
# longest-unseen ones are dropped so a stream of made-up tags can't fill the
# registry (and the device list, and the notifications).
MAX_UNASSIGNED_BANDS = 50


def normalize_uid(uid: str) -> str:
    """Lookup key for a band ID: uppercase, separators and anything but ASCII letters/digits removed.

    Use parse_uid to check that a value is a real NFC ID before adding it.
    """
    return "".join(c for c in str(uid).upper() if c.isascii() and c.isalnum())


def parse_uid(value: object) -> str | None:
    """A valid NFC ID in canonical form (04-53-65-2A-C0-5F-80 -> 0453652AC05F80), or None.

    Only hex digits and the separators - : and space are accepted, and the ID
    must be 4, 7 or 10 bytes long, the same rules the reader firmware applies.
    """
    if not isinstance(value, str):
        return None
    key = "".join(c for c in value.strip() if c not in _SEPARATORS).upper()
    if len(key) not in UID_HEX_LENGTHS or not set(key) <= _HEX:
        return None
    return key


def display_uid(uid: str) -> str:
    """Readable band ID: 0453652A -> 04-53-65-2A."""
    uid = normalize_uid(uid)
    return "-".join(uid[i : i + 2] for i in range(0, len(uid), 2))


BAND_TYPES = ("auto", "plus", "classic")


@dataclass
class Person:
    """Someone who can be given bands. Optionally linked to an HA person."""

    id: str
    name: str
    ha_person: str | None = None  # e.g. "person.jackie"
    allowed: bool = True


@dataclass
class Band:
    """A band (or any NFC tag) seen by a reader."""

    uid: str  # normalized
    label: str = ""
    person_id: str | None = None
    first_seen: str | None = None  # ISO timestamps
    last_seen: str | None = None
    last_reader: str | None = None
    scans: int = 0
    band_type: str = "auto"  # BAND_TYPES: auto (not said), plus (MagicBand+), classic (NFC only)

    @property
    def display(self) -> str:
        """Readable ID."""
        return display_uid(self.uid)


@dataclass
class _Data:
    people: dict[str, Person] = field(default_factory=dict)
    bands: dict[str, Band] = field(default_factory=dict)


_BAND_FIELDS = set(Band.__dataclass_fields__)
_PERSON_FIELDS = set(Person.__dataclass_fields__)


class MagicBandRegistry:
    """People, their bands, and which bands are allowed."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data = _Data()
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ storage

    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        if not isinstance(raw, dict):
            raw = {}
        people: dict[str, Person] = {}
        for item in raw.get("people", []) or []:
            try:
                person = Person(**{k: v for k, v in item.items() if k in _PERSON_FIELDS})
                if not isinstance(person.id, str) or not isinstance(person.name, str):
                    raise TypeError("id and name must be text")
            except (AttributeError, TypeError) as err:
                _LOGGER.warning("Skipping a damaged person in the MagicbHAnds store: %s", err)
                continue
            people[person.id] = person
        bands: dict[str, Band] = {}
        for item in raw.get("bands", []) or []:
            try:
                band = Band(**{k: v for k, v in item.items() if k in _BAND_FIELDS})
                if not isinstance(band.uid, str):
                    raise TypeError("uid must be text")
            except (AttributeError, TypeError) as err:
                _LOGGER.warning("Skipping a damaged band in the MagicbHAnds store: %s", err)
                continue
            if parse_uid(band.uid) is None:
                _LOGGER.warning("Band %r isn't a valid NFC ID; it's kept but never allowed in", band.uid)
            bands[band.uid] = band
        self._data = _Data(people=people, bands=bands)

    def _serialize(self) -> dict:
        return {
            "people": [asdict(p) for p in self._data.people.values()],
            "bands": [asdict(b) for b in self._data.bands.values()],
        }

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._serialize, 1.0)

    async def async_flush(self) -> None:
        """Write any pending changes now (on unload/reload)."""
        await self._store.async_save(self._serialize())

    @callback
    def _changed(self, allowed_changed: bool = True) -> None:
        self._save()
        if allowed_changed:
            for listener in list(self._listeners):
                listener()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call `listener` whenever the allowed list may have changed."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    # ------------------------------------------------------------------ queries

    @property
    def people(self) -> list[Person]:
        return sorted(self._data.people.values(), key=lambda p: p.name.lower())

    @property
    def bands(self) -> list[Band]:
        """All bands, most recently seen first."""
        return sorted(self._data.bands.values(), key=lambda b: b.last_seen or "", reverse=True)

    def get_person(self, person_id: str | None) -> Person | None:
        return self._data.people.get(person_id) if person_id else None

    def find_person(self, name_or_id: str) -> Person | None:
        """Look up a person by ID, exact name, or linked HA person entity."""
        if name_or_id in self._data.people:
            return self._data.people[name_or_id]
        for person in self._data.people.values():
            if person.name.lower() == name_or_id.lower() or person.ha_person == name_or_id:
                return person
        return None

    def get_band(self, uid: str) -> Band | None:
        return self._data.bands.get(normalize_uid(uid))

    def bands_for(self, person_id: str) -> list[Band]:
        return [b for b in self.bands if b.person_id == person_id]

    def band_allowed(self, uid: str) -> bool:
        band = self.get_band(uid)
        if band is None or parse_uid(band.uid) is None:
            return False  # only real NFC IDs are ever allowed
        person = self.get_person(band.person_id) if band else None
        return bool(person and person.allowed)

    def allowed_uids(self) -> list[str]:
        return sorted(b.uid for b in self._data.bands.values() if self.band_allowed(b.uid))

    @property
    def unassigned_bands(self) -> list[Band]:
        return [b for b in self.bands if b.person_id is None or b.person_id not in self._data.people]

    @property
    def last_band(self) -> Band | None:
        bands = self.bands
        return bands[0] if bands and bands[0].last_seen else None

    # ------------------------------------------------------------------ changes

    @callback
    def record_scan(self, uid: str, reader: str | None, when: datetime | None = None) -> tuple[Band, bool]:
        """Log a scan of a valid NFC ID (see parse_uid). Returns (band, is_new)."""
        key = parse_uid(uid)
        if key is None:
            raise ValueError(f"{uid!r} isn't a valid band ID")
        now = (when or dt_util.utcnow()).isoformat()
        band = self._data.bands.get(key)
        is_new = band is None
        if band is None:
            band = Band(uid=key, first_seen=now)
            self._data.bands[key] = band
        band.last_seen = now
        band.last_reader = reader
        band.scans += 1
        self._changed(allowed_changed=False)
        return band, is_new

    @callback
    def add_person(self, name: str, ha_person: str | None = None, allowed: bool = True) -> Person:
        name = name.strip()
        if not name:
            raise ValueError("A person needs a name")
        if self.find_person(name):
            raise ValueError(f"There's already a person called {name}")
        person = Person(id=uuid.uuid4().hex[:12], name=name, ha_person=ha_person or None, allowed=allowed)
        self._data.people[person.id] = person
        self._changed()
        return person

    @callback
    def update_person(
        self, person_id: str, *, name: str | None = None, ha_person: str | None = None, allowed: bool | None = None
    ) -> Person:
        person = self._data.people[person_id]
        if name is not None:
            name = name.strip()
            other = self.find_person(name)
            if not name or (other and other.id != person_id):
                raise ValueError(f"There's already a person called {name}" if name else "A person needs a name")
            person.name = name
        if ha_person is not None:
            person.ha_person = ha_person or None
        if allowed is not None:
            person.allowed = allowed
        self._changed()
        return person

    @callback
    def remove_person(self, person_id: str) -> None:
        self._data.people.pop(person_id, None)
        for band in self._data.bands.values():
            if band.person_id == person_id:
                band.person_id = None
        self._changed()

    @callback
    def prune_unassigned(self, limit: int = MAX_UNASSIGNED_BANDS - 1) -> list[str]:
        """Drop the longest-unseen untouched unassigned bands beyond `limit`. Returns their IDs."""
        spare = sorted(
            (
                b
                for b in self._data.bands.values()
                if b.person_id is None and not b.label and b.band_type == "auto"
            ),
            key=lambda b: b.last_seen or b.first_seen or "",
        )
        removed = [b.uid for b in spare[: max(0, len(spare) - limit)]]
        for uid in removed:
            self._data.bands.pop(uid, None)
        if removed:
            _LOGGER.info("Dropped %d old unassigned band(s) to stay under %d", len(removed), MAX_UNASSIGNED_BANDS)
            self._changed(allowed_changed=False)
        return removed

    @callback
    def assign_band(self, uid: str, person_id: str | None, label: str | None = None) -> Band:
        """Give a band to a person (or unassign with person_id=None). Unseen bands are added."""
        key = normalize_uid(uid)
        if not key:
            raise ValueError("Band ID is empty")
        if person_id is not None and person_id not in self._data.people:
            raise ValueError("Unknown person")
        if parse_uid(key) is None and (person_id is not None or key not in self._data.bands):
            raise ValueError(
                f"{uid} isn't a valid band ID (4, 7 or 10 bytes of hex, e.g. 04-53-65-2A-C0-5F-80)"
            )
        band = self._data.bands.setdefault(key, Band(uid=key))
        band.person_id = person_id
        if label is not None:
            band.label = label.strip()
        self._changed()
        return band

    @callback
    def set_band_type(self, uid: str, band_type: str) -> Band:
        """Say whether a band is a MagicBand+ (Bluetooth) or a standard MagicBand (NFC only)."""
        if band_type not in BAND_TYPES:
            raise ValueError(f"Band type must be one of {', '.join(BAND_TYPES)}")
        band = self._data.bands.get(normalize_uid(uid))
        if band is None:
            raise ValueError("Unknown band")
        band.band_type = band_type
        self._changed(allowed_changed=False)
        return band

    @callback
    def remove_band(self, uid: str) -> None:
        self._data.bands.pop(normalize_uid(uid), None)
        self._changed()
