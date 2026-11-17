"""Hear MagicBand+ Bluetooth traffic through Home Assistant's Bluetooth.

Every Bluetooth adapter and proxy Home Assistant has (including MagicBand
bridges with their Bluetooth proxy switched on, and the SCREEK BP2-POE)
reports advertisements with Disney's company ID (0x0183). Each one is sorted
into:

- "command": an effect or ping (E9 ... / CC 03 xx xx xx), i.e. a bridge (or a
  park) talking to bands. Useful to see which proxies can hear a bridge.
- "band": anything else with Disney's ID, e.g. a band answering a ping.

Each is logged, fired as a ``magicband_heard`` event and kept in a short
history (the "Last band heard" sensor and ``magicband.list_heard``), with how
long after the last ``magicband.send`` it arrived.

MagicBand+ bands may use rotating (private) Bluetooth addresses, so the same
band can show up under different addresses over time.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import DISNEY_COMPANY_ID, EVENT_HEARD, SIGNAL_HEARD

_LOGGER = logging.getLogger(__name__)

HISTORY = 30
# Don't repeat an event for the same address and data more often than this.
REPEAT_SECONDS = 5.0
# A band heard this soon after a send is reported as a likely response.
RESPONSE_WINDOW_SECONDS = 15.0


def classify(payload: bytes) -> str:
    """'command' for effects/pings (from a bridge or a park), 'band' otherwise."""
    p = payload
    if len(p) >= 2 and p[0] in (0xE1, 0xE2) and p[1] == 0x00:
        p = p[2:]
    if p[:1] == b"\xe9":
        return "command"
    if p[:2] == b"\xcc\x03" and len(p) == 5:
        return "command"
    return "band"


@dataclass
class Heard:
    address: str
    name: str | None
    rssi: int
    source: str
    payload: str
    kind: str
    time: str
    after_send: float | None


class BandListener:
    """Collects Disney-ID advertisements heard by Home Assistant's Bluetooth."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.history: deque[Heard] = deque(maxlen=HISTORY)
        self.last_band: Heard | None = None
        self._last_send: float | None = None
        self._last_fired: dict[tuple[str, str], float] = {}
        self.active = False

    @callback
    def note_send(self) -> None:
        self._last_send = time.monotonic()

    def _source_name(self, source: str) -> str:
        try:
            from homeassistant.components import bluetooth

            scanner = bluetooth.async_scanner_by_source(self.hass, source)
            if scanner is not None and getattr(scanner, "name", None):
                return scanner.name
        except Exception:  # noqa: BLE001 - name is cosmetic
            pass
        return source

    @callback
    def async_heard(self, address: str, name: str | None, rssi: int, source: str, payload: bytes) -> Heard | None:
        """Record one advertisement. Returns the entry, or None if it was a repeat."""
        now = time.monotonic()
        hexed = payload.hex(" ").upper()
        key = (address, hexed)
        if now - self._last_fired.get(key, -1e9) < REPEAT_SECONDS:
            return None
        self._last_fired[key] = now
        if len(self._last_fired) > 500:
            cutoff = now - REPEAT_SECONDS
            self._last_fired = {k: v for k, v in self._last_fired.items() if v >= cutoff}

        after = round(now - self._last_send, 1) if self._last_send is not None else None
        heard = Heard(
            address=address,
            name=name if name and name != address else None,
            rssi=rssi,
            source=self._source_name(source),
            payload=hexed,
            kind=classify(payload),
            time=dt_util.utcnow().isoformat(),
            after_send=after,
        )
        self.history.appendleft(heard)
        recent = after is not None and after <= RESPONSE_WINDOW_SECONDS
        if heard.kind == "band":
            self.last_band = heard
            _LOGGER.info(
                "%s %s (RSSI %s) via %s: 83 01 %s%s",
                "Response from" if recent else "Heard",
                address,
                rssi,
                heard.source,
                hexed,
                f", {after}s after the last send" if recent else "",
            )
        else:
            _LOGGER.debug("Command heard by %s from %s (RSSI %s): 83 01 %s", heard.source, address, rssi, hexed)
        self.hass.bus.async_fire(EVENT_HEARD, {**asdict(heard), "likely_response": recent and heard.kind == "band"})
        async_dispatcher_send(self.hass, SIGNAL_HEARD)
        return heard

    def async_start(self) -> callable | None:
        """Start listening if Home Assistant's Bluetooth is set up."""
        if "bluetooth" not in self.hass.config.components:
            _LOGGER.debug("Bluetooth isn't set up; not listening for MagicBand+ responses")
            return None
        from homeassistant.components import bluetooth

        @callback
        def _on_adv(info: Any, _change: Any) -> None:
            payload = info.manufacturer_data.get(DISNEY_COMPANY_ID)
            if payload is not None:
                self.async_heard(info.address, info.name, info.rssi, info.source, bytes(payload))

        unsub = bluetooth.async_register_callback(
            self.hass,
            _on_adv,
            bluetooth.BluetoothCallbackMatcher(manufacturer_id=DISNEY_COMPANY_ID),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
        self.active = True
        return unsub

    def as_list(self) -> list[dict[str, Any]]:
        return [asdict(h) for h in self.history]
