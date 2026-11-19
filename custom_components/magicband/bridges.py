"""Send effects to MagicBand bridges (ESPHome devices with the magicband add-on).

A bridge is an ESPHome device with a "Command" text entity and a "MagicBand"
light, both from esphome/magicband-addon.yaml. Commands are JSON strings set on
the Command entity; the firmware parses them (see docs/commands.md).
"""

from __future__ import annotations

from collections import deque
import json
import time
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

EFFECTS = [
    "color",
    "rgb",
    "dual_color",
    "five_color",
    "crossfade",
    "circle",
    "animation",
    "buzz",
    "ping",
    "wake",
    "off",
    "raw",
    "stop",
]
# Predefined scenes built into the firmware (see docs/commands.md#scenes).
ANIMATIONS = [
    "lightning",
    "orange_blink",
    "color_cycle",
    "rainbow",
    "circle",
    "alternating",
    "crossfade",
    "crossfade_2",
    "crossfade_3",
    "crossfade_4",
    "crossfade_5",
    "crossfade_6",
    "crossfade_7",
    "spin_buzz",
    "spin_buzz_2",
    "spin_buzz_3",
    "show_0e_1",
    "show_0e_2",
    "show_0e_3",
    "show_0e_4",
    "show_0e_5",
    "show_0f_1",
    "show_0f_2",
    "show_e913",
    "show_13_2",
    "show_13_3",
    "show_14_1",
    "show_14_2",
    "show_14_3",
    "show_07_1",
    "show_07_2",
]
MAX_COMMAND_LEN = 255  # the Command text entity's max length
# Each command makes a bridge broadcast (and may pause its Bluetooth proxy),
# so magicband.send accepts at most this many commands per bridge a minute.
# Far more than any automation or dashboard needs; it stops a loop or a user
# keeping every bridge transmitting.
MAX_SENDS_PER_MINUTE = 30
MAX_DURATION_MS = 30000  # also the limit on the duration_ms field
_SEND_TIMES = "magicband_send_times"


def _is_named(entry: er.RegistryEntry, name: str) -> bool:
    return (entry.original_name or "").lower() == name.lower() or entry.entity_id.split(".", 1)[1].endswith(
        "_" + name.lower()
    )


def find_bridges(hass: HomeAssistant) -> list[str]:
    """Command entity IDs of every MagicBand bridge, in a stable order."""
    ent_reg = er.async_get(hass)
    by_device: dict[str, list[er.RegistryEntry]] = {}
    for entry in ent_reg.entities.values():
        if entry.platform == "esphome" and entry.device_id and not entry.disabled:
            by_device.setdefault(entry.device_id, []).append(entry)
    bridges = []
    for entries in by_device.values():
        command = next((e for e in entries if e.domain == "text" and _is_named(e, "command")), None)
        has_light = any(e.domain == "light" and _is_named(e, "magicband") for e in entries)
        if command and has_light:
            bridges.append(command.entity_id)
    return sorted(bridges)


def build_command(data: dict[str, Any]) -> dict[str, Any]:
    """Turn the magicband.send fields into the firmware's JSON command."""
    if isinstance(data.get("command"), dict):
        cmd = dict(data["command"])  # raw command, passed through, within the same time limits
        for key, limit in (("duration_ms", MAX_DURATION_MS), ("seconds", 60)):
            value = cmd.get(key)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= limit):
                raise ServiceValidationError(f"command {key} must be a number from 0 to {limit}")
        return cmd
    effect = data.get("effect", "color")
    cmd: dict[str, Any] = {"effect": effect}

    def put(key: str, field: str | None = None) -> None:
        value = data.get(field or key)
        if value is not None and value != "":
            cmd[key] = value

    if effect in ("color", "dual_color", "crossfade"):
        put("color")
        put("color2")
    if effect == "color":
        put("leds")
    if effect == "five_color":
        put("colors")
    if effect == "rgb":
        rgb = data.get("rgb_color")
        if rgb is not None:
            cmd["rgb"] = [int(v) for v in rgb]
        put("flash")
    if effect == "animation":
        put("name", "animation")
    if effect == "ping":
        put("fast")
    if effect == "wake":
        put("seconds")
    if effect == "raw":
        put("hex")
    if effect in ("color", "rgb", "dual_color", "five_color"):
        put("on_seconds")
        put("fade_seconds")
        put("always_on")
    if effect not in ("ping", "wake", "off", "raw", "stop", "animation"):
        put("vibration")
    put("duration_ms")
    return cmd


async def async_send(hass: HomeAssistant, data: dict[str, Any], context: Context | None = None) -> list[str]:
    """Send one command to the chosen bridges (default: all). Returns the bridges used.

    Only MagicBand bridges' Command entities can be targeted: anything else in
    `bridges` is refused, so this can't be used to write other text entities.
    The write runs with the caller's context, so Home Assistant's own
    permissions and logbook see who sent it.
    """
    known = find_bridges(hass)
    wanted = list(dict.fromkeys(data.get("bridges") or []))
    if wanted:
        if unknown := [entity_id for entity_id in wanted if entity_id not in known]:
            raise ServiceValidationError(
                f"Not a MagicBand bridge's Command entity: {', '.join(unknown)}. "
                "magicband.list_bridges shows the bridges."
            )
        bridges = wanted
    else:
        bridges = known
    if not bridges:
        raise ServiceValidationError(
            "No MagicBand bridges found. Add a bridge (an ESPHome device with the magicband "
            "add-on) through the ESPHome integration first."
        )
    value = json.dumps(build_command(data), separators=(",", ":"))
    if len(value) > MAX_COMMAND_LEN:
        raise ServiceValidationError(f"Command is {len(value)} characters; the limit is {MAX_COMMAND_LEN}")
    now = time.monotonic()
    times: dict[str, deque[float]] = hass.data.setdefault(_SEND_TIMES, {})
    for entity_id in bridges:
        recent = times.setdefault(entity_id, deque())
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= MAX_SENDS_PER_MINUTE:
            raise ServiceValidationError(
                f"Too many commands to {entity_id}: at most {MAX_SENDS_PER_MINUTE} a minute per bridge"
            )
    for entity_id in bridges:
        times[entity_id].append(now)
    await hass.services.async_call(
        "text", "set_value", {"entity_id": bridges, "value": value}, blocking=True, context=context
    )
    return bridges
