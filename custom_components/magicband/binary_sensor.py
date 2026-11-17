"""Binary sensors: is each MagicBand+ nearby (heard recently over Bluetooth)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MagicBandConfigEntry
from .band_entity import BluetoothBandEntity, async_setup_band_entities
from .beacons import AWAY_AFTER, BeaconTracker


async def async_setup_entry(
    hass: HomeAssistant, entry: MagicBandConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_band_entities(
        hass, entry.runtime_data.beacons, async_add_entities, [NearbySensor], [], entry.async_on_unload
    )


class NearbySensor(BluetoothBandEntity, BinarySensorEntity):
    """On while the band's beacons are being heard."""

    _attr_device_class = BinarySensorDeviceClass.PRESENCE

    def __init__(self, tracker: BeaconTracker, band_id: str) -> None:
        super().__init__(tracker, band_id, "nearby")

    @property
    def is_on(self) -> bool | None:
        band = self.band
        return band.nearby() if band else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        band = self.band
        if band is None:
            return {}
        person, nfc = self._tracker.owner(band)
        return {
            "person": person.name if person else None,
            "band": nfc.display if nfc else None,
            "away_after_minutes": int(AWAY_AFTER.total_seconds() // 60),
        }
