"""MagicBand: the Home Assistant side of Magic bHAnds.

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
    SIGNAL_UPDATED,
    SYNC_INTERVAL_MINUTES,
)
from .blueprint_installer import async_install_blueprints
from .bridges import ANIMATIONS, EFFECTS, async_send, find_bridges
from .listener import BandListener
from .registry import Band, MagicBandRegistry, display_uid

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

EVENT_TAG_SCANNED = "tag_scanned"


@dataclass
class MagicBandData:
    """Runtime data for the config entry."""

    registry: MagicBandRegistry
    sync: Debouncer
    listener: BandListener
    unsubs: list = field(default_factory=list)


type MagicBandConfigEntry = ConfigEntry[MagicBandData]


def is_reader_device(hass: HomeAssistant, device_id: str | None) -> bool:
    """True if the device is a MagicBand reader."""
    if not device_id:
        return False
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return False
    if (device.model or "").lower() == READER_MODEL:
        return True
    # Fallback: a device that exposes the reader's "Known bands" sensor.
    return any(
        entity.entity_id.endswith("_known_bands") and entity.domain == "sensor"
        for entity in er.async_entries_for_device(er.async_get(hass), device_id)
    )


def _reader_name(hass: HomeAssistant, device_id: str | None) -> str | None:
    device = dr.async_get(hass).async_get(device_id) if device_id else None
    return (device.name_by_user or device.name) if device else None


async def async_setup_entry(hass: HomeAssistant, entry: MagicBandConfigEntry) -> bool:
    registry = MagicBandRegistry(hass)
    await registry.async_load()

    async def _sync() -> None:
        await async_sync_readers(hass, registry)

    debouncer = Debouncer(hass, _LOGGER, cooldown=2.0, immediate=False, function=_sync)
    data = MagicBandData(registry=registry, sync=debouncer, listener=BandListener(hass))
    entry.runtime_data = data

    @callback
    def _allowed_changed() -> None:
        hass.async_create_task(debouncer.async_call())
        async_dispatcher_send(hass, SIGNAL_UPDATED)

    data.unsubs.append(registry.async_add_listener(_allowed_changed))

    @callback
    def _on_tag(event: Event) -> None:
        device_id = event.data.get("device_id")
        if not is_reader_device(hass, device_id):
            return
        _handle_scan(hass, registry, event.data["tag_id"], device_id)

    data.unsubs.append(hass.bus.async_listen(EVENT_TAG_SCANNED, _on_tag))

    @callback
    def _on_service_registered(event: Event) -> None:
        # A reader (re)connected: give it the current list.
        if event.data.get("domain") == "esphome" and str(event.data.get("service", "")).endswith(
            READER_SET_SERVICE_SUFFIX
        ):
            hass.async_create_task(debouncer.async_call())

    data.unsubs.append(hass.bus.async_listen(EVENT_SERVICE_REGISTERED, _on_service_registered))
    data.unsubs.append(
        async_track_time_interval(
            hass, lambda _now: hass.async_create_task(debouncer.async_call()), timedelta(minutes=SYNC_INTERVAL_MINUTES)
        )
    )

    if hass.state is CoreState.running:
        hass.async_create_task(debouncer.async_call())
    else:
        data.unsubs.append(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, lambda _e: hass.async_create_task(debouncer.async_call()))
        )

    if (unsub_bt := data.listener.async_start()) is not None:
        data.unsubs.append(unsub_bt)

    _register_services(hass)
    await async_install_blueprints(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MagicBandConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.registry.async_flush()
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

    if person is None:
        persistent_notification.async_create(
            hass,
            (
                f"{'A new' if is_new else 'An unassigned'} band **{band.display}** was tapped on "
                f"**{reader or 'a reader'}**.\n\n"
                "To let it in, open **Settings → Devices & services → MagicBand → Configure → "
                "Add or assign a band**, then pick this band and who it belongs to."
            ),
            title="MagicBand: unknown band",
            notification_id=f"{DOMAIN}_unknown_{band.uid}",
        )


# ---------------------------------------------------------------------------
# Sync to readers
# ---------------------------------------------------------------------------


async def async_sync_readers(hass: HomeAssistant, registry: MagicBandRegistry) -> int:
    """Send the allowed list to every reader. Returns how many readers were updated."""
    bands = ",".join(registry.allowed_uids())
    services = [
        name
        for name in hass.services.async_services_for_domain("esphome")
        if name.endswith(READER_SET_SERVICE_SUFFIX)
    ]
    for service in services:
        try:
            await hass.services.async_call("esphome", service, {"bands": bands}, blocking=True)
        except Exception:  # noqa: BLE001 - one offline reader shouldn't stop the rest
            _LOGGER.warning("Couldn't update reader via esphome.%s", service, exc_info=True)
    _LOGGER.debug("Synced %d allowed band(s) to %d reader(s)", len(registry.allowed_uids()), len(services))
    return len(services)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def _get_registry(hass: HomeAssistant) -> MagicBandRegistry:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("MagicBand isn't set up")
    return entries[0].runtime_data.registry


def _resolve_band(registry: MagicBandRegistry, value: str) -> str:
    if value.strip().lower() == "last":
        band = registry.last_band
        if band is None:
            raise ServiceValidationError("No band has been scanned yet")
        return band.uid
    return value


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
        registry.assign_band(uid, person.id, call.data.get(ATTR_LABEL))
        persistent_notification.async_dismiss(hass, f"{DOMAIN}_unknown_{registry.get_band(uid).uid}")

    async def unassign_band(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        registry.assign_band(_resolve_band(registry, call.data[ATTR_BAND]), None)

    async def remove_band(call: ServiceCall) -> None:
        registry = _get_registry(hass)
        registry.remove_band(_resolve_band(registry, call.data[ATTR_BAND]))

    async def sync(call: ServiceCall) -> dict[str, Any]:
        return {"readers": await async_sync_readers(hass, _get_registry(hass))}

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
            "bands": [_band_dict(registry, b) for b in registry.bands],
        }

    hass.services.async_register(
        DOMAIN,
        "add_person",
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
    hass.services.async_register(
        DOMAIN,
        "update_person",
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
    hass.services.async_register(
        DOMAIN, "remove_person", remove_person, vol.Schema({vol.Required(ATTR_PERSON): cv.string})
    )
    hass.services.async_register(
        DOMAIN,
        "assign_band",
        assign_band,
        vol.Schema(
            {
                vol.Required(ATTR_BAND): cv.string,
                vol.Required(ATTR_PERSON): cv.string,
                vol.Optional(ATTR_LABEL): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN, "unassign_band", unassign_band, vol.Schema({vol.Required(ATTR_BAND): cv.string})
    )
    hass.services.async_register(
        DOMAIN, "remove_band", remove_band, vol.Schema({vol.Required(ATTR_BAND): cv.string})
    )
    hass.services.async_register(DOMAIN, "sync", sync, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "list", list_bands, supports_response=SupportsResponse.ONLY)

    async def send(call: ServiceCall) -> dict[str, Any]:
        bridges = await async_send(hass, dict(call.data))
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            entry.runtime_data.listener.note_send()
        return {"bridges": bridges}

    async def list_heard(call: ServiceCall) -> dict[str, Any]:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("MagicBand isn't set up")
        listener = entries[0].runtime_data.listener
        return {"listening": listener.active, "heard": listener.as_list(), "bands": listener.bands_list()}

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
    hass.services.async_register(DOMAIN, "list_heard", list_heard, supports_response=SupportsResponse.ONLY)


def _band_dict(registry: MagicBandRegistry, band: Band) -> dict[str, Any]:
    person = registry.get_person(band.person_id)
    return {
        "band": display_uid(band.uid),
        "label": band.label or None,
        "person": person.name if person else None,
        "allowed": registry.band_allowed(band.uid),
        "first_seen": band.first_seen,
        "last_seen": band.last_seen,
        "last_reader": band.last_reader,
        "scans": band.scans,
    }
