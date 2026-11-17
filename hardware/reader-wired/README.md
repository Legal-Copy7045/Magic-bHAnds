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
amplifier and PN532 wired to them.

**Status:** reviewed, **not yet built**. Build and test the breadboard
version first. The component review, current budget and the reasons behind
each choice are in the [breadboard spec](../reader-breadboard/README.md),
and apply here unchanged.

## Power

- **Supply:** a **USB-C charger of 20 W or more** (Apple 20 W, a laptop
  charger and so on) and a USB-C cable rated for 3 A or more. At 5 V, USB-C
  gives up to 3 A; the reader needs at most about 2.6 A with a 24-LED ring
  (2.1 A with 16).
- **USB-C breakout:** Adafruit HUSB238 USB-C Power Delivery breakout
  (product 5807), with the **5V jumper kept closed** and the **1A jumper
  cut** for 5 V 3 A. Never cut the 5V jumper: that asks the charger for up
  to 20 V. Details: [breadboard spec](../reader-breadboard/README.md#supply).
- **Two Wago 221-415 hubs**, one for 5 V and one for ground. Every power
  wire starts at a hub, and every ground meets at the GND hub.

```
USB-C charger ─ USB-C breakout ─(18 AWG)─┬─ 5 V hub ──┬─ ESP32 5V            (22 AWG; unclip before using the ESP32's USB)
                                         │            ├─ interface board 5V  (22 AWG; also feeds the PN532)
                                         │            ├─ amplifier Vin       (22 AWG)
                                         │            └─ LED ring 5V         (20 AWG; 1000 µF at the ring)
                                         └─ GND hub ──┬─ ESP32 GND
                                                      ├─ interface board GND (also the PN532 ground)
                                                      ├─ amplifier GND
                                                      └─ LED ring GND
```

**USB rule:** before plugging USB into the ESP32 (for the first install or
serial logs), **open the 5 V hub's lever and pull out the ESP32's 5 V
wire**. Put it back afterwards. USB and the 5 V supply must never feed the
ESP32 together.

## Parts

As in the [breadboard parts list](../reader-breadboard/README.md#parts),
without the breadboard, jumper kit and Wago 221-414s, plus:

| Qty | Part | Specification | For |
|---|---|---|---|
| 1 | Terminal base | **Lonely Binary ESP32-S3 pluggable terminal block** base for the DevKitC-1 layout | Terminal base build |
| 9 | Jumper leads | **Female-to-bare** (or female-to-male, end cut off) Dupont leads, 10–15 cm | Point-to-point build |
| 2 | Lever connectors | **Wago 221-415** (5-way) | Power hubs |
| 1 | Perfboard | Single-sided, 2.54 mm pitch, about 30 × 40 mm | Interface board |
| 1 | IC socket | DIP-14, 2.54 mm | Interface board (the 74AHCT125 plugs in) |
| — | Wire | 22 AWG **stranded** hook-up wire (red, black and signal colours) instead of solid | All the short runs |

## Interface board

A small perfboard that holds the parts that would otherwise dangle in the
wiring. It's the same for both builds.

```
                     +3V3 (from ESP32 3V3)
                      │        │
                    4.7 kΩ   4.7 kΩ
                      │        │
  ESP32 GPIO8 ──────── SDA ────┼──────────────── PN532 SDA
  ESP32 GPIO9 ──────────────── SCL ───────────── PN532 SCL
  5 V hub ─── +5V ──────────────────────────────── PN532 VCC
  GND hub ─── GND ──────────────────────────────── PN532 GND

                  SN74AHCT125N (in a DIP-14 socket)
               ┌──────────── U ────────────┐
   GND ─── 1  │ 1OE                    VCC │ 14 ─── +5V ─┐
 GPIO10 ── 2  │ 1A                     4OE │ 13 ─── +5V   0.1 µF from pin 14
  LED ──── 3  │ 1Y                      4A │ 12 ─── GND   to pin 7, across
  out      4  │ 2OE ─── +5V             4Y │ 11 (open)    the socket
   GND ─── 5  │ 2A                     3OE │ 10 ─── +5V
  (open)   6  │ 2Y                      3A │  9 ─── GND
   GND ─── 7  │ GND                     3Y │  8 (open)
               └───────────────────────────┘
```

| IC pin | Connection | Why |
|---|---|---|
| 1 (1OE) | GND | Enables channel 1 (active low) |
| 2 (1A) | ESP32 **GPIO10** | LED data in, 3.3 V |
| 3 (1Y) | LED data out → ring | 5 V data; the 330 Ω is at the ring end |
| 4 (2OE), 10 (3OE), 13 (4OE) | +5V | Disables channels 2–4 |
| 5 (2A), 9 (3A), 12 (4A) | GND | TI: unused inputs must be tied |
| 6, 8, 11 | Open | Unused outputs |
| 7 (GND) | GND | |
| 14 (VCC) | +5V | 0.1 µF (X7R, 50 V) straight across pins 14 and 7 |

**Wires onto the board** (solder them in, or fit a 2.54 mm pin header or
small screw terminal for each): +5V and GND from the hubs, +3V3, GPIO8,
GPIO9 and GPIO10 from the ESP32; out to the PN532 (GND, +5V, SDA, SCL) and
the ring (LED data).

**Check the board before fitting the IC.** With the IC out of its socket
and the meter on continuity: pins 1, 5, 7, 9 and 12 to GND = beep; pins 4,
10, 13 and 14 to +5V = beep; +5V to GND = no beep; SDA and SCL each to +3V3
read 4.7 kΩ.

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
| **GPIO5** | Right **5** | J1-5 | Amplifier **LRC** |
| **GPIO6** | Right **6** | J1-6 | Amplifier **BCLK** |
| **GPIO7** | Left **7** | J1-7 | Amplifier **DIN** |

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
| USB-C breakout terminal + / − | 5 V hub / GND hub | 18 AWG |
| 5 V hub / GND hub | Interface board +5V / GND | 22 AWG |
| Interface board +5V, GND, SDA, SCL | PN532 **VCC**, **GND**, **SDA**, **SCL** | ≤ 20 cm. Switches: 1 ON, 2 OFF (I²C) |
| 5 V hub / GND hub | Amplifier **Vin** / **GND** | 22 AWG. 100 µF 16 V across Vin and GND at the amplifier (solder to its header pins), stripe to GND |
| Interface board LED out | 330 Ω → ring **DIN** | 22 AWG; resistor soldered inline at the ring, in heat-shrink |
| 5 V hub / GND hub | Ring **5V** / **GND** | 20 AWG; 1000 µF 10 V across the ring's pads, stripe to GND |
| Amplifier + / − | Speaker (8 Ω, 2–3 W) | Neither terminal is ground |

- **Keep the I²S wires (LRC, BCLK, DIN) under about 20 cm**, routed together.
- **Detachable leads (optional):** JST-PH 2.0 plugs inline, 3-pin for the
  ring (5V, DATA, GND) and 2-pin for the speaker.
- Insulate every joint with heat-shrink, and fix the modules in the case so
  the joints don't flex.

## Build and test

Follow the breadboard spec's
[build and test sequence](../reader-breadboard/README.md#build-and-test-sequence),
stage by stage, with these differences:

- **Before stage 1:** check the interface board with the IC out (above).
- **Stage 1:** install the firmware over USB with nothing else connected.
  Then connect the hubs and the ESP32's 5V/GND, and measure the voltages
  there.
- **Stage 2:** the PN532 pre-check is the same: on its own from the 5 V hub,
  SDA and SCL must read below 3.6 V. Then connect it to the interface board,
  and the interface board to GPIO8/9 and 3V3.
- **Stage 3:** fit the 74AHCT125 in its socket (notch to pin 1), then
  connect the ring. Measure IC pins 14 to 7: 4.75–5.25 V.
- **Stages 4 and 5:** as written.
