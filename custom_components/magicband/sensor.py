"""Sensors: last tap overall, last tap per person, unknown bands."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import MagicBandConfigEntry, is_reader_device
from .const import DOMAIN, SIGNAL_BEACON, SIGNAL_HEARD, SIGNAL_READER_TAP, SIGNAL_UPDATED
from .band_entity import BluetoothBandEntity, NfcBandEntity, async_setup_band_entities
from .beacons import CLOSEST_WINDOW, BeaconTracker, adapter_name
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

    # "Last band name" on every reader's own device page.
    readers: dict[str, ReaderLastBandSensor] = {}

    @callback
    def _add_reader(device_id: str) -> None:
        if device_id in readers or not is_reader_device(hass, device_id):
            return
        device = dr.async_get(hass).async_get(device_id)
        if device is None or not device.connections:
            return
        readers[device_id] = ReaderLastBandSensor(entry, device)
        async_add_entities([readers[device_id]])

    for device in list(dr.async_get(hass).devices.values()):
        _add_reader(device.id)

    @callback
    def _on_tap(device_id: str, uid: str, allowed: bool) -> None:
        _add_reader(device_id)
        if (sensor := readers.get(device_id)) is not None:
            sensor.tapped(uid, allowed)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_READER_TAP, _on_tap))

    async_setup_band_entities(
        hass,
        entry.runtime_data.beacons,
        async_add_entities,
        [BandLastSeenSensor, BandHeardBySensor, BandClosestSensor, BandSignalSensor, BandBatterySensor],
        [BandLastTapSensor],
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
            "heard_by": adapter_name(self.hass, band.last_source),
            "beacons": band.beacons,
            "first_seen": band.first_seen,
            "payload": band.last_payload,
        }


class BandHeardBySensor(BluetoothBandEntity, SensorEntity):
    """Which bridge, proxy or adapter heard the band's latest beacon."""

    _attr_icon = "mdi:access-point"

    def __init__(self, tracker: BeaconTracker, band_id: str) -> None:
        super().__init__(tracker, band_id, "heard_by")

    @property
    def native_value(self) -> str | None:
        band = self.band
        return adapter_name(self.hass, band.last_source) if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        band = self.band
        return {"rssi": band.last_rssi, "at": band.last_seen} if band else {}


class BandClosestSensor(BluetoothBandEntity, SensorEntity):
    """The bridge, proxy or adapter that heard the band strongest in the last 20 minutes."""

    _attr_icon = "mdi:map-marker-radius"

    def __init__(self, tracker: BeaconTracker, band_id: str) -> None:
        super().__init__(tracker, band_id, "closest")

    @property
    def native_value(self) -> str | None:
        band = self.band
        return adapter_name(self.hass, band.closest()[0]) if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        band = self.band
        if band is None:
            return {}
        now = dt_util.utcnow()
        recent = {
            adapter_name(self.hass, s) or s: rssi
            for s, (rssi, when) in band.heard.items()
            if (seen := dt_util.parse_datetime(when)) is not None and now - seen <= CLOSEST_WINDOW
        }
        return {"rssi": band.closest()[1], "heard_in_last_20_minutes": dict(sorted(recent.items(), key=lambda kv: -kv[1]))}


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
        if band is None:
            return {}
        return {
            "heard_by": adapter_name(self.hass, band.last_source),
            "by_source": {adapter_name(self.hass, s) or s: r for s, r in band.rssi_by_source.items()},
        }


class BandBatterySensor(BluetoothBandEntity, SensorEntity):
    """Battery level, from the beacon's level byte (confirmed by charging bands)."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

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
        }


class BandLastTapSensor(NfcBandEntity, SensorEntity):
    """When this band was last tapped on a reader, and its NFC details."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:nfc-variant"

    def __init__(self, tracker: BeaconTracker, uid: str) -> None:
        super().__init__(tracker, uid, "last_tap")

    @property
    def native_value(self) -> datetime | None:
        nfc = self.nfc
        return _ts(nfc.last_seen) if nfc else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nfc = self.nfc
        if nfc is None:
            return {}
        registry = self._tracker.registry
        person = registry.get_person(nfc.person_id)
        ble = self._tracker.for_nfc(nfc.uid)
        return {
            "band": nfc.display,
            "label": nfc.label or None,
            "person": person.name if person else None,
            "ha_person": person.ha_person if person else None,
            "allowed": registry.band_allowed(nfc.uid),
            "reader": nfc.last_reader,
            "scans": nfc.scans,
            "first_seen": nfc.first_seen,
            "bluetooth_band": ble.id if ble else None,
        }


class ReaderLastBandSensor(RestoreSensor):
    """The name of the last band tapped on this reader, on the reader's own device page."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "reader_last_band"
    _attr_icon = "mdi:account-badge"

    def __init__(self, entry: MagicBandConfigEntry, device: dr.DeviceEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"reader_{device.id}_last_band"
        # Matching the reader's connections puts this entity on the reader's device.
        self._attr_device_info = DeviceInfo(connections=set(device.connections))
        self._uid: str | None = None
        self._allowed: bool | None = None
        self._at: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._uid = last.attributes.get("band_id")
            self._allowed = last.attributes.get("allowed")
            self._at = last.attributes.get("at")
        for signal in (SIGNAL_UPDATED, SIGNAL_BEACON):
            self.async_on_remove(async_dispatcher_connect(self.hass, signal, self.async_write_ha_state))

    @callback
    def tapped(self, uid: str, allowed: bool) -> None:
        self._uid, self._allowed, self._at = uid, allowed, dt_util.utcnow().isoformat()
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        if self._uid is None:
            return None
        return self._entry.runtime_data.beacons.band_display_name(self._uid)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._uid is None:
            return {}
        registry = self._entry.runtime_data.registry
        band = registry.get_band(self._uid)
        person = registry.get_person(band.person_id) if band else None
        return {
            "band_id": self._uid,
            "band": band.display if band else self._uid,
            "person": person.name if person else None,
            "allowed": self._allowed,
            "at": self._at,
        }
