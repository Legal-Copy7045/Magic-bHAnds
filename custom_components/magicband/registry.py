"""People and bands, stored in Home Assistant's .storage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
import uuid

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import STORAGE_KEY, STORAGE_VERSION


def normalize_uid(uid: str) -> str:
    """Canonical band ID: uppercase hex digits, no separators (04-53-65 -> 045365)."""
    return "".join(c for c in uid.upper() if c.isalnum())


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
        self._data = _Data(
            people={p["id"]: Person(**p) for p in raw.get("people", [])},
            bands={b["uid"]: Band(**{k: v for k, v in b.items() if k in _BAND_FIELDS}) for b in raw.get("bands", [])},
        )

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
        """Log a scan. Returns (band, is_new)."""
        key = normalize_uid(uid)
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
    def assign_band(self, uid: str, person_id: str | None, label: str | None = None) -> Band:
        """Give a band to a person (or unassign with person_id=None). Unseen bands are added."""
        key = normalize_uid(uid)
        if not key:
            raise ValueError("Band ID is empty")
        if person_id is not None and person_id not in self._data.people:
            raise ValueError("Unknown person")
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
