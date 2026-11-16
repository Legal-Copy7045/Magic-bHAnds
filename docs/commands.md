# Bridge commands (JSON)

Each bridge has a **Command** text entity, e.g.
`text.magicband_bridge_3fa2c1_command`. Setting its value to a JSON object
makes the bridge broadcast that command. Because it's an ordinary entity, one
`text.set_value` call can target one bridge, several, or all of them:

```yaml
action: text.set_value
target:
  entity_id:
    - text.magicband_bridge_3fa2c1_command
    - text.magicband_bridge_aa11bb_command
data:
  value: 'mb{"effect": "color", "color": "red", "vibration": 3}'
```

Everything before the first `{` is ignored. The `mb` prefix matters when the
value comes from a template: without it, Home Assistant turns JSON-looking
template output into a dict, and the bridge receives something it can't parse.
`script.magicband_send` in `homeassistant/magicband_scripts.yaml` adds the
prefix for you and defaults to all bridges.

The value can be at most 255 characters.

## Fields

| `effect` | Other fields |
|---|---|
| `color` (default) | `color`, `vibration`, `leds`, `on_seconds`, `fade_seconds`, `always_on` |
| `rgb` | `rgb` as `[r, g, b]`, or `red`/`green`/`blue` (0–255), `vibration`, `flash`, `on_seconds`, `fade_seconds`, `always_on` |
| `dual_color` | `inner`, `outer`, `vibration`, `on_seconds`, `fade_seconds`, `always_on` |
| `five_color` | `colors` ("centre, top right, bottom right, bottom left, top left"), `vibration`, timing fields |
| `crossfade` | `color1`, `color2`, `vibration` |
| `circle` | `vibration` |
| `animation` | `name`: lightning, orange_blink, color_cycle, rainbow, circle, crossfade, spin_buzz, show_e913 |
| `buzz` | `vibration` (vibrate without lights) |
| `ping` | `fast` (bool) |
| `off` | none |
| `raw` | `hex` |
| `stop` | none |

These fields work with any effect:

- `vibration`: 0 (none) or a pattern from 1 to 11.
- `duration_ms`: how long the bridge broadcasts. 0 uses the default of 2 s.
- `on_seconds`, `fade_seconds`, `always_on`: control how long the band stays
  lit. If `on_seconds` is 0 and `always_on` is false, the band uses its
  captured default timing.
- `leds`: `all`, `top_left`, `top_right`, `bottom_left` or `bottom_right`
  (single colour only).

Colours accept palette names (`red`, `pink`, `lime_green`, …) or numbers
0–31. See [protocol.md](protocol.md).
