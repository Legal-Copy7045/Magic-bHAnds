"""Hearing MagicBand+ Bluetooth traffic, scenes and the wake effect."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback

from custom_components.magicband.bridges import build_command
from custom_components.magicband.const import DOMAIN, EVENT_HEARD
from custom_components.magicband.listener import classify


def test_classify() -> None:
    assert classify(bytes.fromhex("E1 00 E9 05 00 2E 0E E5 B3")) == "command"
    assert classify(bytes.fromhex("E9 0C 00 0F 0F 5D 46 5B F0 05 32 37 48 B0")) == "command"
    assert classify(bytes.fromhex("E2 00 CC 03 00 01 00")) == "command"
    assert classify(bytes.fromhex("CC 03 00 00 00 12 34 56 78")) == "band"
    assert classify(bytes.fromhex("01 02 03")) == "band"


def test_scene_and_wake_commands() -> None:
    assert build_command({"effect": "animation", "animation": "spin_buzz_2", "vibration": 3}) == {
        "effect": "animation",
        "name": "spin_buzz_2",
    }
    assert build_command({"effect": "wake", "seconds": 10}) == {"effect": "wake", "seconds": 10}


async def test_heard_band_is_reported_after_send(hass: HomeAssistant, setup_integration) -> None:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    listener = entry.runtime_data.listener
    events = []
    hass.bus.async_listen(EVENT_HEARD, callback(lambda e: events.append(e)))  # on the loop, in order

    listener.note_send()
    listener.async_heard("AA:BB:CC:DD:EE:FF", None, -61, "proxy", bytes.fromhex("CC 03 00 00 00 12 34"))
    # The same thing again straight away is a repeat and isn't reported twice.
    assert listener.async_heard("AA:BB:CC:DD:EE:FF", None, -61, "proxy", bytes.fromhex("CC 03 00 00 00 12 34")) is None
    listener.async_heard("11:22:33:44:55:66", None, -70, "proxy", bytes.fromhex("E1 00 E9 0C 00 0F 0F"))
    await hass.async_block_till_done()

    assert [e.data["kind"] for e in events] == ["band", "command"]
    assert events[0].data["likely_response"] is True
    assert events[0].data["address"] == "AA:BB:CC:DD:EE:FF"

    state = hass.states.get("sensor.magicband_last_band_heard")
    assert state is not None and state.attributes["address"] == "AA:BB:CC:DD:EE:FF"
    assert state.attributes["rssi"] == -61

    result = await hass.services.async_call(DOMAIN, "list_heard", {}, blocking=True, return_response=True)
    assert [h["kind"] for h in result["heard"]] == ["command", "band"]
    assert [h["address"] for h in result["bands"]] == ["AA:BB:CC:DD:EE:FF"]


async def test_band_history_survives_many_commands(hass: HomeAssistant, setup_integration) -> None:
    listener = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.listener
    listener.async_heard("AA:BB:CC:DD:EE:01", None, -60, "proxy", bytes.fromhex("C0 0F 01 01 48 4A"))
    for i in range(100):  # far more commands than the 30-entry history
        listener.async_heard(f"11:22:33:44:55:{i:02X}", None, -60, "proxy", bytes.fromhex("E1 00 E9 05 00 80 0E FA BA"))
    await hass.async_block_till_done()
    assert all(h.kind == "command" for h in listener.history)
    assert [h.address for h in listener.bands] == ["AA:BB:CC:DD:EE:01"]
