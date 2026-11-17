# MagicBand Reader: terminal base and point-to-point builds

Two more compact ways to build the
[breadboard proof of concept](../reader-breadboard/README.md), with the
same parts, connections and power:

- **Terminal base:** the ESP32-S3 board plugs into a Lonely Binary
  pluggable terminal-block base, and wires go into its push-in terminals.
- **Point-to-point:** female Dupont jumpers go straight onto the ESP32-S3
  board's header pins.

Everything else is shared: a small **interface board** for the level
shifter and I²C pull-ups, two lever-connector **power hubs**, and the ring,
amplifier and PN532 wired to them. Parts: the
[shopping list](../shopping-list.md).

**Building it? Follow the [step-by-step build](build.md).** This page is the
reference behind it.

| Terminal base | Point-to-point |
|---|---|
| ![Terminal base wiring](../../docs/reader-terminal-base.svg) | ![Point-to-point wiring](../../docs/reader-point-to-point.svg) |

**Status:** reviewed, **not yet built**. Build and test the breadboard
version first. The component review, current budget and the reasons behind
each choice are in the [breadboard spec](../reader-breadboard/README.md),
and apply here unchanged.

## Power

- **Supply:** a **USB-C charger of 20 W or more** (Apple 20 W, a laptop
  charger and so on) and a USB-C cable rated for 3 A or more. At 5 V, USB-C
  gives up to 3 A; the reader needs at most about 2.75 A with the 24-LED
  ring and the 4 Ω speaker.
- **USB-C PD trigger:** a CH224K board with its DIP switch **set to 5 V**,
  checked with a meter and taped down (or the Adafruit HUSB238, 5807, with
  the 5V jumper kept and the 1A jumper cut). Never select anything above
  5 V. Details: [breadboard spec](../reader-breadboard/README.md#supply).
- **Two 5-way lever connectors** (Wago 221-415 or similar), one for 5 V and
  one for ground. Every power wire starts at a hub, and every ground meets
  at the GND hub.

![Power distribution](../../docs/reader-power.svg)

**USB rule:** before plugging USB into the ESP32 (for the first install or
serial logs), **open the 5 V hub's lever and pull out the ESP32's 5 V
wire**. Put it back afterwards. USB and the 5 V supply must never feed the
ESP32 together.

## Parts

As in the [breadboard parts list](../reader-breadboard/README.md#parts),
without the breadboard and its jumpers, plus:

| Qty | Part | Specification | For |
|---|---|---|---|
| 1 | Terminal base | **Lonely Binary ESP32-S3 screwless (push-in) terminal base** for the DevKitC-1 layout | Terminal base build |
| 6 | Jumper leads | **Female-to-male Dupont jumpers**, 150–200 mm, male end cut off | Point-to-point build: ESP32 3V3, GPIO8/9/10, 5V, GND |
| 2 | Lever connectors | **5-way lever connector** (Wago 221-415 or similar) | Power hubs |
| 1 | Perfboard | **Half-size solderable breadboard PCB** (Adafruit Perma-Proto 1609 or similar: rows 1–30, columns a–j, a rail pair each side) | Interface board |
| 1 | IC socket (optional) | DIP-14, 2.54 mm | Lets the 74AHCT125 plug in; or solder it directly |
| — | Wire | 22 AWG **stranded** | All the runs. Colours, lengths and how to finish each wire: [wiring guide](../shopping-list.md#wiring-guide) |

## Interface board

An **Adafruit Perma-Proto half-sized PCB (1609)**: a solderable board laid
out like a half-size breadboard (rows 1–30, columns a–j, a 5 V/GND rail
pair down each side). It holds the parts that would otherwise dangle in the
wiring, and it's the same for both builds. The diagrams draw it hole for
hole.

![Interface board](../../docs/reader-interface-board.svg)

| IC pin | Connection | Why |
|---|---|---|
| 1 (1OE) | GND | Enables channel 1 (active low) |
| 2 (1A) | ESP32 **GPIO10** | LED data in, 3.3 V |
| 3 (1Y) | LED data out → ring | 5 V data; the 470 Ω is at the ring end |
| 4 (2OE), 10 (3OE), 13 (4OE) | +5V | Disables channels 2–4 |
| 5 (2A), 9 (3A), 12 (4A) | GND | TI: unused inputs must be tied |
| 6, 8, 11 | Open | Unused outputs |
| 7 (GND) | GND | |
| 14 (VCC) | +5V | 0.1 µF from pin 14's row to ground, right beside it |

### Perma-Proto layout

| Part or wire | Holes |
|---|---|
| 74AHCT125 | pin 1 in **e10** (pins 1–7 down column e, rows 10–16), pins 14–8 down column f; notch towards row 1 |
| 4.7 kΩ (SDA pull-up) | a2 – a6 |
| 4.7 kΩ (SCL pull-up) | b2 – b7 |
| 0.1 µF | h9 – h10 |
| **In:** 5 V hub / GND hub | **L+25** / **L−26** |
| **In:** ESP32 3V3 | **c2** |
| **In:** ESP32 GPIO8 (SDA) / GPIO9 (SCL) | **d6** / **d7** |
| **In:** ESP32 GPIO10 | **d11** (IC pin 2) |
| **Out:** PN532 SDA / SCL | **c6** / **c7** |
| **Out:** PN532 VCC / GND | **L+4** / **L−3** |
| **Out:** LED data to the ring | **c12** (IC pin 3) |
| Tie: 1OE to GND, 2OE to 5 V, 2A to GND, IC GND | a10 – L−10, a13 – L+13, a14 – L−14, a16 – L−16 |
| Tie: VCC, 4OE, 3OE to 5 V; 4A, 3A to GND | j10 – R+10, j11 – R+11, j14 – R+14; j12 – R−12, j15 – R−15 |
| Ground for the 0.1 µF | j9 – R−9 |
| Rail bridges | L+20 – R+20, L−21 – R−21 |

Solder each wire into its hole (or fit a 2.54 mm pin header there if you
want plug-in leads).

**Check the board before fitting the IC** (or before soldering it, if you
don't use a socket). With the meter on continuity: holes e10, e14, e16, f12
and f15 (IC pins 1, 5, 7, 12, 9) to GND = beep; e13, f10, f11 and f14 (IC
pins 4, 14, 13, 10) to 5 V = beep; 5 V to GND = no beep. On resistance:
c6 and c7 each to c2 read 4.7 kΩ.

## Wiring

### ESP32 connections

| ESP32-S3 signal | Terminal base terminal | Point-to-point: J1 pin | Goes to |
|---|---|---|---|
| **5V** | 5V pad (solder a 22 AWG wire) | J1-21 | 5 V hub (**unclip before using USB**) |
| **GND** | GND pad (solder a 22 AWG wire) | J1-22 | GND hub |
| **3V3** | Left **3V3** | J1-1 | Interface board +3V3 |
| **GPIO8** | Left **8** | J1-12 | Interface board SDA |
| **GPIO9** | Left **9** | J1-15 | Interface board SCL |
| **GPIO10** | Left **10** | J1-16 | Interface board GPIO10 (IC pin 2) |
| **GPIO5** | Right **5** | J1-5 | Amplifier cable **LRC** |
| **GPIO6** | Right **6** | J1-6 | Amplifier cable **BCLK** |
| **GPIO7** | Left **7** | J1-7 | Amplifier cable **DIN** |

- **Point-to-point:** J1 is the header on the left with the antenna at the
  top (component side up); J1-1 (3V3) is nearest the antenna. Female Dupont
  leads carry the ESP32's 5 V (≤ 0.5 A) comfortably; the LEDs and amplifier
  have their own wires.
- **Terminal base:** the terminal and pad positions above come from the
  base's printed labels; check them against your base before wiring. The
  base has no 5 V terminal, so solder wires to its 5V and GND pads.

### Everything else

| From | To | Notes |
|---|---|---|
| PD trigger output + / − | 5 V hub / GND hub | 22 AWG stranded, ≤ 30 cm |
| 5 V hub / GND hub | Interface board +5V / GND | 22 AWG |
| Interface board +5V, GND, SDA, SCL | PN532 **VCC**, **GND**, **SDA**, **SCL** | ≤ 20 cm. Switches: 1 ON, 2 OFF (I²C) |
| 5 V hub / GND hub | Amplifier cable **VIN** / **GND** | 22 AWG. Cut the Dupont ends off the cable's VIN and GND wires and solder each to its 22 AWG hub wire, **with the 100 µF soldered across that joint** (stripe to GND), within 5 cm of the amplifier |
| Amplifier cable **LRC** / **BCLK** / **DIN** | ESP32 GPIO5 / GPIO6 / GPIO7 | Point-to-point: female Dupont ends plug straight onto J1-5/6/7 (male ends: use female-to-female jumpers). Terminal base: cut the Dupont ends off, strip 8–10 mm, push into the terminals |
| Interface board LED out | 470 Ω → ring **DIN** | 22 AWG; resistor soldered inline at the ring, in heat-shrink |
| 5 V hub / GND hub | Ring **5V** / **GND** (or a strip's input end: see [LED options](../shopping-list.md#if-a-ring-wont-fit-flexible-led-options)) | 22 AWG stranded, ≤ 50 cm; 1000 µF 10 V across the ring's pads, stripe to GND |
| Amplifier PH2.0 speaker socket | Speaker (4 Ω 3 W, its own plug) | Neither wire is ground |

- **Keep the I²S wires (LRC, BCLK, DIN) under about 20 cm**, routed together.
- **Detachable leads (optional):** a 3-pin JST plug inline for the ring
  (5V, DATA, GND). A 2-pin JST SM lead suits a detachable ring power pair
  if the data wire gets its own connector.
- Insulate every joint with heat-shrink, and fix the modules in the case so
  the joints don't flex.

## Build and test

The staged build, with checks after each stage, is in the
**[step-by-step build](build.md)**.
