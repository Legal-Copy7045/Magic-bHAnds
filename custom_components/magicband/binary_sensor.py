"""Binary sensors: is each MagicBand+ nearby (heard recently over Bluetooth), and is the house in lockdown."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MagicBandConfigEntry
from .band_entity import BluetoothBandEntity, async_setup_band_entities
from .beacons import AWAY_AFTER, BeaconTracker
from .const import SIGNAL_UPDATED


async def async_setup_entry(
    hass: HomeAssistant, entry: MagicBandConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_band_entities(
        hass, entry.runtime_data.beacons, async_add_entities, [NearbySensor], [], entry.async_on_unload
    )
    async_add_entities([LockdownSensor(entry)])


class LockdownSensor(BinarySensorEntity):
    """On while the house is in lockdown: only people marked "Gets in during lockdown" are let in."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "lockdown"
    _attr_icon = "mdi:shield-lock"

    def __init__(self, entry: MagicBandConfigEntry) -> None:
        from .sensor import _device

        self._registry = entry.runtime_data.registry
        self._attr_unique_id = f"{entry.entry_id}_lockdown"
        self._attr_device_info = _device(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return bool(self._registry.lockdown_reasons())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cfg = self._registry.settings
        return {
            "reasons": self._registry.lockdown_reasons(),
            "manual": cfg["lockdown"],
            "when_nobody_home": cfg["lockdown_away"],
            "at_night": f"{cfg['lockdown_from']}-{cfg['lockdown_until']}" if cfg["lockdown_night"] else None,
            "alarm": cfg["lockdown_alarm"],
            "let_in": [p.name for p in self._registry.people if p.lockdown_exempt],
        }


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
