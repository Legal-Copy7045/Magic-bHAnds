# MagicBand+ BLE protocol notes

MagicBand+ bands react to **BLE advertisements**. They don't use connections or
pairing. Park beacons broadcast manufacturer-specific data under Disney's
Bluetooth company ID **0x0183**, which goes over the air little-endian as `83 01`.

These notes come from community reverse engineering, mainly the
[emcot.world MagicBand+ Bluetooth codes](https://emcot.world/Disney_MagicBand%2B_Bluetooth_Codes)
wiki and projects built on it. None of it is official, and a Disney firmware
update could change it.

## Advertisement layout

```
02 01 06                 Flags AD (LE general discoverable, BR/EDR not supported)
LL FF 83 01 <payload>    Manufacturer-specific AD, LL = 3 + len(payload)
```

Legacy advertisements are limited to 31 bytes, so the payload can be at most
**24 bytes**.

## Byte encodings

| Thing       | Encoding                          | Notes |
|-------------|-----------------------------------|-------|
| Vibration   | `0xB0 \| v` (v = 0–15)            | Usually the last byte. 0 = no vibration. |
| Colour      | `mode \| index` (index = 5 bits)  | The mode bits change with the effect, see below. |
| `E9 LL ...` | Effect opcode + remaining length  | LL = number of bytes after it. |

### Colour palette (5-bit index)

| Index | Name          | Index | Name          |
|-------|---------------|-------|---------------|
| 0x00  | cyan          | 0x12  | lime          |
| 0x01  | purple        | 0x13  | orange        |
| 0x02  | blue          | 0x14  | red_orange    |
| 0x03  | midnight_blue | 0x15  | red           |
| 0x05  | bright_purple | 0x19  | green         |
| 0x06  | lavender      | 0x1A  | lime_green    |
| 0x08  | pink          | 0x1B  | white         |
| 0x0F  | yellow_orange | 0x1D  | off           |
| 0x10  | off_yellow    | 0x1F  | random        |

The indexes not listed above are unmapped. Mapping them is a good experiment.

## Known commands (payload after `83 01`)

| Effect      | Payload |
|-------------|---------|
| Single colour | `E9 05 00 TT 0E (E0\|c) (B0\|v)`, TT ≈ timing, default `2E` |
| Dual colour   | `E9 06 00 TT 0F (80\|c1) (80\|c2) (B0\|v)`, default TT `22` |
| Five colour   | `E9 09 00 TT 0F (A0\|c1) … (A0\|c5) (B0\|v)`, default TT `2E` |
| Crossfade     | `E1 00 E9 11 00 6F 0F (40\|c1) (40\|c2) 58 F4 48 82 D1 46 02 08 D0 65 00 (B0\|v)` |
| Circle        | `E9 0B 0B 0F 0F 5C 5D 48 A5 D1 45 32 (B0\|v)` |
| Ping          | `CC 03 00 00 00` |

Worked example: red (0x15) with vibration 3 gives
`83 01 E9 05 00 2E 0E E5 B3`.

## Open questions to test

- What the `TT` "timing" byte controls exactly (duration? fade speed?).
- What the unmapped palette indexes look like.
- How many repeats or how long a burst a sleeping band needs before it reacts.
- Whether the vibration nibble is a strength, a pattern ID, or both.

Use the `raw` action (see the README) to try payloads, and record findings here.
