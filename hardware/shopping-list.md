# MagicBand Reader: shopping list (Adafruit)

Exact parts for the reader, from Adafruit where they sell a suitable part.
Each one was checked against its Adafruit product page or guide. Stock
changes often: check availability before ordering.

The same core parts serve all three builds
([breadboard](reader-breadboard/README.md),
[terminal base and point-to-point](reader-wired/README.md)); the last two
tables list what each build adds.

## Core parts (every build)

| Qty | Part | Adafruit | Why this one |
|---|---|---|---|
| 1 | NeoPixel Ring, 24 × 5050 RGB LED | [1586](https://www.adafruit.com/product/1586) | 65.5 mm outside, **52.3 mm inside**: the PN532 module (43 × 41 mm) fits inside the ring, so the LEDs stay clear of its antenna. Ships with WS2812B or SK6812 LEDs, same protocol. Matches the firmware's default `ring_leds: 24` |
| 1 | I2S 3W Class D Amplifier Breakout, MAX98357A | [3006](https://www.adafruit.com/product/3006) | The amplifier the firmware is written for. 2.5–5.5 V supply; 1 MΩ on SD gives mono (L+R)/2 at 5 V; 9 dB default gain |
| 1 | Mono Enclosed Speaker, 3 W 4 Ω | [3351](https://www.adafruit.com/product/3351) | Rated for the amplifier's full output (3 W into 4 Ω at 5 V). Adafruit's 8 Ω speakers are 1 W, below what the amplifier can deliver |
| 1 | 74AHCT125 Quad Level-Shifter (3V to 5V), DIP-14 | [1787](https://www.adafruit.com/product/1787) | Lifts the ESP32's 3.3 V LED data to the 5 V the LEDs need |
| 1 | Through-Hole Resistors, 4.7 kΩ 5 % ¼ W, pack of 25 | [2783](https://www.adafruit.com/product/2783) | Two I²C pull-ups |
| 1 | Through-Hole Resistors, 470 Ω 5 % ¼ W, pack of 25 | [2781](https://www.adafruit.com/product/2781) | LED data resistor, at the ring. Adafruit recommends 300–500 Ω; it doesn't sell 330 Ω |
| 1 | 100 µF 16 V Electrolytic Capacitors, pack of 10 | [2193](https://www.adafruit.com/product/2193) | Amplifier supply |
| 1 | 0.1 µF ceramic capacitors, 10 pack | [753](https://www.adafruit.com/product/753) | 74AHCT125 supply decoupling |
| 1 | USB Type C Power Delivery Dummy Breakout, HUSB238 | [5807](https://www.adafruit.com/product/5807) | Asks the charger for 5 V 3 A (**keep the 5V jumper, cut the 1A jumper**). Rated to 20 V 5 A, comes with a terminal block |
| 1 | Official Raspberry Pi 27 W PD Power Supply, 5.1 V 5 A, USB-C | [5814](https://www.adafruit.com/product/5814) | True USB Power Delivery, so the HUSB238 gets its 5 V 3 A; 5.1 V output; captive 18 AWG cable. *Or use a USB-C charger of 20 W or more you already have* |
| 1 | Snap-action 5-Wire Block Connector (12–24 AWG), pack of 3 | [874](https://www.adafruit.com/product/874) | Two of them are the 5 V and GND power hubs. 32 A rated |
| 1 | Stranded-Core Wire Spool, 25 ft, 22 AWG, Red | [3068](https://www.adafruit.com/product/3068) | 5 V runs: supply, ring, amplifier |
| 1 | Stranded-Core Wire Spool, 25 ft, 22 AWG, Black | [2976](https://www.adafruit.com/product/2976) | Ground runs |
| 1 | Heat Shrink Pack | [344](https://www.adafruit.com/product/344) | Insulating the resistor at the ring and soldered joints |

**Not from Adafruit:**

| Qty | Part | Specification | Why |
|---|---|---|---|
| 1 | **ESP32-S3 board** | ESP32-S3-DevKitC-1 **N16R8** layout (your Lonely Binary N16R8) | Adafruit's DevKitC-1 boards are N8R8 (8 MB flash, product 5336) or WROOM-2 (product 5364). The reader firmware is built for the N16R8's 16 MB flash and octal PSRAM |
| 1 | **PN532 NFC module V3** | Elechouse V3 or clone (your AITRIP) | Adafruit's PN532 breakout (364) is a 3.3 V-only design needing different wiring and 1.5 kΩ pull-ups. The V3 module is what the build docs are written for |
| 1 | **1000 µF electrolytic capacitor** | 10 V or 16 V, radial, 105 °C | Adafruit's closest is 4700 µF 10 V (1589), well above its own 500–1000 µF NeoPixel guidance |

## If a ring won't fit: flexible LED options

For a ready-made housing, a short length of flexible NeoPixel strip can
replace the ring. Every option below is 5 V, uses the same three wires
(5V, DATA, GND), and needs the same 470 Ω and 1000 µF at its input end.
Set `ring_leds` to the number of LEDs you use.

**How many LEDs:** loop length (mm) × LEDs per metre ÷ 1000. A loop 60 mm
across is about 190 mm long. Keep it to **24 LEDs or fewer**: the current
budget above assumes 24 (1.44 A at full white). Cut only at the marked cut
lines, and wire to the end marked as the input (arrows point away from it).

| Adafruit | Strip | Width | LEDs/m (60 mm loop) | Light comes out | Notes |
|---|---|---|---|---|---|
| [3634](https://www.adafruit.com/product/3634) | NeoPixel **Side Light** Strip, black, 120 LED | 10 mm | 120 (≈ 22) | **Edge** | **Best match.** Curled into a loop standing on its edge, it shines upward like a ring. Adafruit's own Magic Band Reader uses this strip. Also [3635](https://www.adafruit.com/product/3635) (90/m) and [3636](https://www.adafruit.com/product/3636) (60/m, 8 mm) |
| [4310](https://www.adafruit.com/product/4310) | Flexible Silicone **Neon-like** Skinny NeoPixel | 12 × 6 mm | 96 (≈ 18) | Edge, through a silicone diffuser | Smoothest glow (side-light strip inside silicone). Arrives as 1 m sealed at one end, with a JST SM input. **Colour order is RGB, not GRB**: needs a one-line firmware setting |
| [2963](https://www.adafruit.com/product/2963) / [2964](https://www.adafruit.com/product/2964) | **Mini Skinny** NeoPixel, 60 LED/m | 7.5 mm | 60 (≈ 11) | Face of the strip | Lines a housing wall, facing inward. Needs a diffuser to look continuous. 30/m ([2958](https://www.adafruit.com/product/2958)) is too sparse for a small loop |
| [4368](https://www.adafruit.com/product/4368) | **Ultra Skinny** NeoPixel 1515, 4 mm | 4 mm | 150 (cut to ≤ 24) | Face of the strip | Tightest spaces; cut every 7 mm. Adafruit warns it shouldn't be flexed repeatedly: shape it once |

**Not suitable:**
- **Neon-like LED Flex Strip with Silicone Tube (3869):** 12 V (WS2811),
  so it can't share the reader's 5 V supply.
- **LED Dots and Pebble strands (3630, 5225, 4560 and similar):** one LED
  every 50–100 mm, so only 2–4 LEDs on a small loop.
- **RGBW strips:** the firmware drives RGB LEDs.
- **144 LED/m strips** (e.g. [2970](https://www.adafruit.com/product/2970)):
  usable, but a 60 mm loop would hold 27 LEDs, over the 24-LED budget.
  Cut to 24 at most.

Not stated by Adafruit: the smallest safe bend for each strip. Try the
loop size with the strip unpowered before you commit to the housing.

## Breadboard build adds

| Qty | Part | Adafruit |
|---|---|---|
| 1 | Full Sized Premium Breadboard, 830 tie points | [239](https://www.adafruit.com/product/239) |
| 1 | Breadboarding wire bundle | [153](https://www.adafruit.com/product/153) |
| 1 | Premium Female/Male Jumper Wires, 40 × 150 mm | [826](https://www.adafruit.com/product/826) (PN532 leads) |
| 1 | Solid-Core Wire Spool, 25 ft, 22 AWG, Red | [288](https://www.adafruit.com/product/288) (power into the breadboard) |
| 1 | Solid-Core Wire Spool, 25 ft, 22 AWG, Black | [290](https://www.adafruit.com/product/290) |

## Terminal base and point-to-point builds add

| Qty | Part | Adafruit / source |
|---|---|---|
| 1 | Perma-Proto Half-sized Breadboard PCB | [1609](https://www.adafruit.com/product/1609): the interface board, laid out like the breadboard |
| 1 | Premium Female/Male Jumper Wires, 40 × 150 mm | [826](https://www.adafruit.com/product/826): PN532 leads; for point-to-point also the ESP32 leads (female end on the pin, male end cut off and soldered) |
| 1 | Lonely Binary ESP32-S3 pluggable terminal-block base | Lonely Binary (terminal base build only) |

## If you use a charger you already have

Any USB-C charger of **20 W or more** works instead of the Raspberry Pi
supply: at 5 V, USB-C gives up to 3 A. Use a USB-C cable rated for 3 A or
more, such as Adafruit's
[USB C to USB C Cable with E-Mark, 1 m (4199)](https://www.adafruit.com/product/4199).

## Current budget with these parts

| Load | Worst case |
|---|---|
| NeoPixel Ring 24, full white (60 mA per LED, Adafruit) | 1.44 A |
| MAX98357A into 4 Ω at full volume (Adafruit: up to 650 mA) | 0.65 A |
| ESP32-S3 board (*estimate*) | 0.50 A |
| PN532 module (*estimate*) | 0.15 A |
| 74AHCT125, pull-ups | 0.01 A |
| **Total** | **≈ 2.75 A**, within 3 A |

That worst case stacks every maximum at once: the ring at full white
(the firmware only does that if Home Assistant asks), full volume and a
Wi-Fi transmit peak. In normal use the reader draws about 0.3 A idle and
about 1.4 A during a welcome.
