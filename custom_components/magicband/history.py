"""A short history of taps on the readers, kept in Home Assistant's storage.

Shown on the management page (admins only, through ``magicband.history``).
Taps also appear in Home Assistant's logbook (see logbook.py), which keeps
them as long as the recorder does; this keeps the last few hundred with the
band's name and owner as they were at the time.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

STORE_KEY = "magicband.history"
STORE_VERSION = 1
MAX_TAPS = 300


class TapHistory:
    """The last MAX_TAPS taps, newest first."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict] = Store(hass, STORE_VERSION, STORE_KEY)
        self.taps: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        taps = raw.get("taps", []) if isinstance(raw, dict) else []
        self.taps = [t for t in taps if isinstance(t, dict)][:MAX_TAPS]

    @callback
    def add(self, **tap: Any) -> None:
        tap.setdefault("time", dt_util.utcnow().isoformat())
        self.taps = [tap, *self.taps][:MAX_TAPS]
        self._store.async_delay_save(lambda: {"taps": self.taps}, 5.0)

    async def async_flush(self) -> None:
        await self._store.async_save({"taps": self.taps})

    def recent(self, count: int = 50) -> list[dict[str, Any]]:
        return self.taps[: max(0, count)]
