"""MagicbHAnds: the Home Assistant integration (domain ``magicband``).

Sends light and vibration effects to MagicBand+ bands through MagicBand
bridges (``magicband.send``), and hears what bands send back over Bluetooth.

Listens for tag scans from MagicBand readers (ESPHome, project
legal-copy7045.magicband-reader), keeps a log of every band, lets you give
bands to people (with or without a Home Assistant user), and syncs the list of
allowed bands to every reader so they can answer instantly on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
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

from .const import (
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
from .listener import BandListener
from .registry import Band, MagicBandRegistry, display_uid, parse_uid

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SELECT, Platform.SENSOR]

EVENT_TAG_SCANNED = "tag_scanned"
# The reader stores its allowed list as ",UID,UID," in 3,200 characters
# including the terminator (esphome/magicband-reader.yaml, known_list): 213
# bands with 7-byte IDs. Readers on 0.10.3 or earlier hold 1,600 (106 bands).
READER_LIST_CAPACITY = 3199
SYNC_NOTIFICATION_ID = f"{DOMAIN}_reader_sync"


@dataclass
class MagicBandData:
    """Runtime data for the config entry."""

    registry: MagicBandRegistry
    sync: Debouncer
    listener: BandListener
    beacons: BeaconTracker
    unsubs: list = field(default_factory=list)


type MagicBandConfigEntry = ConfigEntry[MagicBandData]


def _esphome_entries(hass: HomeAssistant, device: dr.DeviceEntry) -> list[ConfigEntry]:
    entries = (hass.config_entries.async_get_entry(entry_id) for entry_id in device.config_entries)
    return [entry for entry in entries if entry is not None and entry.domain == "esphome"]


def is_reader_device(hass: HomeAssistant, device_id: str | None) -> bool:
    """True if the device is a MagicBand reader: an ESPHome device built from the reader firmware.

    The model alone isn't enough: other integrations (a phone registered with
    the mobile app, for example) let any logged-in user pick a device's model
    and name, and send tag scans from it.
    """
    if not device_id:
        return False
    device = dr.async_get(hass).async_get(device_id)
    if device is None or not _esphome_entries(hass, device):
        return False
    if (device.model or "").lower() == READER_MODEL:
        return True
    # Fallback (a reader built with another project name): an ESPHome device with the reader's "Known bands" sensor.
    return any(
        entity.entity_id.endswith("_known_bands") and entity.domain == "sensor" and entity.platform == "esphome"
        for entity in er.async_entries_for_device(er.async_get(hass), device_id)
    )


def reader_set_services(hass: HomeAssistant) -> list[str]:
    """The esphome.<node>_set_known_bands actions of the MagicBand readers, and no other device's.

    Any ESPHome device can declare an action with that name; only readers get the allowed list.
    """
    names: set[str] = set()
    for device in dr.async_get(hass).devices.values():
        if not is_reader_device(hass, device.id):
            continue
        for entry in _esphome_entries(hass, device):
            info = getattr(getattr(entry, "runtime_data", None), "device_info", None)
            node = getattr(info, "name", None) or entry.data.get("device_name")
            if node:
                names.add(f"{node.replace('-', '_')}{READER_SET_SERVICE_SUFFIX}")
    return sorted(name for name in names if hass.services.has_service("esphome", name))


def _reader_name(hass: HomeAssistant, device_id: str | None) -> str | None:
    device = dr.async_get(hass).async_get(device_id) if device_id else None
    return (device.name_by_user or device.name) if device else None


async def async_setup_entry(hass: HomeAssistant, entry: MagicBandConfigEntry) -> bool:
    if entry.title == "MagicBand":  # the integration's old name
        hass.config_entries.async_update_entry(entry, title="MagicbHAnds")
    registry = MagicBandRegistry(hass)
    await registry.async_load()

    async def _sync() -> None:
        await async_sync_readers(hass, registry)

    debouncer = Debouncer(hass, _LOGGER, cooldown=2.0, immediate=False, function=_sync)
    beacons = BeaconTracker(hass, registry)
    await beacons.async_load()
    listener = BandListener(hass)
    listener.on_band = beacons.async_beacon
    data = MagicBandData(registry=registry, sync=debouncer, listener=listener, beacons=beacons)
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
        _handle_scan(hass, registry, uid, device_id)
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
    await async_setup_panel(hass, entry.options.get(CONF_SIDEBAR, True))
    data.unsubs.append(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_updated(hass: HomeAssistant, entry: MagicBandConfigEntry) -> None:
    """Configure saves the options after every change; only the sidebar setting needs acting on."""
    if entry.options.get(CONF_SIDEBAR, True):
        await async_setup_panel(hass, True)
    else:
        async_remove_panel(hass)


async def async_unload_entry(hass: HomeAssistant, entry: MagicBandConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        async_remove_panel(hass)
        await entry.runtime_data.registry.async_flush()
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
def _handle_scan(hass: HomeAssistant, registry: MagicBandRegistry, tag_id: str, device_id: str | None) -> None:
    reader = _reader_name(hass, device_id)
    if registry.get_band(tag_id) is None:
        for old in registry.prune_unassigned():
            persistent_notification.async_dismiss(hass, f"{DOMAIN}_unknown_{old}")
            for entry in hass.config_entries.async_loaded_entries(DOMAIN):
                entry.runtime_data.beacons.unlink_nfc(old)
    band, is_new = registry.record_scan(tag_id, reader)
    person = registry.get_person(band.person_id)
    allowed = registry.band_allowed(band.uid)

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
        },
    )
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
# Sync to readers
# ---------------------------------------------------------------------------


async def async_sync_readers(hass: HomeAssistant, registry: MagicBandRegistry) -> dict[str, Any]:
    """Send the allowed list to every reader.

    Readers from 0.10.4 on reply whether they applied the list; a reader that
    can't (a list too long to store, or malformed) empties its own list, so
    it denies everyone rather than keep bands that were revoked. Failures are
    reported in a notification and in the result: {"readers", "applied", "failed"}.
    """
    uids = registry.allowed_uids()
    bands = ",".join(uids)
    stored = 1 + sum(len(u) + 1 for u in uids)  # ",UID,UID," as the reader keeps it
    services = reader_set_services(hass)
    ignored = sorted(
        name
        for name in hass.services.async_services_for_domain("esphome")
        if name.endswith(READER_SET_SERVICE_SUFFIX) and name not in services
    )
    if ignored:
        _LOGGER.warning("Not sending the allowed list to %s: not a MagicBand reader", ", ".join(ignored))
    failed: dict[str, str] = {}
    for service in services:
        try:
            await hass.services.async_call("esphome", service, {"bands": bands}, blocking=True)
        except Exception as err:  # noqa: BLE001 - one offline reader shouldn't stop the rest
            failed[service] = str(err) or type(err).__name__
            _LOGGER.warning("Reader esphome.%s didn't take the allowed list: %s", service, failed[service])
    problems = []
    if stored > READER_LIST_CAPACITY:
        problems.append(
            f"The allowed list is too long for the readers ({len(uids)} bands, {stored} characters; "
            f"they hold {READER_LIST_CAPACITY}). Readers that can't store it deny every band until "
            "there are fewer allowed bands."
        )
    problems += [f"**esphome.{name}**: {error}" for name, error in failed.items()]
    if problems:
        persistent_notification.async_create(
            hass,
            "Some readers don't have the current allowed list:\n\n- " + "\n- ".join(problems),
            title="MagicbHAnds: reader not updated",
            notification_id=SYNC_NOTIFICATION_ID,
        )
    else:
        persistent_notification.async_dismiss(hass, SYNC_NOTIFICATION_ID)
    _LOGGER.debug("Synced %d allowed band(s) to %d reader(s), %d failed", len(uids), len(services), len(failed))
    return {"readers": len(services), "applied": len(services) - len(failed), "failed": sorted(failed)}


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
                call.data[ATTR_NAME], call.data.get(ATTR_HA_PERSON), call.data.get(ATTR_ALLOWED, True)
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

    async def sync(call: ServiceCall) -> dict[str, Any]:
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
                    "bands": [b.display for b in registry.bands_for(p.id)],
                }
                for p in registry.people
            ],
            "bands": [_band_dict(registry, b, _beacons()[1]) for b in registry.bands],
        }

    async_register_admin_service(
        hass, DOMAIN, "add_person",
        add_person,
        vol.Schema(
            {
                vol.Required(ATTR_NAME): cv.string,
                vol.Optional(ATTR_HA_PERSON): cv.entity_domain("person"),
                vol.Optional(ATTR_ALLOWED, default=True): cv.boolean,
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
    }
