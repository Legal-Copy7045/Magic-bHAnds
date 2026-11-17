"""Shared base for the entities of each Bluetooth band (see beacons.py)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .beacons import BeaconTracker, BluetoothBand
from .const import DOMAIN, SIGNAL_BEACON, SIGNAL_BEACON_NEW, SIGNAL_UPDATED


def device_identifier(band_id: str) -> tuple[str, str]:
    return (DOMAIN, f"bluetooth_{band_id}")


class BluetoothBandEntity(Entity):
    """An entity belonging to one MagicBand+, recognised by its beacons."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, tracker: BeaconTracker, band_id: str, key: str) -> None:
        self._tracker = tracker
        self._band_id = band_id
        self._attr_unique_id = f"bluetooth_{band_id}_{key}"
        self._attr_translation_key = f"band_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={device_identifier(band_id)},
            name=tracker.name(tracker.bands[band_id]),
            manufacturer="Disney",
            model="MagicBand+",
            serial_number=band_id.upper(),
        )

    @property
    def band(self) -> BluetoothBand | None:
        return self._tracker.bands.get(self._band_id)

    @property
    def available(self) -> bool:
        return self.band is not None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_BEACON, self._refresh))
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._refresh))

    @callback
    def _refresh(self) -> None:
        band = self.band
        if band is not None and self.device_entry is not None:
            # Keep the device's name in step with its owner (unless renamed by hand).
            name = self._tracker.name(band)
            if self.device_entry.name != name:
                dr.async_get(self.hass).async_update_device(self.device_entry.id, name=name)
        self.async_write_ha_state()


@callback
def async_setup_band_entities(
    hass: HomeAssistant,
    tracker: BeaconTracker,
    add: Callable[[list], None],
    factories: list[Callable[[BeaconTracker, str], Entity]],
    on_unload: Callable[[Callable[[], None]], None],
) -> None:
    """Create entities for every Bluetooth band now and as new ones are heard."""
    known: set[str] = set()

    @callback
    def _sync() -> None:
        current = set(tracker.bands)
        new = current - known
        if new:
            add([factory(tracker, band_id) for band_id in sorted(new) for factory in factories])
            known.update(new)
        ent_reg = er.async_get(hass)
        for band_id in known - current:
            known.discard(band_id)
            for entity in list(ent_reg.entities.values()):
                if entity.platform == DOMAIN and (entity.unique_id or "").startswith(f"bluetooth_{band_id}_"):
                    ent_reg.async_remove(entity.entity_id)

    _sync()
    on_unload(async_dispatcher_connect(hass, SIGNAL_BEACON_NEW, _sync))
