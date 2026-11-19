"""Diagnostics download (Settings → Devices & services → MagicbHAnds → ⋮ → Download diagnostics).

Band IDs are what's needed to copy a band, so they're shortened to their last
four characters; names of people are replaced by placeholders, and Bluetooth
signatures and raw beacons are left out.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import MagicBandConfigEntry, enrolment_state
from .registry import display_uid


def _short(uid: str | None) -> str | None:
    return f"…{display_uid(uid)[-5:]}" if uid else None


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: MagicBandConfigEntry) -> dict[str, Any]:
    data = entry.runtime_data
    registry, beacons = data.registry, data.beacons
    people = {p.id: f"person {i + 1}" for i, p in enumerate(registry.people)}
    return {
        "options": dict(entry.options),
        "people": [
            {"name": people[p.id], "allowed": p.allowed, "ha_person": bool(p.ha_person), "welcome_colour": p.welcome_colour,
             "bands": len(registry.bands_for(p.id))}
            for p in registry.people
        ],
        "bands": [
            {
                "band": _short(b.uid),
                "owner": people.get(b.person_id) if b.person_id else None,
                "allowed": registry.band_allowed(b.uid),
                "type": b.band_type,
                "scans": b.scans,
                "last_seen": b.last_seen,
                "schedule": {"expires": b.expires, "from": b.access_from, "until": b.access_until, "days": b.access_days}
                if b.has_schedule
                else None,
                "bluetooth_linked": beacons.for_nfc(b.uid) is not None,
            }
            for b in registry.bands
        ],
        "allowed_count": len(registry.allowed_uids()),
        "bluetooth_bands": [
            {
                "band": f"bt {i + 1}",
                "owner": people.get(beacons.owner(b)[0].id) if beacons.owner(b)[0] else None,
                "linked": b.band_uid is not None,
                "battery": b.battery,
                "battery_low": b.battery_low,
                "beacons": b.beacons,
                "forms": b.forms,
                "last_seen": b.last_seen,
                "nearby": b.nearby(),
            }
            for i, b in enumerate(beacons.bands.values())
        ],
        "encrypted_messages": len(beacons.encrypted),
        "readers": [{**s, "device_id": "…" + s["device_id"][-4:]} for s in data.readers.report()],
        "enrolment": {**state, "person": "set"} if (state := enrolment_state(data)) else None,
        "listener": {"active": data.listener.active, "heard": len(data.listener.history),
                     "events_dropped": data.listener.events_dropped},
        "history_taps": len(data.history.taps),
    }
