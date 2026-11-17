"""Sensors: last tap overall, last tap per person, unknown bands."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import MagicBandConfigEntry
from .const import DOMAIN, SIGNAL_HEARD, SIGNAL_UPDATED
from .band_entity import BluetoothBandEntity, async_setup_band_entities
from .beacons import BeaconTracker
from .registry import MagicBandRegistry


def _device(entry: MagicBandConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="MagicBand",
        manufacturer="Magic bHAnds",
        entry_type=DeviceEntryType.SERVICE,
    )


def _ts(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


async def async_setup_entry(
    hass: HomeAssistant, entry: MagicBandConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    registry = entry.runtime_data.registry
    async_add_entities(
        [LastTapSensor(entry, registry), UnknownBandsSensor(entry, registry), LastHeardSensor(entry, registry)]
    )

    known: dict[str, PersonLastTapSensor] = {}

    @callback
    def _sync_people() -> None:
        current = {p.id for p in registry.people}
        new = [PersonLastTapSensor(entry, registry, pid) for pid in current - known.keys()]
        for sensor in new:
            known[sensor.person_id] = sensor
        if new:
            async_add_entities(new)
        ent_reg = er.async_get(hass)
        for pid in list(known.keys() - current):
            sensor = known.pop(pid)
            if sensor.entity_id and ent_reg.async_get(sensor.entity_id):
                ent_reg.async_remove(sensor.entity_id)

    _sync_people()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATED, _sync_people))

    async_setup_band_entities(
        hass,
        entry.runtime_data.beacons,
        async_add_entities,
        [BandLastSeenSensor, BandSignalSensor, BandBatterySensor],
        entry.async_on_unload,
    )


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: MagicBandConfigEntry, registry: MagicBandRegistry) -> None:
        self._registry = registry
        self._attr_device_info = _device(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self.async_write_ha_state))


class LastTapSensor(_Base):
    """When a band was last tapped, and whose."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_tap"
    _attr_icon = "mdi:nfc-variant"

    def __init__(self, entry, registry) -> None:
        super().__init__(entry, registry)
        self._attr_unique_id = f"{entry.entry_id}_last_tap"

    @property
    def native_value(self) -> datetime | None:
        band = self._registry.last_band
        return _ts(band.last_seen) if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        band = self._registry.last_band
        if band is None:
            return {}
        person = self._registry.get_person(band.person_id)
        return {
            "band": band.display,
            "label": band.label or None,
            "person": person.name if person else None,
            "ha_person": person.ha_person if person else None,
            "allowed": self._registry.band_allowed(band.uid),
            "reader": band.last_reader,
        }


class UnknownBandsSensor(_Base):
    """Bands that have been seen but don't belong to anyone yet."""

    _attr_translation_key = "unknown_bands"
    _attr_icon = "mdi:help-circle-outline"
    _attr_native_unit_of_measurement = "bands"

    def __init__(self, entry, registry) -> None:
        super().__init__(entry, registry)
        self._attr_unique_id = f"{entry.entry_id}_unknown_bands"

    @property
    def native_value(self) -> int:
        return len(self._registry.unassigned_bands)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "bands": [
                {"band": b.display, "last_seen": b.last_seen, "reader": b.last_reader, "scans": b.scans}
                for b in self._registry.unassigned_bands[:20]
            ]
        }


class PersonLastTapSensor(_Base):
    """When this person last tapped any of their bands."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:account-clock"

    def __init__(self, entry, registry, person_id: str) -> None:
        super().__init__(entry, registry)
        self.person_id = person_id
        self._attr_unique_id = f"{entry.entry_id}_person_{person_id}_last_tap"

    @property
    def name(self) -> str:
        person = self._registry.get_person(self.person_id)
        return f"{person.name} last tap" if person else "Last tap"

    @property
    def available(self) -> bool:
        return self._registry.get_person(self.person_id) is not None

    def _latest(self):
        bands = [b for b in self._registry.bands_for(self.person_id) if b.last_seen]
        return max(bands, key=lambda b: b.last_seen) if bands else None

    @property
    def native_value(self) -> datetime | None:
        band = self._latest()
        return _ts(band.last_seen) if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        person = self._registry.get_person(self.person_id)
        if person is None:
            return {}
        band = self._latest()
        return {
            "ha_person": person.ha_person,
            "allowed": person.allowed,
            "bands": [
                {"band": b.display, "label": b.label or None} for b in self._registry.bands_for(self.person_id)
            ],
            "last_band": band.display if band else None,
            "last_reader": band.last_reader if band else None,
        }


class LastHeardSensor(_Base):
    """The last MagicBand+ Bluetooth response heard (through HA's Bluetooth)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_heard"
    _attr_icon = "mdi:bluetooth-audio"

    def __init__(self, entry, registry) -> None:
        super().__init__(entry, registry)
        self._listener = entry.runtime_data.listener
        self._attr_unique_id = f"{entry.entry_id}_last_heard"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_HEARD, self.async_write_ha_state))

    @property
    def native_value(self) -> datetime | None:
        heard = self._listener.last_band
        return _ts(heard.time) if heard else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        heard = self._listener.last_band
        attrs: dict[str, Any] = {"listening": self._listener.active}
        if heard:
            attrs.update(
                address=heard.address,
                rssi=heard.rssi,
                heard_by=heard.source,
                payload=heard.payload,
                seconds_after_send=heard.after_send,
            )
        return attrs


# ---------------------------------------------------------------------------
# Per MagicBand+ (Bluetooth beacons)
# ---------------------------------------------------------------------------


class BandLastSeenSensor(BluetoothBandEntity, SensorEntity):
    """When the band's beacon was last heard, and by which adapter or proxy."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, tracker: BeaconTracker, band_id: str) -> None:
        super().__init__(tracker, band_id, "last_seen")

    @property
    def native_value(self) -> datetime | None:
        band = self.band
        return _ts(band.last_seen) if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        band = self.band
        if band is None:
            return {}
        person, nfc = self._tracker.owner(band)
        return {
            "person": person.name if person else None,
            "band": nfc.display if nfc else None,
            "heard_by": band.last_source,
            "beacons": band.beacons,
            "first_seen": band.first_seen,
            "payload": band.last_payload,
        }


class BandSignalSensor(BluetoothBandEntity, SensorEntity):
    """Signal strength of the band's last beacon."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, tracker: BeaconTracker, band_id: str) -> None:
        super().__init__(tracker, band_id, "signal")

    @property
    def native_value(self) -> int | None:
        band = self.band
        return band.last_rssi if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        band = self.band
        return {"heard_by": band.last_source, "by_source": band.rssi_by_source} if band else {}


class BandBatterySensor(BluetoothBandEntity, SensorEntity):
    """The beacon's level byte, which looks like the battery percentage (unconfirmed)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-unknown"

    def __init__(self, tracker: BeaconTracker, band_id: str) -> None:
        super().__init__(tracker, band_id, "battery")

    @property
    def native_value(self) -> int | None:
        band = self.band
        return band.battery if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        band = self.band
        if band is None:
            return {}
        return {
            "raw": f"0x{band.level:02X}" if band.level is not None else None,
            "changes": band.level_history[-10:],
            "note": "Unconfirmed: the beacon byte that only goes down. A full charge returning it to 100 would confirm it.",
        }
