"""Taps in Home Assistant's logbook: "Jackie's MagicBand: welcomed at Front Door"."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_TAP


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    @callback
    def describe_tap(event: Event) -> dict[str, Any]:
        data = event.data
        name = data.get("name") or (f"{data['person']}'s band" if data.get("person") else "An unknown band")
        where = f" at {data['reader']}" if data.get("reader") else ""
        if data.get("enrolled"):
            message = f"enrolled for {data.get('person')}{where}"
        else:
            message = ("welcomed" if data.get("allowed") else "denied") + where
        return {"name": name, "message": message}

    async_describe_event(DOMAIN, EVENT_TAP, describe_tap)
