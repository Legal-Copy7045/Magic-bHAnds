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
| Scenes | `E9 07`…`E9 14` | captured show packets, see below |
| Crossfade | `E1 00 E9 11 00 6F 0F (40\|c1) (40\|c2) 58 F4 48 82 D1 46 02 08 D0 65 00 (B0\|v)` | |
| Spin + buzz | `E9 12 00 01 0F BC BD BD BD BD 30 D0 37 F4 D2 46 00 00 FC BB` | |
| Ping | `CC 03 00 00 00` | seen everywhere in parks |
| Fast ping | `CC 03 00 01 00` | believed to switch bands to continuous listening, see [Fast mode](#fast-mode-cc-03-00-01-00) |

RGB levels are not balanced: green appears dimmer than red or blue at low
values, and the effect varies with battery level.

### Captured animations (scenes)

31 captured show packets are built in as scenes: see
[commands.md](commands.md#scenes) for the full list with payloads. Opcodes
`E9 07`, `0C`, `0E`, `0F`, `10`, `11`, `12`, `13` and `14` aren't decoded
beyond the shared timing/colour/vibration bytes.

### Fast mode (`CC 03 00 01 00`)

Bands normally listen for broadcasts only now and then. The fast-mode ping
(captured during the Frozen show) is believed to switch them to continuous
listening for a while. Haw8411's Flipper Zero app says this cuts the response
time from about 15 s to under 2 s; that's the author's claim and hasn't been
measured. The app sends the ping on its own for a "pre-warm" of 5–30 s, then
interleaves it with the effect (2 packets in 10).

The bridge's **Fast mode** (on by default) does the same: one 100 ms slot in
five of every broadcast carries the fast ping, with the same E1/E2 prefix as
the effect. **Fast mode warm-up** (0–15 s, default off) sends the ping on its
own first when the bridge has been quiet for 30 s; it makes the first effect
more reliable, but delays it by that long. **Wake bands** sends just the
ping, for 15 s.

### Band replies

Bands are believed to answer the `CC 03` ping with a longer `CC` advertisement
of their own, though its contents aren't understood, and none has been heard
here yet. The MagicBand integration logs anything with Disney's company ID
that Home Assistant's Bluetooth hears (see
[integration.md](integration.md#hearing-bands-respond)).

## Band beacons

Worked out from 36 messages heard from two MagicBand+ bands over about
15 hours (17 Nov 2026). Treat it as a working model, not a specification.

Every band sends a **status beacon** on its own, not in reply to anything:
every 15 minutes overnight, every ~6 minutes while being handled
(`83 01` = Disney's company ID, then):

```
C0 0F 01 01  LL  B1 B2 B3 B4 B5 B6 B7 B8  00 35 33 00
C0 13 01 01  LL  B1 B2 B3 B4 B5 B6 B7 B8  00 36 31 00 00 00 00 00
```

The second byte is the length of what follows. The longer `C0 13` form came
from a third band just after it was switched on; its signature (below) was
stable across its beacons, and it is handled the same way. Its `LL` went
`3C` → `32` (60 → 50) within 8 minutes, which a battery reading wouldn't
normally do: one more reason the battery idea is unconfirmed.

| Part | What's known |
|---|---|
| `C0 0F 01 01` / `C0 13 01 01` | Constant apart from the length byte |
| `LL` | Only ever went **down**, in round decimal steps: band 1 `64` `62` `50` `48` (100, 98, 80, 72), band 2 `50` `48` `32` (80, 72, 50). **Probably the battery level in percent**: unconfirmed until a charged band is seen going back up |
| `B1`–`B8` | Mostly fixed per band. The bits `83 42 40 C0 8C 04 10 4A` changed between beacons, **in the same positions for both bands**; every other bit never changed. Those fixed bits are the band's **signature**: the two bands differ in 16 of them, and each band's signature was identical in every beacon |
| `00 35 33 00` / `00 36 31 00 00 00 00 00` | Constant for each form |

- **Addresses:** a new random (private) Bluetooth address every beacon, so
  the address can't identify a band. The signature can.
- **Timing:** two bands kept their own 15-minute cycles about 1.5 minutes
  apart. Identical beacons (same `LL` and body) sometimes repeat hours apart.
- **A second type,** `0F 11 01` followed by 16 bytes that look random,
  appeared three times in the bands' time slots: probably encrypted, not
  decoded.
- **Not a reply:** beacons kept their schedule regardless of the bridges'
  commands.

The integration uses this to recognise each band, show whether it's
nearby, track the `LL` byte as an unconfirmed battery level, and pair each
band's Bluetooth with its NFC ID (see
[integration.md](integration.md#bands-over-bluetooth)).

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
