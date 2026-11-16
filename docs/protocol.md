# MagicBand+ BLE protocol notes

MagicBand+ bands react to **BLE advertisements**. They don't use connections or
pairing. Park show equipment broadcasts manufacturer-specific data under Disney's
Bluetooth company ID **0x0183**, which goes over the air little-endian as `83 01`.

These notes summarise community reverse engineering, mainly the
[emcot.world MagicBand+ Bluetooth codes](https://emcot.world/Disney_MagicBand%2B_Bluetooth_Codes)
wiki, plus our own implementation choices. None of it is official, and a Disney
firmware update could change it. Things not yet tested on a real band by this
project are marked *(untested)*.

## Advertisement layout

```
02 01 06                 Flags AD
LL FF 83 01 <payload>    Manufacturer-specific AD, LL = 3 + len(payload)
```

Legacy advertisements are limited to 31 bytes, so the payload can be at most
**24 bytes**.

### `E1 00` / `E2 00` prefix
Captured packets sometimes start the payload with `E1 00` or `E2 00`. Bands
react without the prefix. But in our testing on a real MagicBand+, **switching
between `E1 00` and `E2 00` on each new command made repeated commands
noticeably more reliable** than sending the same bytes every time. That
suggests the prefix works as a toggle, letting the band tell a new command
from a repeat. The bridge alternates it by default (`alternate_prefix`).

## Common building blocks

### `E9 LL` effect opcode
`LL` is the number of bytes that follow. The byte after `LL` is always `00`
in the commands below.

### Timing byte
This is the byte after `E9 LL 00`.

| Bits | Meaning |
|------|---------|
| 7 | **Always on**: stay lit until the next command |
| 6 | Scaler: 0 → on time = 1.5 × v + 6.5 s; 1 → on time = 3.1 × v + 5.5 s |
| 5–4 | Fade-out: 0–3 seconds |
| 3–0 | `v`, the time value fed to the scaler |

Short on-times may show as two flashes with a gap. Captured defaults are `2E`
(about 27.5 s on, 2 s fade) and `22` (about 9.5 s, 2 s fade).
`MagicBand::timing(seconds, fade, always_on)` builds this byte.

### Vibration byte
`0xB0 | pattern`, usually the last byte. The `B` nibble enables colour and
vibration; other values disable vibration or change how the colour is chosen.

| Pattern | Feel | Pattern | Feel |
|---|---|---|---|
| 0 | none | 6 | `---***---`, 3 s gap |
| 1 | `-`, 6 s gap | 7 | `#`, 4 s gap |
| 2 | `--`, 6 s gap | 8 | `''''''`, 6 s gap |
| 3 | `---`, 6 s gap | 9 | `-`, 6 s gap |
| 4 | `--*`, 4 s gap | 10 | `*`, 6 s gap |
| 5 | `----*-`, 3 s gap | 11 | `%`, 5 s gap |
| 12–15 | none | | |

Legend: `'` = 0.125 s, `-` = 0.25 s, `*` = 0.5 s, `%` = 1 s, `#` = 2 s.

### Palette colour byte
Bits 4–0 hold the palette index. Bits 7–5 depend on the command. For a single
colour, they are an **LED mask**:

| Mask | LEDs | Mask | LEDs |
|---|---|---|---|
| 000 | all | 100 | top left only |
| 001 | top right only | 101 | all |
| 010 | bottom right only | 110 | top right only |
| 011 | bottom left only | 111 | all (what we send) |

### Palette (5-bit)

| Index | Colour | Index | Colour |
|---|---|---|---|
| 00 | cyan | 10 | off yellow |
| 01 | purple | 11 | yellow orange |
| 02 | blue | 12 | lime |
| 03 | midnight blue | 13 | orange |
| 04 | blue | 14 | red orange |
| 05 | bright purple | 15 | red |
| 06 | lavender | 16–18 | cyan |
| 07 | purple | 19 | green |
| 08–0E | pink | 1A | lime green |
| 0F | yellow orange | 1B, 1C | white |
| | | 1D | off |
| | | 1E | "unique" |
| | | 1F | random |

## Commands (payload after `83 01`)

| Command | Payload | Notes |
|---|---|---|
| Single colour | `E9 05 00 TT 0E (mask<<5 \| c) (B0\|v)` | `0E` is fixed, purpose unknown |
| Centre + outer | `E9 06 00 TT 0F (80\|inner) (80\|outer) (B0\|v)` | |
| **Any colour (RGB)** | `E9 08 00 TT D2 55 RR GG BB (B0\|v)` | each channel: bit 7 = flash, bits 6–1 = 6-bit level; `D2 55` fixed |
| Five colours | `E9 09 00 TT 0F (A0\|c)×5 (B0\|v)` | order: centre, top right, bottom right, bottom left, top left |
| Circle | `E9 0B 0B 0F 0F 5C 5D 48 A5 D1 45 32 (B0\|v)` | |
| Animations | `E9 0C 00 …` | captured show packets, see below |
| Crossfade | `E1 00 E9 11 00 6F 0F (40\|c1) (40\|c2) 58 F4 48 82 D1 46 02 08 D0 65 00 (B0\|v)` | |
| Spin + buzz | `E9 12 00 01 0F BC BD BD BD BD 30 D0 37 F4 D2 46 00 00 FC BB` | |
| Ping | `CC 03 00 00 00` | seen everywhere in parks |
| Fast ping | `CC 03 00 01 00` | believed to switch bands to quicker response *(untested)* |

RGB levels are not balanced: green appears dimmer than red or blue at low
values, and the effect varies with battery level.

### Captured animations (`send_animation(name)`)

| Name | Payload |
|---|---|
| `lightning` | `E9 0C 00 0F 0F 5D 46 5B F0 05 32 37 48 95` |
| `orange_blink` | `E9 0C 00 EF 0F 4F 4F 5B F0 FB 14 37 48 95` |
| `color_cycle` | `E9 0C 00 0F 0F B1 B9 B5 B1 A2 30 7B 7D B0` |
| `rainbow` | `E9 0C 00 0F 0F 5D 46 5B F0 05 32 37 48 B0` |
| `circle` | `E9 0B 0B 0F 0F 5C 5D 48 A5 D1 45 32 B0` |
| `crossfade` | `E1 00 E9 11 00 6F 0F 56 48 58 F4 48 82 D1 46 02 08 D0 65 00 B0` |
| `spin_buzz` | `E9 12 00 01 0F BC BD BD BD BD 30 D0 37 F4 D2 46 00 00 FC BB` |
| `show_e913` | `E9 13 00 B6 0F 40 44 58 F4 48 82 D0 65 19 D1 46 06 0A 30 7B FF` |

The wiki lists more captures for opcodes `E9 0E`, `0F`, `10` and `14`. Those
aren't decoded yet, but you can try them with the `raw` action.

## Not possible with broadcasts

The Disney app talks to a specific band over a GATT connection, acting as an
"Alexa Gadget". It can upload frame-based custom animations, but it needs BLE
tokens from Disney's servers. Broadcasts reach every band in range and can't
target one band.

## Tested on a real band

- Single colour, RGB light and animation commands work.
- Range improves a lot when the bridge isn't also scanning flat out as a
  Bluetooth proxy (the bridge now pauses scanning while broadcasting), and
  with +20 dBm on ESP32-S3.
- Alternating `E1 00` / `E2 00` makes repeated commands more reliable.

## Things to test on a real band

- Whether always-on (`TT` = `80`) holds the colour indefinitely, and whether
  "off" (`1D`) clears it.
- Whether the RGB command matches the colours in the HA colour picker.
- Whether the fast ping makes a sleeping band respond sooner.
- Whether a colour of `off` plus a vibration pattern gives "vibrate only".
- What the unnamed captures (`show_e913`, `E9 0E`/`0F`/`10`/`14`) look like.
