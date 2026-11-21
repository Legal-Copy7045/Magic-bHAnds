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
- the **LED ring** and the **PN532 NFC board**, on leads with JST-XH plugs,
  so they can go wherever the housing needs them.

![Front and back copper](docs/board.png)

[Schematic (PDF)](docs/schematic.pdf) · [Front](docs/front.svg) · [Back](docs/back.svg) · [DRC report](fab/drc.rpt)

> **Status: routed, design rules pass, not yet built.** Every net in the
> schematic matches the board pin for pin, and the dev-board sockets follow
> Espressif's DevKitC-1 pinout. Treat the first order as a prototype: get 5
> boards, power one up without the dev board first (below), and keep the
> compact build working until a board has been proven.

## What's on it

| | Part | Notes |
|---|---|---|
| J1 | USB-C (power only) | On the left edge |
| U1 | **CH224K** USB PD controller | Asks the charger for **5 V**, and nothing else: CFG1 is tied high on the board, so there's no switch to knock to 20 V. Wired per the datasheet (V2.1, 6.2): 1 kΩ + 1 µF on VDD, 10 kΩ on VBUS |
| F1 | 3 A resettable fuse (1812) | Between USB-C and everything else |
| D2 | SMAJ5.0A TVS | Clamps spikes on the 5 V rail |
| D1 | Green LED, "5V OK" | Lights when the charger has agreed 5 V (CH224K's PG) |
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

| | Connector | Pins (1 = square pad) | Goes to | Lead |
|---|---|---|---|---|
| J3 | JST-XH 3-pin | 5V, DIN, GND | LED ring | Up to about 1 m. 22 AWG or thicker for 5V and GND |
| J2 | JST-XH 4-pin | 5V, GND, SDA, SCL | PN532 (I²C mode, switches 1 ON 2 OFF) | Up to about 50 cm. Note the PN532's own header order is GND, VCC, SDA, SCL |
| J4 | 1×5 pin header | VIN, GND, LRC, BCLK, DIN | Amplifier kit's cable (Dupont ends) | As supplied (about 20 cm) |
| J5 | 1×7 socket | LRC, BCLK, DIN, GAIN, SD, GND, Vin | Adafruit 3006, *instead of* J4 | — |
| XJ1, XJ3 | 2 × 1×22 sockets, 22.86 mm apart | DevKitC-1 J1 and J3 | Dev board, **antenna end over the copper-free strip** (pin 1 on the right) | — |

Leads: pre-crimped JST-XH leads (2.5 mm pitch) are the easy way; cut one end
and solder it to the ring's pads or a Dupont socket for the PN532.

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
   1.6 mm, any colour. 1 oz copper is enough (the 5 V track is 0.8 mm wide).
2. Turn on **PCB Assembly**, top side, and upload **`fab/bom.csv`** and
   **`fab/cpl.csv`**. They list only the small surface-mount parts.
3. Four parts have no LCSC number yet: pick them in JLCPCB's parts search by
   the MPN in the BOM (or an equivalent): **SMAJ5.0A** (TVS, SMA),
   **3 A hold 1812 PTC fuse**, **74AHCT1G125** (SOT-23-5), **SRV05-4**
   (SOT-23-6). Check every LCSC number shown before paying.
4. In the placement preview, check **U1 (CH224K)** pin 1 and the **USB-C**
   orientation; rotate in the preview if they're off.

**You solder** (through-hole, all on the top side): the two 1×22 female
sockets, the 1×5 header (and the 1×7 socket only if you use an Adafruit
3006), the two JST-XH sockets, the 1000 µF and 100 µF capacitors (stripe =
minus, away from the square pad), and nothing else.

## First power-up

1. **No dev board, no leads.** Plug in the USB-C charger: the **5V OK** LED
   lights. Measure **TP1 (5V) to TP3 (GND): 4.75–5.25 V**.
2. Unplug. Fit the dev board (antenna end right). Plug in: the dev board's
   LED lights, **TP2 (3V3) reads 3.2–3.4 V**.
3. Add the PN532, then the amplifier, then the ring, one at a time, and run
   [the checks for every build](../README.md#checking-a-build-works).

## How it's made

Everything is generated from one parts list (`tools/netlist.py`):
`make_schematic.py` writes the schematic, `make_pcb.py` places the parts,
Freerouting 1.9.0 routes it (`export_dsn.py` / `import_ses.py`, with the
power nets in their own wide-track classes and ground stitched between the
pours), and `make_fab.py` writes the JLCPCB files. `tools/build.sh` runs it
all, including the design-rule check:

```
FREEROUTING=/path/to/freerouting-1.9.0.jar tools/build.sh
```

The CH224K has no KiCad library part; its symbol and footprint (ESSOP-10 with
the exposed pad, its only ground) are in `tools/lib/`. The DRC report's
remaining entries are notices that KiCad's stock libraries aren't configured
on the build machine, and the USB-C outline meeting the board edge (the fab
trims it).
