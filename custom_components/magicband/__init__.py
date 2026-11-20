"""MagicbHAnds: the Home Assistant integration (domain ``magicband``).

Sends light and vibration effects to MagicBand+ bands through MagicBand
bridges (``magicband.send``), and hears what bands send back over Bluetooth.

Listens for tag scans from MagicBand readers (ESPHome, project
legal-copy7045.magicband-reader), keeps a log of every band, lets you give
bands to people (with or without a Home Assistant user), and syncs the list of
allowed bands to every reader so they can answer instantly on their own.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import secrets
import time
from typing import Any

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_SERVICE_REGISTERED, Platform
from homeassistant.core import CoreState, Event, HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_WELCOME_COLOUR,
    CONF_BATTERY_LEVEL,
    CONF_SNAPSHOT_DAYS,
    DEFAULT_BATTERY_LEVEL,
    READER_COLOURS,
    WEEKDAYS,
    ATTR_ALLOWED,
    ATTR_BAND,
    ATTR_HA_PERSON,
    ATTR_LABEL,
    ATTR_NAME,
    ATTR_PERSON,
    DOMAIN,
    EVENT_TAP,
    READER_MODEL,
    READER_SET_SERVICE_SUFFIX,
    SIGNAL_READER_TAP,
    SIGNAL_UPDATED,
    SYNC_INTERVAL_MINUTES,
)
from .beacons import BeaconTracker
from .blueprint_installer import async_install_blueprints
from .panel import CONF_SIDEBAR, async_remove_panel, async_setup_panel
from .bridges import ANIMATIONS, EFFECTS, async_send, find_bridges
from . import snapshots
from .history import TapHistory
from .listener import BandListener
from .readers import CONF_READER_KEY, READER_LIST_CAPACITY, ReaderManager, is_reader_device  # noqa: F401 - re-exported
from .registry import Band, MagicBandRegistry, display_uid, parse_uid

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SELECT, Platform.SENSOR]

EVENT_TAG_SCANNED = "tag_scanned"
MAX_SYNCS_PER_MINUTE = 6
MAX_ENROL_MINUTES = 15
SIGNAL_ENROLMENT = f"{DOMAIN}_enrolment"
EVENT_ENROLLED = "magicband_enrolled"


@dataclass
class Enrolment:
    """Bands tapped until `until` that nobody owns yet go to this person."""

    person_id: str
    until: datetime
    label: str | None = None
    count: int = 0
    device_id: str | None = None  # only taps on this reader enrol (None: any reader)


@dataclass
class MagicBandData:
    """Runtime data for the config entry."""

    registry: MagicBandRegistry
    sync: Debouncer
    listener: BandListener
    beacons: BeaconTracker
    readers: ReaderManager
    history: TapHistory
    enrolment: Enrolment | None = None
    unsubs: list = field(default_factory=list)


type MagicBandConfigEntry = ConfigEntry[MagicBandData]


def _reader_name(hass: HomeAssistant, device_id: str | None) -> str | None:
    device = dr.async_get(hass).async_get(device_id) if device_id else None
    return (device.name_by_user or device.name) if device else None


async def async_setup_entry(hass: HomeAssistant, entry: MagicBandConfigEntry) -> bool:
    if entry.title == "MagicBand":  # the integration's old name
        hass.config_entries.async_update_entry(entry, title="MagicbHAnds")
    registry = MagicBandRegistry(hass)
    await registry.async_load()
    if not entry.data.get(CONF_READER_KEY):
        # The key readers are paired with (readers.py): kept in the config entry,
        # which only administrators can read.
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_READER_KEY: secrets.token_hex(32)})
    readers = ReaderManager(hass, registry, entry.data[CONF_READER_KEY])
    history = TapHistory(hass)
    await history.async_load()

    async def _sync() -> None:
        await readers.async_sync()

    debouncer = Debouncer(hass, _LOGGER, cooldown=2.0, immediate=False, function=_sync)
    beacons = BeaconTracker(hass, registry)
    beacons.battery_low_level = entry.options.get(CONF_BATTERY_LEVEL, DEFAULT_BATTERY_LEVEL)
    await beacons.async_load()
    listener = BandListener(hass)
    listener.on_band = beacons.async_beacon
    data = MagicBandData(
        registry=registry, sync=debouncer, listener=listener, beacons=beacons, readers=readers, history=history
    )
    entry.runtime_data = data

    @callback
    def _allowed_changed() -> None:
        hass.async_create_task(debouncer.async_call())
        async_dispatcher_send(hass, SIGNAL_UPDATED)

    data.unsubs.append(registry.async_add_listener(_allowed_changed))

    @callback
    def _on_tag(event: Event) -> None:
        device_id = event.data.get("device_id")
        if not isinstance(device_id, str) or not is_reader_device(hass, device_id):
            return
        uid = parse_uid(event.data.get("tag_id"))
        if uid is None:
            # Not an NFC ID: e.g. the reader's "Test welcome" button ("TEST").
            _LOGGER.debug("Ignoring tag %r from a reader: not a band ID", event.data.get("tag_id"))
            return
        _handle_scan(hass, data, uid, device_id)
        beacons.async_start_pairing(uid, _reader_name(hass, device_id))

    data.unsubs.append(hass.bus.async_listen(EVENT_TAG_SCANNED, _on_tag))

    @callback
    def _on_service_registered(event: Event) -> None:
        # A reader (re)connected: give it the current list.
        if event.data.get("domain") == "esphome" and str(event.data.get("service", "")).endswith(
            READER_SET_SERVICE_SUFFIX
        ):
            hass.async_create_task(debouncer.async_call())

    data.unsubs.append(hass.bus.async_listen(EVENT_SERVICE_REGISTERED, _on_service_registered))
    @callback
    def _periodic_sync(_now) -> None:
        hass.async_create_task(debouncer.async_call())

    data.unsubs.append(async_track_time_interval(hass, _periodic_sync, timedelta(minutes=SYNC_INTERVAL_MINUTES)))

    @callback
    def _every_minute(_now) -> None:
        # A band's schedule opened or closed: the readers' lists change.
        if readers.schedule_changed():
            hass.async_create_task(debouncer.async_call())
        readers.check_health()
        if data.enrolment is not None and dt_util.utcnow() >= data.enrolment.until:
            _end_enrolment(hass, data)
        if _now.minute == 7:  # hourly: old tap snapshots go
            days = entry.options.get(CONF_SNAPSHOT_DAYS, snapshots.DEFAULT_DAYS)
            hass.async_add_executor_job(snapshots.prune, hass, days)

    data.unsubs.append(async_track_time_interval(hass, _every_minute, timedelta(minutes=1)))

    if hass.state is CoreState.running:
        hass.async_create_task(debouncer.async_call())
    else:
        data.unsubs.append(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _periodic_sync)
        )

    if (unsub_bt := data.listener.async_start()) is not None:
        data.unsubs.append(unsub_bt)

    _register_services(hass)
    await async_install_blueprints(hass)
    snapshots.async_register_view(hass)
    await async_setup_panel(hass, entry.options.get(CONF_SIDEBAR, True))
    data.unsubs.append(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_updated(hass: HomeAssistant, entry: MagicBandConfigEntry) -> None:
    """Configure saves the options after every change; the sidebar and battery settings need acting on."""
    entry.runtime_data.beacons.battery_low_level = entry.options.get(CONF_BATTERY_LEVEL, DEFAULT_BATTERY_LEVEL)
    if entry.options.get(CONF_SIDEBAR, True):
        await async_setup_panel(hass, True)
    else:
        async_remove_panel(hass)


async def async_unload_entry(hass: HomeAssistant, entry: MagicBandConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        async_remove_panel(hass)
        await entry.runtime_data.registry.async_flush()
        await entry.runtime_data.history.async_flush()
        await entry.runtime_data.beacons.async_shutdown()
        for unsub in entry.runtime_data.unsubs:
            unsub()
        entry.runtime_data.sync.async_shutdown()
        for service in list(hass.services.async_services_for_domain(DOMAIN)):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------


@callback
def _handle_scan(hass: HomeAssistant, data: MagicBandData, tag_id: str, device_id: str | None) -> None:
    registry = data.registry
    reader = _reader_name(hass, device_id)
    if registry.get_band(tag_id) is None:
        for old in registry.prune_unassigned():
            persistent_notification.async_dismiss(hass, f"{DOMAIN}_unknown_{old}")
            data.beacons.unlink_nfc(old)
    band, is_new = registry.record_scan(tag_id, reader)
    enrolled = _maybe_enrol(hass, data, band.uid, device_id)
    person = registry.get_person(band.person_id)
    # The tap that enrols a band never counts as allowed: it was an unknown band
    # a moment ago, so it mustn't open anything. Its next tap is let in.
    allowed = False if enrolled else registry.band_allowed(band.uid)
    name = data.beacons.band_display_name(band.uid)

    hass.bus.async_fire(
        EVENT_TAP,
        {
            ATTR_BAND: band.display,
            ATTR_LABEL: band.label or None,
            ATTR_PERSON: person.name if person else None,
            "person_id": person.id if person else None,
            ATTR_HA_PERSON: person.ha_person if person else None,
            ATTR_ALLOWED: allowed,
            "known": person is not None,
            "reader": reader,
            "reader_device_id": device_id,
            "name": name,
            "enrolled": enrolled,
        },
    )
    entry = data.history.add(band=band.display, name=name, person=person.name if person else None, reader=reader,
                             allowed=allowed, enrolled=enrolled)
    if camera := data.registry.reader_camera(device_id):
        # Optional: a picture of who tapped, from the camera linked to this reader (in the
        # background, so the tap and any unlock aren't held up).
        async def _snapshot() -> None:
            if snap := await snapshots.async_capture(hass, camera):
                entry["snapshot"] = snap
                data.history.changed()
                async_dispatcher_send(hass, SIGNAL_UPDATED)

        hass.async_create_background_task(_snapshot(), f"{DOMAIN}_snapshot")
    async_dispatcher_send(hass, SIGNAL_UPDATED)
    if device_id:
        async_dispatcher_send(hass, SIGNAL_READER_TAP, device_id, band.uid, allowed)

    if person is None:
        persistent_notification.async_create(
            hass,
            (
                f"{'A new' if is_new else 'An unassigned'} band **{band.display}** was tapped on "
                f"**{reader or 'a reader'}**.\n\n"
                "To let it in, open **Settings → Devices & services → MagicbHAnds → Configure → "
                "Add or assign a band**, then pick this band and who it belongs to."
            ),
            title="MagicbHAnds: unknown band",
            notification_id=f"{DOMAIN}_unknown_{band.uid}",
        )


# ---------------------------------------------------------------------------
# Enrolment: the next bands tapped go to one person
# ---------------------------------------------------------------------------


@callback
def _maybe_enrol(hass: HomeAssistant, data: MagicBandData, uid: str, device_id: str | None = None) -> bool:
    """Give a band nobody owns to the person being enrolled, if enrolment is on (and it's on that reader)."""
    enrolment = data.enrolment
    if enrolment is None:
        return False
    if enrolment.device_id and device_id != enrolment.device_id:
        return False
    if dt_util.utcnow() >= enrolment.until:
        _end_enrolment(hass, data)
        return False
    band = data.registry.get_band(uid)
    person = data.registry.get_person(enrolment.person_id)
    if band is None or band.person_id is not None or person is None:
        return False  # only bands nobody owns: enrolment never takes a band from someone
    enrolment.count += 1
    label = f"{enrolment.label} {enrolment.count}" if enrolment.label else None
    data.registry.assign_band(uid, person.id, label)
    persistent_notification.async_dismiss(hass, f"{DOMAIN}_unknown_{uid}")
    hass.bus.async_fire(EVENT_ENROLLED, {"band": band.display, "person": person.name, "count": enrolment.count})
    async_dispatcher_send(hass, SIGNAL_ENROLMENT)
    return True


@callback
def _end_enrolment(hass: HomeAssistant, data: MagicBandData) -> None:
    enrolment, data.enrolment = data.enrolment, None
    if enrolment is not None:
        person = data.registry.get_person(enrolment.person_id)
        persistent_notification.async_create(
            hass,
            f"Enrolment for **{person.name if person else 'someone'}** ended: {enrolment.count} band(s) added.",
            title="MagicbHAnds: enrolment finished",
            notification_id=f"{DOMAIN}_enrolment",
        )
    async_dispatcher_send(hass, SIGNAL_ENROLMENT)


def enrolment_state(data: MagicBandData) -> dict[str, Any] | None:
    enrolment = data.enrolment
    if enrolment is None:
        return None
    person = data.registry.get_person(enrolment.person_id)
    return {
        "person": person.name if person else None,
        "until": enrolment.until.isoformat(),
        "count": enrolment.count,
        "reader": _reader_name(data.readers.hass, enrolment.device_id) if enrolment.device_id else None,
        "reader_device_id": enrolment.device_id,
    }


# ---------------------------------------------------------------------------
# Sync to readers
# ---------------------------------------------------------------------------


async def async_sync_readers(hass: HomeAssistant, registry: MagicBandRegistry | None = None) -> dict[str, Any]:
    """Send the allowed list to every reader now (see readers.py)."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("MagicbHAnds isn't set up")
    return await entries[0].runtime_data.readers.async_sync()


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def _get_registry(hass: HomeAssistant) -> MagicBandRegistry:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("MagicbHAnds isn't set up")
    return entries[0].runtime_data.registry


def _resolve_band(registry: MagicBandRegistry, value: str) -> str:
    if value.strip().lower() == "last":
        band = registry.last_band
        if band is None:
            raise ServiceValidationError("No band has been scanned yet")
        return band.uid
    if (uid := parse_uid(value)) is not None:
        return uid
    if registry.get_band(value) is not None:
        return registry.get_band(value).uid  # an older stored ID that isn't a valid NFC ID: can still be removed
    raise ServiceValidationError(f"{value} isn't a valid band ID (4, 7 or 10 bytes of hex, e.g. 04-53-65-2A-C0-5F-80)")


def _resolve_person(registry: MagicBandRegistry, value: str):
    person = registry.find_person(value)
    if person is None:
        raise ServiceValidationError(f"No person called {value}")
    return person


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "add_person"):
        return

    async def add_person(call: ServiceCall) -> dict[str, Any]:
        registry = _get_registry(hass)
        try:
            person = registry.add_person(
                call.data[ATTR_NAME],
                call.data.get(ATTR_HA_PERSON),
                call.data.get(ATTR_ALLOWED, True),
                call.data.get(ATTR_WELCOME_COLOUR) or None,
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        return {"person_id": person.id}

    async def update_person(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        person = _resolve_person(registry, call.data[ATTR_PERSON])
        try:
            registry.update_person(
                person.id,
                name=call.data.get(ATTR_NAME),
                ha_person=call.data.get(ATTR_HA_PERSON),
                allowed=call.data.get(ATTR_ALLOWED),
                welcome_colour=call.data.get(ATTR_WELCOME_COLOUR),
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def remove_person(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        registry.remove_person(_resolve_person(registry, call.data[ATTR_PERSON]).id)

    async def assign_band(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        uid = _resolve_band(registry, call.data[ATTR_BAND])
        person = _resolve_person(registry, call.data[ATTR_PERSON])
        try:
            registry.assign_band(uid, person.id, call.data.get(ATTR_LABEL))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        persistent_notification.async_dismiss(hass, f"{DOMAIN}_unknown_{registry.get_band(uid).uid}")

    async def unassign_band(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        registry.assign_band(_resolve_band(registry, call.data[ATTR_BAND]), None)

    async def remove_band(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        registry.remove_band(_resolve_band(registry, call.data[ATTR_BAND]))

    sync_times: deque[float] = deque()

    async def sync(call: ServiceCall) -> dict[str, Any]:
        # Open to every user, so limited: each sync calls every reader.
        now = time.monotonic()
        while sync_times and now - sync_times[0] >= 60:
            sync_times.popleft()
        if len(sync_times) >= MAX_SYNCS_PER_MINUTE:
            raise ServiceValidationError(f"Too many syncs: at most {MAX_SYNCS_PER_MINUTE} a minute")
        sync_times.append(now)
        return await async_sync_readers(hass, _get_registry(hass))

    async def list_bands(call: ServiceCall) -> dict[str, Any]:
        registry = _get_registry(hass)
        return {
            "people": [
                {
                    "id": p.id,
                    "name": p.name,
                    "ha_person": p.ha_person,
                    "allowed": p.allowed,
                    "welcome_colour": p.welcome_colour,
                    "bands": [b.display for b in registry.bands_for(p.id)],
                }
                for p in registry.people
            ],
            "bands": [_band_dict(registry, b, _beacons()[1]) for b in registry.bands],
            "readers": _data().readers.report(),
            "enrolment": enrolment_state(_data()),
            "colours": READER_COLOURS,
        }

    async_register_admin_service(
        hass, DOMAIN, "add_person",
        add_person,
        vol.Schema(
            {
                vol.Required(ATTR_NAME): cv.string,
                vol.Optional(ATTR_HA_PERSON): cv.entity_domain("person"),
                vol.Optional(ATTR_ALLOWED, default=True): cv.boolean,
                vol.Optional(ATTR_WELCOME_COLOUR): vol.Any("", vol.In(READER_COLOURS)),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass, DOMAIN, "update_person",
        update_person,
        vol.Schema(
            {
                vol.Required(ATTR_PERSON): cv.string,
                vol.Optional(ATTR_NAME): cv.string,
                vol.Optional(ATTR_HA_PERSON): vol.Any("", cv.entity_domain("person")),
                vol.Optional(ATTR_ALLOWED): cv.boolean,
                vol.Optional(ATTR_WELCOME_COLOUR): vol.Any("", vol.In(READER_COLOURS)),
            }
        ),
    )
    async_register_admin_service(
        hass, DOMAIN, "remove_person", remove_person, vol.Schema({vol.Required(ATTR_PERSON): cv.string})
    )
    async_register_admin_service(
        hass, DOMAIN, "assign_band",
        assign_band,
        vol.Schema(
            {
                vol.Required(ATTR_BAND): cv.string,
                vol.Required(ATTR_PERSON): cv.string,
                vol.Optional(ATTR_LABEL): cv.string,
            }
        ),
    )
    async_register_admin_service(
        hass, DOMAIN, "unassign_band", unassign_band, vol.Schema({vol.Required(ATTR_BAND): cv.string})
    )
    async_register_admin_service(
        hass, DOMAIN, "remove_band", remove_band, vol.Schema({vol.Required(ATTR_BAND): cv.string})
    )
    hass.services.async_register(DOMAIN, "sync", sync, supports_response=SupportsResponse.OPTIONAL)

    async def play_show(call: ServiceCall) -> dict[str, Any]:
        """Play a light show on the readers (a light show only: open to every user, like send)."""
        from .readers import async_play_show

        devices = call.data.get("device_id") or None
        if isinstance(devices, str):
            devices = [devices]
        return await async_play_show(hass, call.data.get("show", "Random"), devices, call.context)

    from .readers import SHOW_NAMES

    hass.services.async_register(
        DOMAIN,
        "play_show",
        play_show,
        vol.Schema(
            {
                vol.Optional("show", default="Random"): vol.In(("Random", *SHOW_NAMES)),
                vol.Optional("device_id"): vol.Any(cv.string, [cv.string]),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def answer(call: ServiceCall) -> None:
        """Answer a reader in "Ask Home Assistant" mode (admin-only: it decides the reader's welcome)."""
        await _data().readers.async_answer(call.data["device_id"], call.data["allow"], call.context)

    async def unpair_reader(call: ServiceCall) -> None:
        """Release a reader's pairing (it re-pairs with whichever MagicbHAnds syncs it next)."""
        await _data().readers.async_unpair(call.data["device_id"], call.context)

    async_register_admin_service(
        hass, DOMAIN, "unpair_reader", unpair_reader, vol.Schema({vol.Required("device_id"): cv.string})
    )

    async def pair_reader(call: ServiceCall) -> dict[str, Any]:
        """Take back a reader released with unpair_reader (it pairs again; a band tap on it confirms)."""
        return await _data().readers.async_reclaim(call.data["device_id"])

    async_register_admin_service(
        hass,
        DOMAIN,
        "pair_reader",
        pair_reader,
        vol.Schema({vol.Required("device_id"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        "answer",
        answer,
        vol.Schema({vol.Required("device_id"): cv.string, vol.Required("allow"): cv.boolean}),
    )
    async_register_admin_service(
        hass, DOMAIN, "list", list_bands, supports_response=SupportsResponse.ONLY)

    async def send(call: ServiceCall) -> dict[str, Any]:
        bridges = await async_send(hass, dict(call.data), call.context)
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            entry.runtime_data.listener.note_send()
        return {"bridges": bridges}

    async def list_heard(call: ServiceCall) -> dict[str, Any]:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("MagicbHAnds isn't set up")
        listener = entries[0].runtime_data.listener
        return {"listening": listener.active, "heard": listener.as_list(), "bands": listener.bands_list()}

    def _beacons() -> tuple[MagicBandRegistry, BeaconTracker]:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("MagicbHAnds isn't set up")
        return entries[0].runtime_data.registry, entries[0].runtime_data.beacons

    def _bluetooth_band(tracker: BeaconTracker, value: str):
        band = tracker.find(value)
        if band is None:
            raise ServiceValidationError(f"No Bluetooth band matches {value}")
        return band

    async def list_bluetooth_bands(call: ServiceCall) -> dict[str, Any]:
        return _beacons()[1].report()

    async def link_bluetooth(call: ServiceCall) -> None:
        registry, tracker = _beacons()
        band = _bluetooth_band(tracker, call.data["bluetooth_band"])
        if call.data.get(ATTR_BAND):
            uid = _resolve_band(registry, call.data[ATTR_BAND])
            if registry.get_band(uid) is None:
                raise ServiceValidationError(f"No band {uid} has been tapped or added")
            tracker.link(band, nfc_uid=uid)
        elif call.data.get(ATTR_PERSON):
            tracker.link(band, person_id=_resolve_person(registry, call.data[ATTR_PERSON]).id)
        else:
            raise ServiceValidationError("Give a band (NFC ID) or a person")

    async def unlink_bluetooth(call: ServiceCall) -> None:
        _, tracker = _beacons()
        tracker.link(_bluetooth_band(tracker, call.data["bluetooth_band"]))

    async def forget_bluetooth(call: ServiceCall) -> None:
        _, tracker = _beacons()
        tracker.forget(_bluetooth_band(tracker, call.data["bluetooth_band"]))

    async_register_admin_service(
        hass, DOMAIN, "list_bluetooth_bands", list_bluetooth_bands, supports_response=SupportsResponse.ONLY
    )
    async_register_admin_service(
        hass, DOMAIN, "link_bluetooth",
        link_bluetooth,
        vol.Schema(
            {
                vol.Required("bluetooth_band"): cv.string,
                vol.Optional(ATTR_BAND): cv.string,
                vol.Optional(ATTR_PERSON): cv.string,
            }
        ),
    )
    async_register_admin_service(
        hass, DOMAIN, "unlink_bluetooth", unlink_bluetooth, vol.Schema({vol.Required("bluetooth_band"): cv.string})
    )
    async_register_admin_service(
        hass, DOMAIN, "forget_bluetooth", forget_bluetooth, vol.Schema({vol.Required("bluetooth_band"): cv.string})
    )

    def _data() -> MagicBandData:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("MagicbHAnds isn't set up")
        return entries[0].runtime_data

    async def set_band_access(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        uid = _resolve_band(registry, call.data[ATTR_BAND])
        if registry.get_band(uid) is None:
            raise ServiceValidationError(f"No band {uid} has been tapped or added")
        if call.data.get("clear"):
            registry.set_band_access(uid, expires=None, access_from=None, access_until=None, access_days=None)
            return
        kwargs: dict[str, Any] = {}
        for key, field_name in (("expires", "expires"), ("access_from", "from"), ("access_until", "until"), ("access_days", "days")):
            if field_name in call.data:
                kwargs[key] = call.data[field_name] or None
        if kwargs.get("expires") is not None and kwargs["expires"].tzinfo is None:
            kwargs["expires"] = kwargs["expires"].replace(tzinfo=dt_util.get_default_time_zone())
        registry.set_band_access(uid, **kwargs)

    async def enrol(call: ServiceCall) -> dict[str, Any]:
        data = _data()
        person = _resolve_person(data.registry, call.data[ATTR_PERSON])
        minutes = call.data.get("minutes", 5)
        device_id = call.data.get("device_id") or None
        if device_id and not is_reader_device(hass, device_id):
            raise ServiceValidationError("That device isn't a MagicBand reader")
        data.enrolment = Enrolment(
            person_id=person.id,
            until=dt_util.utcnow() + timedelta(minutes=minutes),
            label=(call.data.get(ATTR_LABEL) or "").strip() or None,
            device_id=device_id,
        )
        persistent_notification.async_dismiss(hass, f"{DOMAIN}_enrolment")
        async_dispatcher_send(hass, SIGNAL_ENROLMENT)
        _LOGGER.info("Enrolling bands for %s for %d minute(s)", person.name, minutes)
        return enrolment_state(data) or {}

    async def stop_enrolment(call: ServiceCall) -> None:
        _end_enrolment(hass, _data())

    async def history(call: ServiceCall) -> dict[str, Any]:
        taps = []
        for tap in _data().history.recent(call.data.get("count", 50)):
            tap = dict(tap)
            if url := snapshots.signed_url(hass, tap.get("snapshot")):
                tap["snapshot_url"] = url
            taps.append(tap)
        entry = hass.config_entries.async_loaded_entries(DOMAIN)[0]
        return {
            "taps": taps,
            "cameras": _data().registry.reader_cameras,
            "snapshot_days": entry.options.get(CONF_SNAPSHOT_DAYS, snapshots.DEFAULT_DAYS),
        }

    async def set_snapshot_days(call: ServiceCall) -> None:
        """How long tap pictures are kept (the same setting as Configure → Settings)."""
        entry = hass.config_entries.async_loaded_entries(DOMAIN)[0]
        hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_SNAPSHOT_DAYS: call.data["days"]})

    async_register_admin_service(
        hass,
        DOMAIN,
        "set_snapshot_days",
        set_snapshot_days,
        vol.Schema({vol.Required("days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=365))}),
    )

    async def set_reader_camera(call: ServiceCall) -> None:
        """Link a reader to a camera (a picture with each tap), or unlink it (no camera)."""
        data = _data()
        device_id, camera = call.data["device_id"], call.data.get("camera") or None
        if not is_reader_device(hass, device_id):
            raise ServiceValidationError("That device isn't a MagicBand reader")
        if camera and not camera.startswith("camera."):
            raise ServiceValidationError("Pick a camera entity")
        data.registry.set_reader_camera(device_id, camera)
        async_dispatcher_send(hass, SIGNAL_UPDATED)

    async_register_admin_service(
        hass,
        DOMAIN,
        "set_reader_camera",
        set_reader_camera,
        vol.Schema({vol.Required("device_id"): cv.string, vol.Optional("camera"): vol.Any(None, "", cv.entity_id)}),
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        "set_band_access",
        set_band_access,
        vol.Schema(
            {
                vol.Required(ATTR_BAND): cv.string,
                vol.Optional("expires"): vol.Any(None, "", cv.datetime),
                vol.Optional("from"): vol.Any(None, "", cv.time),
                vol.Optional("until"): vol.Any(None, "", cv.time),
                vol.Optional("days"): vol.Any(None, vol.All(cv.ensure_list, [vol.In(WEEKDAYS)])),
                vol.Optional("clear", default=False): cv.boolean,
            }
        ),
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        "enrol",
        enrol,
        vol.Schema(
            {
                vol.Required(ATTR_PERSON): cv.string,
                vol.Optional("minutes", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_ENROL_MINUTES)),
                vol.Optional(ATTR_LABEL): cv.string,
                vol.Optional("device_id"): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(hass, DOMAIN, "stop_enrolment", stop_enrolment, vol.Schema({}))
    async_register_admin_service(
        hass,
        DOMAIN,
        "history",
        history,
        vol.Schema({vol.Optional("count", default=50): vol.All(vol.Coerce(int), vol.Range(min=1, max=300))}),
        supports_response=SupportsResponse.ONLY,
    )

    async def list_bridges(call: ServiceCall) -> dict[str, Any]:
        return {"bridges": find_bridges(hass)}

    hass.services.async_register(
        DOMAIN,
        "send",
        send,
        vol.Schema(
            {
                vol.Optional("effect", default="color"): vol.In(EFFECTS),
                vol.Optional("color"): cv.string,
                vol.Optional("color2"): cv.string,
                vol.Optional("colors"): cv.string,
                vol.Optional("rgb_color"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), list),
                vol.Optional("animation"): vol.In(ANIMATIONS),
                vol.Optional("vibration"): vol.All(vol.Coerce(int), vol.Range(min=0, max=15)),
                vol.Optional("leds"): vol.In(["all", "top_left", "top_right", "bottom_left", "bottom_right"]),
                vol.Optional("on_seconds"): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
                vol.Optional("fade_seconds"): vol.All(vol.Coerce(int), vol.Range(min=0, max=3)),
                vol.Optional("always_on"): cv.boolean,
                vol.Optional("flash"): cv.boolean,
                vol.Optional("fast"): cv.boolean,
                vol.Optional("seconds"): vol.All(vol.Coerce(float), vol.Range(min=1, max=60)),
                vol.Optional("hex"): cv.string,
                vol.Optional("duration_ms"): vol.All(vol.Coerce(int), vol.Range(min=0, max=30000)),
                vol.Optional("command"): dict,
                vol.Optional("bridges"): vol.All(cv.ensure_list, [cv.entity_id]),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, "list_bridges", list_bridges, supports_response=SupportsResponse.ONLY)
    async_register_admin_service(
        hass, DOMAIN, "list_heard", list_heard, supports_response=SupportsResponse.ONLY)


def _band_dict(registry: MagicBandRegistry, band: Band, tracker: BeaconTracker | None = None) -> dict[str, Any]:
    person = registry.get_person(band.person_id)
    ble = tracker.for_nfc(band.uid) if tracker else None
    return {
        "bluetooth": (
            {"id": ble.id, "nearby": ble.nearby(), "last_seen": ble.last_seen, "battery": ble.battery, "rssi": ble.last_rssi}
            if ble
            else None
        ),
        "band": display_uid(band.uid),
        "label": band.label or None,
        "person": person.name if person else None,
        "allowed": registry.band_allowed(band.uid),
        "first_seen": band.first_seen,
        "last_seen": band.last_seen,
        "last_reader": band.last_reader,
        "scans": band.scans,
        "band_type": tracker.band_type(band.uid) if tracker else band.band_type,
        "expires": band.expires,
        "access_from": band.access_from,
        "access_until": band.access_until,
        "access_days": band.access_days,
        "in_schedule": band.in_schedule(dt_util.now()),
    }
