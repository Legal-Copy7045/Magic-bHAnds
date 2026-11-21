# MagicBand Reader carrier board (KiCad)

Build option 4 of [the ways to build the reader](../README.md).

A 90 × 64 mm, 2-layer "brains" board for the [MagicBand Reader](../../docs/reader.md),
with four M3 holes, sized for a 4.92 in (125 mm) box. It replaces the
breadboard, the power hubs, the interface board and the separate USB-C PD
trigger. The parts you already have plug in:

- the **ESP32-S3-DevKitC-1 (N16R8)** dev board, into two 22-pin sockets;
- the **MAX98357A amplifier kit**, by its own 5-wire cable (or an Adafruit
  3006 breakout straight into a 7-pin socket); the speaker plugs into the
  amplifier as before;
- the **LED ring** and the **PN532 NFC board**, on leads, so they can go
  wherever the housing needs them.

Every lead keeps the cable it uses on the breadboard: each plugs into a
2.54 mm female header wired in **that cable's own pin order**, so nothing is
re-crimped or crossed over.

![Front and back copper](docs/board.png)

[Schematic (PDF)](docs/schematic.pdf) · [Front](docs/front.svg) · [Back](docs/back.svg) · [DRC report](fab/drc.rpt)

> **Status: routed, design rules pass, not yet built.** Every net in the
> schematic matches the board pin for pin, the dev-board sockets follow
> Espressif's DevKitC-1 pinout, and the build checks every power track's
> width in the routed copper (below). Treat the first order as a prototype: get 5
> boards, power one up without the dev board first (below), and keep the
> compact build working until a board has been proven.

## What's on it

| | Part | Notes |
|---|---|---|
| J1 | USB-C (power only) | On the left edge |
| U1 | **CH224A** USB PD controller (or a CH224K) | Asks the charger for **5 V**, and nothing else: CFG1 is tied high through 100 kΩ, so there's no switch to knock to 20 V. The CH224A is WCH's pin-compatible upgrade of the CH224K and the one JLCPCB stocks; wired per its datasheet (V2.1, 6.1.2) with **R1 and R2 = 0 Ω**. For a CH224K, fit **R1 = 1 kΩ and R2 = 10 kΩ** instead (6.2). D+/D− are left open (power only: the request goes over CC) |
| F1 | 3 A resettable fuse (1812) | Between USB-C and everything else |
| D2 | SMAJ5.0A TVS | Clamps spikes on the 5 V rail |
| D1 | Green LED, "5V OK" | Lights when the charger has agreed 5 V (the CH224A's PG) |
| D3 | SS34 Schottky | 5 V to the dev board. The board powers the ESP32, but the dev board's own USB can't power the LEDs and amplifier, so there's **no 5 V wire to pull** before using USB |
| U2 | 74AHCT1G125 | 3.3 V → 5 V LED data, then **470 Ω** (R7) |
| U3 | SRV05-4 | ESD clamp on the lines that leave the box: SDA, SCL, LED data |
| R5, R6 | 4.7 kΩ | I²C pull-ups to 3.3 V |
| C5 | 1000 µF 10 V | LED ring supply, by the ring connector |
| C6, C7 | 100 µF 16 V, 10 µF | Amplifier supply, by its header |
| TP1–TP3 | Test pads | 5 V, 3.3 V, GND |

GPIOs are the reader firmware's: I²S LRC 5, BCLK 6, DIN 7; I²C SDA 8, SCL 9;
LEDs 10. The firmware doesn't change: install the standard reader from the
[web installer](https://legal-copy7045.github.io/Magic-bHAnds/).

## Connectors and leads

| | Header (2.54 mm female) | Pins, left to right (1 = square pad) | Plug in | Lead length |
|---|---|---|---|---|
| J3 | 1×3 | **5V, DIN, GND** | The LED ring's 3-pin plug with its jumper wires: **red, green, black** | Up to about 1 m |
| J2 | 1×4 | **GND, 5V, SDA, SCL** | The PN532's 4-wire Dupont cable, in the PN532's own order (GND, VCC, SDA, SCL). PN532 switches: 1 ON, 2 OFF (I²C) | Up to about 50 cm |
| J4 | 1×5 | **G, V, BCL, LRC, DIN** | The amplifier kit's cable, in the order printed by its socket | As supplied (about 20 cm) |
| J5 | 1×7 | LRC, BCLK, DIN, GAIN, SD, GND, Vin | An Adafruit 3006, *instead of* the kit on J4 | — |
| XJ1, XJ3 | 2 × 1×22, 22.86 mm apart | DevKitC-1 J1 and J3 | The dev board, **antenna end over the copper-free strip** (pin 1 on the right) | — |

The cables' male ends push into the headers the same way they push into a
breadboard. Once everything works, a dab of hot glue along each row keeps
them from working loose in the box. Labels on the board name every pin.

## Power tracks

### Current budget

Everything runs from the one USB-C input, so the worst case adds every
maximum at once (the same budget as the [shopping list](../shopping-list.md#current-budget-with-these-parts)):

| Load | Worst case |
|---|---|
| LED ring at full white | 1.44 A |
| Amplifier (MAX98357A into 4 Ω, full volume) | 0.65 A |
| Dev board (ESP32-S3, Wi-Fi transmit peak; *estimate*) | 0.50 A, through D3 |
| PN532 (*estimate*) | 0.15 A |
| Level shifter, pull-ups, LED | 0.01 A |
| **Total through USB-C, the fuse and the shared 5 V track** | **≈ 2.75 A**, under the charger's 3 A |

**The ring is capped by the firmware, not by its size.** 1.44 A is 24 RGB
LEDs × 60 mA. With more LEDs the reader scales its output down so full white
stays at about 1.44 A (24 ÷ LED count: a 35-LED ring runs at up to 68 %; an
RGBW ring is capped at 18 LEDs × 80 mA). That only works if the reader's
**LED count** setting matches the ring: set it before the first full-white
test. Without the cap, 35 LEDs × 60 mA would be 2.1 A for the ring and about
3.4 A in all, over a 3 A charger.

In normal use the reader draws about 0.3 A idle and about 1.4 A during a
welcome. The 3 A fuse (5 A trip) is there for a short circuit or a damaged
lead, not to limit the current; the charger's own 3 A limit and the
firmware's ring cap do that.

### Track widths

| Net | Track | Carries (worst case) |
|---|---|---|
| VBUS (USB-C → fuse) | 0.8 mm | Everything, ≈ 2.75 A |
| +5V (fuse → ring, amplifier, NFC, and D3 to the dev board) | 0.8 mm | Up to ≈ 2.75 A by the fuse, less further along |
| ESP_5V (D3 → dev board) | 0.6 mm | ≤ 0.5 A |
| +3V3 | 0.4 mm | Pull-ups only |
| GND | 0.5 mm tracks plus solid pours on both sides | |

At 1 oz copper, 0.8 mm carries about 2.0 A for a 10 °C rise and about 2.8 A
for 20 °C (IPC-2221, outer layer); at 2 oz it's about 3.3 A for 10 °C.
**Order 2 oz copper**, so the worst case (≈ 2.75 A, which only happens with
everything at maximum at once) stays under a 10 °C rise.

The only narrower pieces are necks into pads that are themselves narrower
than the track, each under 2.5 mm: the two USB-C VBUS pins (0.6 mm, too
close together for more) and, depending on how the router lays it out, the
SRV05-4's 5 V pin or the 5V OK LED's resistor (a few mA). `tools/check_widths.py` measures the routed copper,
lists every neck, and fails the build on any other power track narrower than
this table.

### Ground and the speaker

On the breadboard, the sound crackled on the charger until the ESP32 had its
own ground wire to the amplifier: otherwise the I²S signals' ground return
ran through the power hub. The board does this in copper: ground pours fill
both sides (stitched together with vias), the dev board's four GND pins and
the amplifier header's G pin all join them directly, and the I²S tracks run
over that ground all the way. There's no jumper to add. If it ever crackles,
check the amplifier lead's G wire first.

## Fitting it in the box

- The USB-C socket is on the **left edge**. For a cable coming up through
  the stand, drill the box floor near that edge and leave about 25 mm for the
  plug and the bend, or use a right-angle USB-C cable.
- The leads to the Mickey head plug in along the **top edge**.
- The dev board's antenna end (right) should face away from metal; nothing
  in the box should sit over it.
- Height: about 25 mm with the dev board in its sockets (the 1000 µF is
  about 20 mm tall). Use M3 standoffs of 5 mm or more under the board.

## Ordering (JLCPCB)

1. Upload **`fab/magicband-carrier-gerbers.zip`** at jlcpcb.com: 2 layers,
   1.6 mm, any colour, **2 oz outer copper** (see Power tracks).
2. Turn on **PCB Assembly**, top side, and upload **`fab/bom.csv`** and
   **`fab/cpl.csv`**. They list only the small surface-mount parts.
3. Every part has an LCSC number, checked in stock at JLCPCB on 21 Nov 2026
   (the CH224A had the fewest: 501). If one has run out, pick the same MPN
   or an equivalent in the parts search; keep R1/R2 matched to the chip
   (0 Ω for a CH224A, 1 kΩ/10 kΩ for a CH224K).
4. In the placement preview, check **U1 (CH224A)** pin 1 and the **USB-C**
   orientation; rotate in the preview if they're off. (Both use footprints
   from `tools/lib`, so JLCPCB's preview is the place to catch a rotation.)

**You solder** (through-hole, all on the top side): the 2.54 mm female
headers (two 1×22, one each of 1×3, 1×4 and 1×5; the 1×7 only if you use an
Adafruit 3006) and the 1000 µF and 100 µF capacitors (stripe = minus, away
from the square pad). Nothing else.

## Before you order: physical checks

- **Charger and cable:** a USB-C PD charger that offers **5 V 3 A** (most of
  20 W and up do), with a cable rated 3 A. Test with the charger and cable
  you'll actually use.
- **Capacitors:** check the 1000 µF you'll fit is 10 mm across with 5 mm lead
  spacing, 10 V or more, and short enough for the box (about 20 mm or less);
  the 100 µF 6.3 mm across, 2.5 mm spacing. Minus stripe away from the square
  pad.

## First power-up

1. **No dev board, no leads.** Plug in the USB-C charger: the **5V OK** LED
   lights. Measure **TP1 (5V) to TP3 (GND): 4.75–5.25 V**.
2. Unplug. Fit the dev board (antenna end right). Plug in: the dev board's
   LED lights, **TP2 (3V3) reads 3.2–3.4 V**.
3. Add the PN532, then the amplifier, then the ring, one at a time, and run
   [the checks for every build](../README.md#checking-a-build-works).
4. **Full-load test.** Check the reader's **LED count** matches the ring.
   Set the ring to full white at full brightness and play
   a sound at full volume. Measure 5 V **at the ring and amplifier headers**
   (not only TP1): it should stay above 4.75 V, and the fuse and tracks should
   be no more than warm after a few minutes.

## How it's made

Everything is generated from one parts list (`tools/netlist.py`):
`make_schematic.py` writes the schematic, `make_pcb.py` places the parts,
Freerouting 1.9.0 routes it (`export_dsn.py` / `import_ses.py`, with the
power nets moved into their own wide-track classes in the DSN and ground
stitched between the pours), `check_widths.py` checks the routed power
widths, and `make_fab.py` writes the JLCPCB files. `tools/build.sh` runs it
all, including the design-rule check:

```
FREEROUTING=/path/to/freerouting-1.9.0.jar tools/build.sh
```

The CH224A/CH224K has no KiCad library part; its symbol and footprint (ESSOP-10 with
the exposed pad, its only ground) are in `tools/lib/`, with the USB-C
footprint (KiCad's, minus the three silkscreen lines that would print off
the board edge; `make_usb_fp.py` makes it). `fp-lib-table` points the DRC at
those and at KiCad's own footprints, so it checks every footprint against its
library too. The build stops unless the DRC report is clean (0 violations,
0 unconnected pads) and every power track passes `check_widths.py`.
