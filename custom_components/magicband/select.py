"""Selects: what kind of band each tapped band is (MagicBand+ or a standard MagicBand)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MagicBandConfigEntry
from .band_entity import NfcBandEntity, async_setup_band_entities
from .beacons import BeaconTracker
from .const import SIGNAL_UPDATED

# shown state -> stored band_type ("unknown" means not said and never heard over Bluetooth)
OPTIONS = {"unknown": "auto", "plus": "plus", "classic": "classic"}


async def async_setup_entry(
    hass: HomeAssistant, entry: MagicBandConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_setup_band_entities(
        hass, entry.runtime_data.beacons, async_add_entities, [], [BandTypeSelect], entry.async_on_unload
    )


class BandTypeSelect(NfcBandEntity, SelectEntity):
    """MagicBand+ (has Bluetooth), standard MagicBand (NFC only), or not known yet.

    A band that's been linked to its Bluetooth beacons is a MagicBand+ on its
    own. Marking a band as a standard MagicBand stops the integration looking
    for its Bluetooth when it's tapped, and the management page stops listing
    it as "not heard over Bluetooth yet".
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:watch-variant"
    _attr_options = list(OPTIONS)

    def __init__(self, tracker: BeaconTracker, uid: str) -> None:
        super().__init__(tracker, uid, "type")

    @property
    def current_option(self) -> str | None:
        return self._tracker.band_type(self._uid) if self.nfc else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nfc = self.nfc
        if nfc is None:
            return {}
        return {
            "band_type_set_by": "you" if nfc.band_type != "auto" else ("bluetooth" if self.current_option == "plus" else None),
            "linked_to_bluetooth": self._tracker.for_nfc(self._uid) is not None,
        }

    async def async_select_option(self, option: str) -> None:
        self._tracker.registry.set_band_type(self._uid, OPTIONS[option])
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
