"""One device per physical band, whether it's known by NFC, Bluetooth or both.

A band tapped on a reader has an NFC ID; a MagicBand+ heard over Bluetooth
has a beacon signature (see beacons.py). Linking the two makes them one
band: its Bluetooth entities move onto the NFC band's device, and the empty
Bluetooth-only device is removed. Unlinking moves them back.

Device identifiers: ``band_<NFC ID>`` for any band with an NFC ID (linked or
not), ``bluetooth_<signature>`` for a Bluetooth band not linked to one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .beacons import BeaconTracker, BluetoothBand
from .const import DOMAIN, SIGNAL_BEACON, SIGNAL_BEACON_NEW, SIGNAL_UPDATED
from .registry import Band


def band_device_info(tracker: BeaconTracker, nfc: Band | None, ble: BluetoothBand | None) -> DeviceInfo:
    """Device for a physical band (at least one of nfc, ble is given)."""
    key = f"band_{nfc.uid}" if nfc is not None else f"bluetooth_{ble.id}"
    return DeviceInfo(
        identifiers={(DOMAIN, key)},
        name=tracker.band_name(nfc, ble),
        manufacturer="Disney",
        model="MagicBand+" if ble is not None else "MagicBand",
        serial_number=nfc.display if nfc is not None else ble.id.upper(),
    )


class BandEntity(Entity):
    """An entity of one physical band; keeps itself on the right device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, tracker: BeaconTracker, unique_id: str, key: str) -> None:
        self._tracker = tracker
        self._attr_unique_id = unique_id
        self._attr_translation_key = key

    def parts(self) -> tuple[Band | None, BluetoothBand | None]:
        """(NFC band, Bluetooth band) this entity belongs to."""
        raise NotImplementedError

    @property
    def device_info(self) -> DeviceInfo | None:
        nfc, ble = self.parts()
        return band_device_info(self._tracker, nfc, ble) if (nfc or ble) else None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_BEACON, self._refresh))
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._refresh))
        self._place()

    @callback
    def _refresh(self) -> None:
        self._place()
        self.async_write_ha_state()

    @callback
    def _place(self) -> None:
        """Move this entity to its band's current device (after a link or unlink), and keep its name."""
        if self.registry_entry is None or self.platform is None:
            return
        info = self.device_info
        if info is None:
            return
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_or_create(config_entry_id=self.platform.config_entry.entry_id, **info)
        old = self.registry_entry.device_id
        if old != device.id:
            old_device = dev_reg.async_get(old) if old else None
            # Linking a renamed Bluetooth band to its NFC band: keep the name you gave it.
            if (
                old_device is not None
                and old_device.name_by_user
                and not device.name_by_user
                and any(i[0] == DOMAIN and i[1].startswith("bluetooth_") for i in old_device.identifiers)
            ):
                device = dev_reg.async_update_device(device.id, name_by_user=old_device.name_by_user) or device
            er.async_get(self.hass).async_update_entity(self.entity_id, device_id=device.id)
            if old:
                remove_device_if_empty(self.hass, old)


@callback
def remove_device_if_empty(hass: HomeAssistant, device_id: str) -> None:
    """Remove a band device once no entity is left on it."""
    if not er.async_entries_for_device(er.async_get(hass), device_id, include_disabled_entities=True):
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if device and any(ident[1].startswith(("band_", "bluetooth_")) for ident in device.identifiers if ident[0] == DOMAIN):
            dev_reg.async_remove_device(device_id)


@callback
def async_setup_dynamic(
    hass: HomeAssistant,
    keys: Callable[[], Iterable[str]],
    make: Callable[[str], list[Entity]],
    prefix: Callable[[str], str],
    add: Callable[[list], None],
    signals: Iterable[str],
    on_unload: Callable[[Callable[[], None]], None],
) -> None:
    """Create entities for each key now and when keys appear; remove them when keys go."""
    known: set[str] = set()

    @callback
    def _sync() -> None:
        current = set(keys())
        new = current - known
        if new:
            add([entity for key in sorted(new) for entity in make(key)])
            known.update(new)
        gone = known - current
        if not gone:
            return
        ent_reg = er.async_get(hass)
        for key in gone:
            known.discard(key)
            for entity in list(ent_reg.entities.values()):
                if entity.platform == DOMAIN and (entity.unique_id or "").startswith(prefix(key)):
                    device_id = entity.device_id
                    ent_reg.async_remove(entity.entity_id)
                    if device_id:
                        remove_device_if_empty(hass, device_id)

    _sync()
    for signal in signals:
        on_unload(async_dispatcher_connect(hass, signal, _sync))


class BluetoothBandEntity(BandEntity):
    """An entity fed by a MagicBand+'s Bluetooth beacons."""

    def __init__(self, tracker: BeaconTracker, band_id: str, key: str) -> None:
        super().__init__(tracker, f"bluetooth_{band_id}_{key}", f"band_{key}")
        self._band_id = band_id

    @property
    def band(self) -> BluetoothBand | None:
        return self._tracker.bands.get(self._band_id)

    def parts(self) -> tuple[Band | None, BluetoothBand | None]:
        band = self.band
        return (self._tracker.linked_nfc(band), band) if band else (None, None)

    @property
    def available(self) -> bool:
        return self.band is not None


class NfcBandEntity(BandEntity):
    """An entity fed by a band's NFC taps on readers."""

    def __init__(self, tracker: BeaconTracker, uid: str, key: str) -> None:
        super().__init__(tracker, f"nfc_{uid}_{key}", f"band_{key}")
        self._uid = uid

    @property
    def nfc(self) -> Band | None:
        return self._tracker.registry.get_band(self._uid)

    def parts(self) -> tuple[Band | None, BluetoothBand | None]:
        nfc = self.nfc
        return (nfc, self._tracker.for_nfc(self._uid)) if nfc else (None, None)

    @property
    def available(self) -> bool:
        return self.nfc is not None


@callback
def async_setup_band_entities(
    hass: HomeAssistant,
    tracker: BeaconTracker,
    add: Callable[[list], None],
    bluetooth: list[Callable[[BeaconTracker, str], Entity]],
    nfc: list[Callable[[BeaconTracker, str], Entity]],
    on_unload: Callable[[Callable[[], None]], None],
) -> None:
    """Entities for every Bluetooth band and every NFC band, kept up to date."""
    if bluetooth:
        async_setup_dynamic(
            hass,
            lambda: tracker.bands,
            lambda band_id: [factory(tracker, band_id) for factory in bluetooth],
            lambda band_id: f"bluetooth_{band_id}_",
            add,
            [SIGNAL_BEACON_NEW],
            on_unload,
        )
    if nfc:
        async_setup_dynamic(
            hass,
            lambda: [b.uid for b in tracker.registry.bands],
            lambda uid: [factory(tracker, uid) for factory in nfc],
            lambda uid: f"nfc_{uid}_",
            add,
            [SIGNAL_UPDATED],
            on_unload,
        )
