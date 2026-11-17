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
| `animation` (or `scene`) | `name`: a [scene](#scenes), e.g. `rainbow`, `crossfade_3`, `spin_buzz_2` |
| `buzz` | `vibration` (vibrate without lights) |
| `ping` | `fast` (bool) |
| `wake` | `seconds` (default 15): the fast-mode ping on its own, so bands respond quickly to what follows |
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

## Scenes

Predefined scenes are captured park packets. Use the id with the `animation`
effect, `magicband.send` (`effect: animation`), or the bridge's `animation`
action; the **Scene** select on the device uses the labels. Labels work as
names too ("Spin & buzz 2"). Labels are descriptive guesses: the `Show …`
scenes are captures nobody has described yet, so try them and see.

| Id | Label | Payload (after `83 01`, before the `E1 00`/`E2 00` prefix) |
|---|---|---|
| `lightning` | Lightning | `E9 0C 00 0F 0F 5D 46 5B F0 05 32 37 48 95` |
| `orange_blink` | Orange blink | `E9 0C 00 EF 0F 4F 4F 5B F0 FB 14 37 48 95` |
| `color_cycle` | Color cycle | `E9 0C 00 0F 0F B1 B9 B5 B1 A2 30 7B 7D B0` |
| `rainbow` | Rainbow | `E9 0C 00 0F 0F 5D 46 5B F0 05 32 37 48 B0` |
| `circle` | Circle | `E9 0B 0B 0F 0F 5C 5D 48 A5 D1 45 32 B0` |
| `alternating` | Alternating | `E9 10 00 13 48 97 D0 0E A0 D1 46 06 0F 30 D0 4E 07 B0` |
| `crossfade` | Crossfade | `E9 11 00 6F 0F 56 48 58 F4 48 82 D1 46 02 08 D0 65 00 B0` |
| `crossfade_2` | Crossfade 2 | `E9 11 00 4F 0F 44 4F 58 F4 48 82 D1 46 06 07 D0 65 43 B0` |
| `crossfade_3` | Crossfade 3 | `E9 11 00 0F 0F 48 59 58 F4 48 82 D1 46 02 0D D0 65 05 B0` |
| `crossfade_4` | Crossfade 4 | `E9 11 00 4F 0F 4F 55 58 F4 48 82 D1 46 02 2A D0 65 01 B0` |
| `crossfade_5` | Crossfade 5 | `E9 11 00 01 0F 5A 47 5B F0 31 34 37 48 94 D1 3D 05 07 B0` |
| `crossfade_6` | Crossfade 6 | `E9 11 00 07 0F 55 5D 58 F4 48 82 D1 46 05 08 D0 65 00 B0` |
| `crossfade_7` | Crossfade 7 | `E9 11 00 44 0F 51 42 58 F4 48 82 D1 46 05 0F D0 65 00 B0` |
| `spin_buzz` | Spin & buzz | `E9 12 00 01 0F BC BD BD BD BD 30 D0 37 F4 D2 46 00 00 FC BB` |
| `spin_buzz_2` | Spin & buzz 2 | `E9 12 00 01 29 04 02 02 11 11 48 96 D0 0E FF D1 46 07 07 B0` |
| `spin_buzz_3` | Spin & buzz 3 | `E9 12 00 03 0F A2 A2 A4 A4 A2 30 D0 37 F4 D2 46 00 64 FC B0` |
| `show_0e_1` | Show 0E 1 | `E9 0E 00 01 0F BD A0 A0 BD A0 59 07 00 48 AE B5` |
| `show_0e_2` | Show 0E 2 | `E9 0E 00 02 0F BC A0 BC A0 BC 59 17 FB 48 AE BB` |
| `show_0e_3` | Show 0E 3 | `E9 0E 00 11 0F BC A7 B9 A7 B9 59 19 02 48 AE B0` |
| `show_0e_4` | Show 0E 4 | `E9 0E 00 15 0F BB BB BB BB BB 59 19 02 48 AE B0` |
| `show_0e_5` | Show 0E 5 | `E9 0E 00 83 0F B5 B9 B2 AD B6 59 19 0B 48 AE B0` |
| `show_0f_1` | Show 0F 1 | `E9 0F 00 11 0F 4F 42 58 07 48 8D D2 46 2A 07 17 B8` |
| `show_0f_2` | Show 0F 2 | `E9 0F 00 2A 0F 46 43 58 12 48 8D D2 46 02 12 00 B0` |
| `show_e913` | Show 13 1 | `E9 13 00 B6 0F 40 44 58 F4 48 82 D0 65 19 D1 46 06 0A 30 7B FF` |
| `show_13_2` | Show 13 2 | `E9 13 00 02 D0 37 F0 D2 3D 05 05 00 0E FA 89 83 51 0E E7 A0 B0` |
| `show_13_3` | Show 13 3 | `E9 13 00 65 0F BD B5 BC B5 BC 7A EC 5C 0A 29 15 29 15 48 AB B0` |
| `show_14_1` | Show 14 1 | `E9 14 00 0C D0 37 F0 D2 3D 05 0C 0C 0E EC 89 83 51 0E EE 0C 3D B0` |
| `show_14_2` | Show 14 2 | `E9 14 00 2C D0 37 F0 D2 3D 02 12 00 0E EA 89 83 51 0E E3 0C 1E B0` |
| `show_14_3` | Show 14 3 | `E9 14 00 42 0F 55 5B 58 F4 48 82 D0 65 1B D1 46 2A 02 30 7B 5D B0` |
| `show_07_1` | Show 07 1 | `E9 07 00 22 0F 43 43 41 B0` |
| `show_07_2` | Show 07 2 | `E9 07 00 22 0F 44 44 41 B0` |

Sources: the [emcot.world code list](https://emcot.world/Disney_MagicBand%2B_Bluetooth_Codes)
and [Haw8411/magic-band-plus-lights](https://github.com/Haw8411/magic-band-plus-lights).
