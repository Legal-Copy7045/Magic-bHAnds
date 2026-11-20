"""People and bands, stored in Home Assistant's .storage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, time
import logging
import uuid

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import READER_COLOURS, STORAGE_KEY, STORAGE_VERSION, WEEKDAYS


_LOGGER = logging.getLogger(__name__)

# NFC IDs (ISO 14443-3) are 4, 7 or 10 bytes: 8, 14 or 20 hex digits.
UID_HEX_LENGTHS = (8, 14, 20)
_HEX = frozenset("0123456789ABCDEF")
_SEPARATORS = "-: "
# Bands nobody owns are kept for assigning later; beyond this many, the
# longest-unseen ones are dropped so a stream of made-up tags can't fill the
# registry (and the device list, and the notifications).
MAX_UNASSIGNED_BANDS = 100


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
    ha_person: str | None = None  # e.g. "person.morgan"
    allowed: bool = True
    welcome_colour: str | None = None  # one of READER_COLOURS: the readers welcome this person's bands in it
    birthday: str | None = None  # "MM-DD": their taps get the Birthday show that day
    lockdown_exempt: bool = False  # still let in while the house is in lockdown
    # A guest pass (guest=True): when this person's bands work, on top of each band's own limits. All optional.
    guest: bool = False
    valid_from: str | None = None  # ISO date-time; not allowed before
    valid_until: str | None = None  # ISO date-time; not allowed from then on
    uses_left: int | None = None  # welcomed taps left (None = no limit); each welcome uses one
    access_from: str | None = None  # "HH:MM", a daily window (as for bands)
    access_until: str | None = None
    access_days: list[str] | None = None

    @property
    def has_pass(self) -> bool:
        return any((self.valid_from, self.valid_until, self.uses_left is not None, self.access_from,
                    self.access_until, self.access_days))

    def in_pass(self, now: datetime) -> bool:
        """Whether this person's own limits (dates, uses left, daily window) let them in at `now` (local)."""
        if self.valid_from:
            starts = dt_util.parse_datetime(self.valid_from)
            if starts is None or now < dt_util.as_local(starts):
                return False
        if self.valid_until:
            ends = dt_util.parse_datetime(self.valid_until)
            if ends is None or now >= dt_util.as_local(ends):
                return False
        if self.uses_left is not None and self.uses_left <= 0:
            return False
        return _in_window(now, self.access_from, self.access_until, self.access_days)


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
    # When the band works (on top of its owner being allowed). All optional.
    expires: str | None = None  # ISO date-time; not allowed from then on
    access_from: str | None = None  # "HH:MM" local time; with access_until, a daily window
    access_until: str | None = None  # "HH:MM"; earlier than access_from means overnight
    access_days: list[str] | None = None  # WEEKDAYS the window applies to; None = every day

    @property
    def display(self) -> str:
        """Readable ID."""
        return display_uid(self.uid)

    @property
    def has_schedule(self) -> bool:
        return bool(self.expires or self.access_from or self.access_until or self.access_days)

    def in_schedule(self, now: datetime) -> bool:
        """Whether the band's own limits (expiry, time window, days) allow it at `now` (local time)."""
        if self.expires:
            ends = dt_util.parse_datetime(self.expires)
            if ends is None or now >= dt_util.as_local(ends):
                return False
        return _in_window(now, self.access_from, self.access_until, self.access_days)


def _in_window(now: datetime, access_from: str | None, access_until: str | None, days: list[str] | None) -> bool:
    """A daily window ("HH:MM" to "HH:MM", on some weekdays). Nothing set: always."""
    start, end = _parse_time(access_from), _parse_time(access_until)
    if start is None and end is None:
        return days is None or WEEKDAYS[now.weekday()] in days
    start, end, t = start or time(0, 0), end or time(23, 59, 59), now.time()
    if start <= end:
        return (days is None or WEEKDAYS[now.weekday()] in days) and start <= t < end
    # Overnight (e.g. 22:00-06:00): the part after midnight belongs to the day it started.
    if t >= start:
        return days is None or WEEKDAYS[now.weekday()] in days
    if t < end:
        return days is None or WEEKDAYS[(now.weekday() - 1) % 7] in days
    return False


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        hours, minutes = (int(x) for x in str(value).split(":")[:2])
        return time(hours, minutes)
    except ValueError:
        return None


@dataclass
class _Data:
    people: dict[str, Person] = field(default_factory=dict)
    bands: dict[str, Band] = field(default_factory=dict)
    released_readers: set[str] = field(default_factory=set)  # device ids released with unpair_reader
    reader_cameras: dict[str, str] = field(default_factory=dict)  # reader device id -> camera entity (snapshots)
    settings: dict = field(default_factory=dict)  # house settings (SETTINGS_DEFAULTS); only changed values kept


# House settings, changed with magicband.set_settings (admin) or the page.
SETTINGS_DEFAULTS: dict = {
    "lockdown": False,  # lockdown now (by hand)
    "lockdown_away": False,  # lockdown while nobody's home (zone.home is 0)
    "lockdown_night": False,  # lockdown between lockdown_from and lockdown_until
    "lockdown_from": "23:00",
    "lockdown_until": "06:00",
    "lockdown_alarm": None,  # an alarm_control_panel: lockdown while it's armed
    "holiday_shows": True,  # on a holiday, its show after each welcome
    "birthday_shows": True,  # on someone's birthday, the Birthday show after their welcome
    "passport": True,  # count taps and give badges
    "passport_shows": True,  # the Stamp show after a welcome that earns a badge
}


_BAND_FIELDS = set(Band.__dataclass_fields__)
_PERSON_FIELDS = set(Person.__dataclass_fields__)


def _check_birthday(value: str) -> str | None:
    """"MM-DD" (or "" to clear)."""
    if not value:
        return None
    try:
        month, day = (int(x) for x in str(value).split("-")[-2:])
        datetime(2000, month, day)  # 2000 is a leap year, so 29 February is fine
    except ValueError as err:
        raise ValueError("Birthday must be a month and day, MM-DD (e.g. 07-14)") from err
    return f"{month:02d}-{day:02d}"


def _check_colour(colour: str | None) -> None:
    if colour and colour not in READER_COLOURS:
        raise ValueError(f"Welcome colour must be one of {', '.join(READER_COLOURS)}")


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
        released = {d for d in raw.get("released_readers", []) or [] if isinstance(d, str)}
        cameras = {
            d: c for d, c in (raw.get("reader_cameras") or {}).items()
            if isinstance(d, str) and isinstance(c, str) and c.startswith("camera.")
        } if isinstance(raw.get("reader_cameras"), dict) else {}
        settings = {
            k: v for k, v in (raw.get("settings") or {}).items()
            if k in SETTINGS_DEFAULTS and (
                isinstance(v, str) or v is None if k == "lockdown_alarm" else isinstance(v, type(SETTINGS_DEFAULTS[k]))
            )
        } if isinstance(raw.get("settings"), dict) else {}
        self._data = _Data(people=people, bands=bands, released_readers=released, reader_cameras=cameras,
                           settings=settings)

    def _serialize(self) -> dict:
        return {
            "people": [asdict(p) for p in self._data.people.values()],
            "bands": [asdict(b) for b in self._data.bands.values()],
            "released_readers": sorted(self._data.released_readers),
            "reader_cameras": dict(self._data.reader_cameras),
            "settings": dict(self._data.settings),
        }

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._serialize, 1.0)

    # ------------------------------------------------------------------ readers released to another Home Assistant

    def reader_released(self, device_id: str) -> bool:
        return device_id in self._data.released_readers

    @callback
    def set_reader_released(self, device_id: str, released: bool) -> None:
        if released:
            self._data.released_readers.add(device_id)
        else:
            self._data.released_readers.discard(device_id)
        self._save()

    # ------------------------------------------------------------------ snapshot cameras (optional)

    def reader_camera(self, device_id: str | None) -> str | None:
        return self._data.reader_cameras.get(device_id) if device_id else None

    @property
    def reader_cameras(self) -> dict[str, str]:
        return dict(self._data.reader_cameras)

    @callback
    def set_reader_camera(self, device_id: str, camera: str | None) -> None:
        if camera:
            self._data.reader_cameras[device_id] = camera
        else:
            self._data.reader_cameras.pop(device_id, None)
        self._save()

    # ------------------------------------------------------------------ house settings and lockdown

    @property
    def settings(self) -> dict:
        return {**SETTINGS_DEFAULTS, **self._data.settings}

    @callback
    def set_settings(self, **changes) -> dict:
        for key, value in changes.items():
            if key not in SETTINGS_DEFAULTS:
                raise ValueError(f"Unknown setting {key}")
            if key in ("lockdown_from", "lockdown_until"):
                if _parse_time(value) is None:
                    raise ValueError(f"{key} must be a time (HH:MM)")
                value = _parse_time(value).strftime("%H:%M")
            if key == "lockdown_alarm":
                value = value or None
                if value and not str(value).startswith("alarm_control_panel."):
                    raise ValueError("Pick an alarm panel (alarm_control_panel.…)")
            self._data.settings[key] = value
        self._changed()
        return self.settings

    def lockdown_reasons(self, now: datetime | None = None) -> list[str]:
        """Why the house is in lockdown now (empty: it isn't). Only people marked lockdown_exempt get in."""
        cfg, reasons = self.settings, []
        now = dt_util.as_local(now or dt_util.now())
        if cfg["lockdown"]:
            reasons.append("Lockdown is on")
        if cfg["lockdown_away"]:
            home = self.hass.states.get("zone.home")
            try:
                if home is not None and int(float(home.state)) == 0:
                    reasons.append("Nobody's home")
            except ValueError:
                pass
        if cfg["lockdown_night"] and _in_window(now, cfg["lockdown_from"], cfg["lockdown_until"], None):
            reasons.append(f"Night hours ({cfg['lockdown_from']}–{cfg['lockdown_until']})")
        if alarm := cfg["lockdown_alarm"]:
            state = self.hass.states.get(alarm)
            if state is not None and (state.state.startswith("armed") or state.state == "triggered"):
                reasons.append(f"{state.attributes.get('friendly_name') or alarm} is {state.state.replace('_', ' ')}")
        return reasons

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

    def band_allowed(self, uid: str, now: datetime | None = None) -> bool:
        """Allowed in now: a valid ID, owned by an allowed person, and within the band's own schedule."""
        band = self.get_band(uid)
        if band is None or parse_uid(band.uid) is None:
            return False  # only real NFC IDs are ever allowed
        person = self.get_person(band.person_id) if band else None
        if not (person and person.allowed):
            return False
        local = dt_util.as_local(now or dt_util.now())
        if not (person.in_pass(local) and band.in_schedule(local)):
            return False
        return person.lockdown_exempt or not self.lockdown_reasons(local)

    def person_allowed_now(self, person: Person, now: datetime | None = None) -> bool:
        """Whether a person could get in now (allowed, within their pass, and not locked down)."""
        local = dt_util.as_local(now or dt_util.now())
        return person.allowed and person.in_pass(local) and (person.lockdown_exempt or not self.lockdown_reasons(local))

    @callback
    def use_tap(self, person_id: str) -> None:
        """A welcomed tap: one use off a guest pass with a limited number of uses."""
        person = self._data.people.get(person_id)
        if person is not None and person.uses_left is not None and person.uses_left > 0:
            person.uses_left -= 1
            self._changed()

    def allowed_uids(self, now: datetime | None = None) -> list[str]:
        return sorted(b.uid for b in self._data.bands.values() if self.band_allowed(b.uid, now))

    def welcome_colours(self, now: datetime | None = None) -> dict[str, str]:
        """Allowed band -> its owner's welcome colour, for bands whose owner has one."""
        out = {}
        for uid in self.allowed_uids(now):
            person = self.get_person(self._data.bands[uid].person_id)
            if person is not None and person.welcome_colour:
                out[uid] = person.welcome_colour
        return out

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
    def add_person(
        self, name: str, ha_person: str | None = None, allowed: bool = True, welcome_colour: str | None = None,
        guest: bool = False,
    ) -> Person:
        name = name.strip()
        if not name:
            raise ValueError("A person needs a name")
        if self.find_person(name):
            raise ValueError(f"There's already a person called {name}")
        _check_colour(welcome_colour)
        person = Person(
            id=uuid.uuid4().hex[:12], name=name, ha_person=ha_person or None, allowed=allowed,
            welcome_colour=welcome_colour or None, guest=guest,
        )
        self._data.people[person.id] = person
        self._changed()
        return person

    @callback
    def update_person(
        self,
        person_id: str,
        *,
        name: str | None = None,
        ha_person: str | None = None,
        allowed: bool | None = None,
        welcome_colour: str | None = None,
        birthday: str | None = None,
        lockdown_exempt: bool | None = None,
        guest: bool | None = None,
    ) -> Person:
        person = self._data.people[person_id]
        if birthday is not None:
            person.birthday = _check_birthday(birthday)
        if lockdown_exempt is not None:
            person.lockdown_exempt = lockdown_exempt
        if guest is not None:
            person.guest = guest
            if not guest:  # no longer a guest: the pass goes too
                person.valid_from = person.valid_until = person.access_from = person.access_until = None
                person.uses_left = person.access_days = None
        if welcome_colour is not None:
            _check_colour(welcome_colour)
            person.welcome_colour = welcome_colour or None  # "" = the reader's own welcome colour
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
        """Drop the longest-unseen unassigned, unnamed bands beyond `limit`. Returns their IDs."""
        spare = sorted(
            # Any user can set a band's type (it's an entity), so only an owner or a nickname
            # (both admin-only) keep an unassigned band.
            (b for b in self._data.bands.values() if b.person_id is None and not b.label),
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
    def set_band_access(
        self,
        uid: str,
        *,
        expires: datetime | None | str = "keep",
        access_from: time | None | str = "keep",
        access_until: time | None | str = "keep",
        access_days: list[str] | None | str = "keep",
    ) -> Band:
        """Set when a band works. None clears a limit; "keep" leaves it as it is."""
        band = self._data.bands.get(normalize_uid(uid))
        if band is None:
            raise ValueError("Unknown band")
        if expires != "keep":
            band.expires = dt_util.as_utc(expires).isoformat() if expires else None
        if access_from != "keep":
            band.access_from = access_from.strftime("%H:%M") if access_from else None
        if access_until != "keep":
            band.access_until = access_until.strftime("%H:%M") if access_until else None
        if access_days != "keep":
            days = [d for d in WEEKDAYS if d in (access_days or [])]
            band.access_days = days or None
        self._changed()
        return band

    @callback
    def set_guest_pass(
        self,
        person_id: str,
        *,
        valid_from: datetime | None | str = "keep",
        valid_until: datetime | None | str = "keep",
        uses_left: int | None | str = "keep",
        access_from: time | None | str = "keep",
        access_until: time | None | str = "keep",
        access_days: list[str] | None | str = "keep",
    ) -> Person:
        """Set a person's guest pass. None clears a limit; "keep" leaves it as it is. Makes them a guest."""
        person = self._data.people.get(person_id)
        if person is None:
            raise ValueError("Unknown person")
        if valid_from != "keep":
            person.valid_from = dt_util.as_utc(valid_from).isoformat() if valid_from else None
        if valid_until != "keep":
            person.valid_until = dt_util.as_utc(valid_until).isoformat() if valid_until else None
        if uses_left != "keep":
            person.uses_left = None if uses_left is None else max(0, int(uses_left))
        if access_from != "keep":
            person.access_from = access_from.strftime("%H:%M") if access_from else None
        if access_until != "keep":
            person.access_until = access_until.strftime("%H:%M") if access_until else None
        if access_days != "keep":
            person.access_days = [d for d in WEEKDAYS if d in (access_days or [])] or None
        person.guest = True
        self._changed()
        return person

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
