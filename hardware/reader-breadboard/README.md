# MagicBand Reader: breadboard proof of concept

The reference build: one ESP32-S3 dev board, a PN532 NFC reader, one LED
ring, a MAX98357A amplifier and speaker, on a single full-size breadboard,
powered from a USB-C charger (20 W or more). Everything else (terminal base,
point-to-point, PCB) should be checked against this build once it works.

![Breadboard layout](../../docs/reader-breadboard.svg)

**Status:** reviewed against manufacturer documents (sources at the end),
**not yet built**. Nothing here is proven until the
[build and test sequence](#build-and-test-sequence) passes on real parts.
Items marked *estimate* are engineering estimates, not datasheet values.

## Verdict

**Ready to build** with the parts, wiring and power arrangement below. This
replaces the earlier breadboard documentation, which had these problems:

| # | Problem in the earlier documentation | Correction |
|---|---|---|
| 1 | The ESP32 board was drawn mirrored (J1 on the right) with its headers 11 holes apart. Viewed from the top with the antenna up, J1 is on the **left**, and the headers are **9 holes** (22.86 mm) apart. | One breadboard, J1 in column c, J3 in column j |
| 2 | LED power ran through the breadboard rails and jumper wires | LED power comes straight from two lever-connector hubs |
| 3 | PN532 VCC was 5 V in one table and 3V3 in another; no I²C pull-ups | PN532 on **5 V**, plus 2 × 4.7 kΩ pull-ups to 3.3 V (the module has none on its header side) |
| 4 | 330 Ω resistor at the level shifter | At the **ring end** of the data wire (Adafruit's guidance) |
| 5 | 0.1 µF decoupling drawn but not in the parts list; capacitors had no voltage ratings | Listed below with ratings and positions |
| 6 | Nothing stopped USB and the 5 V supply feeding the ESP32 together | One jumper (a21) to remove before plugging in USB |
| 7 | No check for split breadboard rails | Rail bridges fitted, and a continuity check |
| 8 | 24 + 12 LEDs could draw ≈ 3.5 A in total, over a 3 A supply | **Ring only** (16 or 24 LEDs): ≈ 2.1–2.6 A worst case |

## Parts

| Qty | Part | Specification | Notes |
|---|---|---|---|
| 1 | ESP32-S3 dev board | **ESP32-S3-DevKitC-1-N16R8** layout (Espressif, or Lonely Binary N16R8), headers fitted | The firmware needs 16 MB flash and octal PSRAM. Check a clone's pin labels match the [pinout](#esp32-s3-devkitc-1-j1-pins-used) |
| 1 | NFC reader | **PN532 NFC module V3** (Elechouse, or a clone such as AITRIP), with its 4-pin header | Set to I²C (switch 1 ON, switch 2 OFF) |
| 1 | LED ring | **Adafruit NeoPixel Ring, 24 × 5050 RGB (product 1586)**: WS2812B or SK6812, 5 V | 52.3 mm inside, so the PN532 fits inside it, clear of the antenna. In a housing a ring won't fit, use a flexible strip instead: [LED options](../shopping-list.md#if-a-ring-wont-fit-flexible-led-options) |
| 1 | Amplifier | **Adafruit MAX98357A I²S amplifier breakout, product 3006** | A clone works if it has the same pins and a 1 MΩ SD resistor |
| 1 | Speaker | **Adafruit Mono Enclosed Speaker, 3 W 4 Ω (product 3351)** | Rated for the amplifier's full 3 W into 4 Ω |
| 1 | Level shifter | **74AHCT125, 14-pin DIP** (Adafruit 1787) | Not the SOT-23 74AHCT1G125, which doesn't fit a breadboard |
| 2 | Resistor | 4.7 kΩ, ¼ W (Adafruit 2783) | I²C pull-ups |
| 1 | Resistor | **470 Ω**, ¼ W (Adafruit 2781) | LED data, at the ring. Adafruit recommends 300–500 Ω |
| 1 | Capacitor | 1000 µF, **10 V** or higher, radial electrolytic, 105 °C (not sold by Adafruit) | Across the ring's 5V/GND pads |
| 1 | Capacitor | 100 µF, **16 V**, radial electrolytic (Adafruit 2193) | Amplifier supply |
| 1 | Capacitor | 0.1 µF ceramic (Adafruit 753) | 74AHCT125 supply |
| 1 | Breadboard | Full-size **830-point**, 63 rows, power rails both sides (Adafruit 239) | |
| 2 | Lever connectors | **Snap-action 5-wire block connector**, 12–24 AWG, 32 A (Adafruit 874, pack of 3) | One for 5 V, one for GND |
| 1 | USB-C breakout | **Adafruit USB Type C Power Delivery Dummy Breakout, HUSB238 (product 5807)**, set to **5 V 3 A**: keep the 5V jumper, **cut the 1A jumper** (2A stays open) | Rated to 20 V 5 A, with a terminal block. See [Power](#power) |
| 1 | Power supply | **Raspberry Pi 27 W PD power supply, 5.1 V 5 A (Adafruit 5814)**, or any **USB-C charger of 20 W or more** with a 3 A cable | At 5 V a USB-C charger gives at most 3 A |
| — | Wire | **22 AWG stranded** red/black (Adafruit 3068, 2976) for the supply, ring and amplifier runs; **22 AWG solid** red/black (Adafruit 288, 290) for wires into the breadboard | Keep the supply-to-hub run under 30 cm and the ring run under 50 cm |
| — | Jumpers | Breadboarding wire bundle (Adafruit 153); 4 × female/male jumpers, 150 mm (Adafruit 826) for the PN532 | |
| — | Misc | Heat-shrink, multimeter (DC volts, continuity) | |

## Power

### Supply

Use a **USB-C charger of 20 W or more**. Any such charger supplies 3 A at
5 V; more watts don't help, because at 5 V USB-C allows **at most 3 A**
(15 W), and a charger's higher ratings only exist at 9–20 V. The budget
below fits within 3 A.

**USB-C breakout:** the **Adafruit HUSB238 USB-C Power Delivery breakout
(product 5807)**. It asks the charger for a set voltage and current, chosen
with solder jumpers. Out of the box it asks for 5 V 1 A. For this reader:

- **Keep the 5V jumper closed. Never cut it:** with no voltage jumper
  closed, the board asks for the charger's *highest* voltage (up to 20 V),
  which would destroy the reader.
- **Cut the 1A jumper** and leave 2A open: that selects 3 A.
- Check with a meter before connecting anything: **4.75–5.25 V** across its
  terminal block.

Avoid plain USB-C socket breakouts without CC resistors (such as Adafruit's
"Simple USB C Socket Breakout", 5180): a standards-compliant charger won't
switch on. Adafruit's "USB Type C Breakout Board - Downstream Connection"
(4090) has the 5.1 kΩ CC resistors, but Adafruit describes it as giving up to
1.5 A, short of this reader's worst case.

### Current budget

| Load | Normal | Peak in use | Worst case | Basis |
|---|---|---|---|---|
| ESP32-S3 board (Wi-Fi + Bluetooth) | 0.15 A | 0.35 A | 0.50 A | *estimate* (Espressif's chip datasheet couldn't be retrieved) |
| PN532 module (polling every 250 ms) | 0.10 A | 0.15 A | 0.15 A | *estimate* (NXP datasheet couldn't be retrieved) |
| LED ring, 24 × WS2812B | 0.05 A (idle glow) | 0.48 A (welcome, full green) | **1.44 A** (full white) | 60 mA per LED at full white (Adafruit); one colour *estimated* at a third of that |
| MAX98357A + 4 Ω speaker | 0.003 A | 0.30 A | 0.65 A | 2.4 mA quiescent (datasheet); up to 650 mA at 5 V into 4 Ω (Adafruit) |
| 74AHCT125, pull-ups, board LEDs | 0.01 A | 0.01 A | 0.01 A | 74AHCT125 ≤ 20 µA (TI) |
| **Total** | **≈ 0.3 A** | **≈ 1.4 A** | **≈ 2.75 A** | |

- **Normal** is idle: the ring glowing white at 30 % (ESPHome's gamma
  correction makes that about 3 % of full power), nothing playing.
- **Peak in use** is a welcome: ring full green, sound playing.
- **Worst case** is Home Assistant setting the ring to full white while a
  sound plays at full volume and Wi-Fi transmits. The firmware has no
  brightness cap.
- **Headroom on 3 A:** about 8 % in that worst case, which stacks every
  maximum at once. In use the reader stays under half the supply.

### Distribution

```
USB-C charger ─ USB-C breakout ─(22 AWG)─┬─ 5 V hub ──┬─(22 AWG solid)─ breadboard L+ rail (row 24): ESP32 5V pin, PN532, 74AHCT125
                                         │            ├─(22 AWG solid)─ amplifier Vin (f52)
                                         │            └─(22 AWG)─────── LED ring 5V pad  (+1000 µF there)
                                         └─ GND hub ──┬─(22 AWG solid)─ breadboard L− rail (row 25)
                                                      ├─(22 AWG solid)─ amplifier GND (f51)
                                                      └─(22 AWG)─────── LED ring GND pad
```

- **One ground point:** every ground meets at the GND hub. The ring's and
  amplifier's currents never flow through the breadboard.
- **The breadboard rails carry only the ESP32, PN532 and level shifter**
  (≤ 0.7 A worst case).
- Keep the hubs within about 30 cm of the breadboard and the ring. With
  22 AWG (about 53 mΩ/m), 1.44 A over 0.5 m each way drops about 80 mV,
  and 2.75 A over 0.3 m each way about 90 mV. The Raspberry Pi supply's
  5.1 V output leaves room for that.
- **USB and the 5 V supply must never feed the ESP32 together.** Espressif
  lists USB, the 5V pin and the 3V3 pin as mutually exclusive power options.
  The board's USB ports feed its 5 V through Schottky diodes, so the charger
  can't push current into your computer. With the charger off and USB in,
  though, your computer would try to power the whole 5 V rail. So:
  **pull the a21 jumper before plugging USB into the ESP32**, and put it
  back afterwards.

## Wiring

Holes are named by column and row (`a21`) or rail and row (`L+24`: left
red rail at row 24). Rows run 1–63 from the top; columns are `L−` `L+` `a–e`
(channel) `f–j` `R+` `R−`.

### Placement

| Part | Holes | Orientation |
|---|---|---|
| ESP32-S3-DevKitC-1 | J1 in **c1–c22**, J3 in **j1–j22** | Antenna towards row 1, USB ports towards row 25, component side up |
| 4.7 kΩ (SDA pull-up) | a26 – a30 | Lying flat |
| 4.7 kΩ (SCL pull-up) | b26 – b31 | Lying flat |
| 74AHCT125 | pin 1 in **e34**, pins 1–7 down column e (rows 34–40), pins 14–8 down column f | Notch towards row 1 |
| 0.1 µF ceramic | h33 – h34 | |
| Adafruit MAX98357A | header in **h46–h52** (LRC, BCLK, DIN, GAIN, SD, GND, Vin top to bottom) | Board overhangs the right-hand rails |
| 100 µF electrolytic | **g51 (−)**, g52 (+) | Stripe towards row 51 |

### Connections

| From | To | Signal | Notes |
|---|---|---|---|
| USB-C breakout terminal **+** | 5 V hub | 5 V | 22 AWG stranded red, ≤ 30 cm |
| USB-C breakout terminal **−** | GND hub | GND | 22 AWG stranded black, ≤ 30 cm |
| 5 V hub | L+24 | 5 V to the breadboard | 22 AWG solid red |
| GND hub | L−25 | GND to the breadboard | 22 AWG solid black |
| L+29 | L+35 | 5 V rail bridge | Bridges a rail split; harmless if there's none |
| L−30 | L−36 | GND rail bridge | As above |
| L+42 | R+42 | 5 V to the right rail | |
| L−43 | R−43 | GND to the right rail | |
| a21 (ESP32 **5V** pin) | L+21 | 5 V into the ESP32 | **Remove before plugging in USB** |
| a22 (ESP32 **GND**) | L−22 | GND | |
| b1 (ESP32 **3V3**) | e26 | 3.3 V for the pull-ups | |
| a12 (**GPIO8**) | e30 | I²C SDA | |
| a15 (**GPIO9**) | e31 | I²C SCL | |
| c30 | PN532 **SDA** | I²C SDA | female-to-male jumper |
| c31 | PN532 **SCL** | I²C SCL | female-to-male jumper |
| L+27 | PN532 **VCC** | 5 V | female-to-male jumper |
| L−28 | PN532 **GND** | GND | female-to-male jumper |
| b16 (**GPIO10**) | d35 (74AHCT125 pin 2, 1A) | LED data, 3.3 V | |
| a34 (pin 1, 1OE) | L−34 | Enables channel 1 | |
| a37 (pin 4, 2OE) | L+37 | Disables channel 2 | |
| a38 (pin 5, 2A) | L−38 | Unused input to GND | TI: unused inputs must be tied |
| a40 (pin 7, GND) | L−40 | IC ground | |
| j34 (pin 14, VCC) | R+34 | IC supply, 5 V | |
| j35 (pin 13, 4OE) | R+35 | Disables channel 4 | |
| j36 (pin 12, 4A) | R−36 | Unused input to GND | |
| j38 (pin 10, 3OE) | R+38 | Disables channel 3 | |
| j39 (pin 9, 3A) | R−39 | Unused input to GND | |
| j33 | R−33 | Grounds row 33 for the 0.1 µF | |
| c36 (pin 3, 1Y) | 470 Ω → ring **DIN** | LED data, 5 V | 22 AWG; the resistor is soldered inline at the ring end, in heat-shrink |
| b5 (**GPIO5**) | f46 | I²S LRC | |
| b6 (**GPIO6**) | f47 | I²S BCLK | |
| b7 (**GPIO7**) | f48 | I²S DIN | |
| 5 V hub | f52 | Amplifier Vin | 22 AWG solid red |
| GND hub | f51 | Amplifier GND | 22 AWG solid black |
| 5 V hub | Ring **5V** pad | LED power | 22 AWG stranded red, ≤ 50 cm |
| GND hub | Ring **GND** pad | LED power return | 22 AWG stranded black, ≤ 50 cm |
| 1000 µF + / − | Ring 5V / GND pads | Bulk capacitor | Soldered at the ring, stripe to GND |
| Amplifier + / − terminal | Speaker | Audio | 22 AWG. Neither terminal is ground (bridge-tied output) |

Left unconnected: amplifier GAIN (9 dB) and SD (the board's 1 MΩ gives
(L+R)/2 mono); 74AHCT125 pins 6, 8 and 11 (unused outputs); ESP32 J3.

### ESP32-S3-DevKitC-1 J1 pins used

From Espressif's v1.1 pin table, pin 1 nearest the antenna: 1 **3V3**, 2 3V3,
3 RST, 4 GPIO4, 5 **GPIO5**, 6 **GPIO6**, 7 **GPIO7**, 8 GPIO15, 9 GPIO16,
10 GPIO17, 11 GPIO18, 12 **GPIO8**, 13 GPIO3, 14 GPIO46, 15 **GPIO9**,
16 **GPIO10**, 17–20 GPIO11–14, 21 **5V**, 22 **GND**. On the breadboard,
pin *n* is row *n*.

None of the used GPIOs is a strapping pin (GPIO0, 3, 45 and 46 are) or used
by the board's flash and PSRAM (GPIO35–37).

## Component review

| Component | Selection | Verdict | Required change | Reason |
|---|---|---|---|---|
| ESP32-S3 board | DevKitC-1 N16R8 / Lonely Binary N16R8 | PASS WITH CONDITIONS | Check a clone's pin labels against the table above | Pinout, 5 V input path and regulator verified on Espressif's v1.1 schematic. Not verified for the Lonely Binary board |
| GPIO assignment | 5, 6, 7 I²S; 8, 9 I²C; 10 LEDs | PASS | — | No strapping, USB, flash or PSRAM pins; matches the firmware |
| PN532 module | V3 (Elechouse / AITRIP clone) | PASS WITH CONDITIONS | VCC on 5 V; add 4.7 kΩ pull-ups; check the clone (test stage 2) | Elechouse schematic: MOSFET level shifter, 4.7 kΩ pull-ups only on the chip side (to its own 3.3 V), no pull-ups on the header. The clone isn't verified |
| PN532 supply voltage | 5 V vs 3.3 V (docs conflicted) | CHANGE REQUIRED | 5 V | The module feeds VCC to the PN532's VBAT. At 3.3 V the reset divider (10 k/20 k) gives about 2.2 V |
| WS2812B LEDs | 24 ring + 12 Mickey | CHANGE REQUIRED | Ring only, 16 or 24 | 36 LEDs at full white (2.16 A) plus the rest exceeds 3 A |
| Level shifter | 74AHCT125 / 74AHCT1G125 | PASS (SN74AHCT125N) | Use the DIP version | WS2812B needs 0.7 × VDD = 3.5 V high; 74AHCT125 accepts 2.0 V and outputs ≥ 3.8 V (TI) |
| 330 Ω resistor | At the shifter | PASS WITH CONDITIONS | 470 Ω (Adafruit sells no 330 Ω), at the ring end | Adafruit: "at the end of the wire closest to the NeoPixel(s)" |
| 1000 µF capacitor | No rating or position given | PASS WITH CONDITIONS | 10 V, at the ring's pads | Adafruit: 500–1000 µF, 6.3 V or higher |
| 0.1 µF capacitor | Drawn, not listed | CHANGE REQUIRED | Add to the parts list, at the IC | Standard supply decoupling |
| I²C pull-ups | None | CHANGE REQUIRED | 2 × 4.7 kΩ to 3.3 V | The module's header side has none; the ESP32's internal pull-ups are weak |
| MAX98357A | Adafruit 3006 | PASS WITH CONDITIONS | Own supply wires; 100 µF at Vin | 2.5–5.5 V supply, 1.3 V logic threshold (datasheet); Adafruit budgets 650–800 mA |
| Speaker | 3 W, 4–8 Ω | PASS | Adafruit 3351, 3 W 4 Ω | Rated for the amplifier's 3 W into 4 Ω; 0.65 A fits the budget |
| Power supply | 5 V 3 A | PASS WITH CONDITIONS | USB-C charger ≥ 20 W; ring only; USB-C breakout with CC resistors | Worst case ≈ 2.6 A |
| Power distribution | Breadboard rails | CHANGE REQUIRED | Hubs; LED and amplifier wired directly | Breadboard contacts aren't meant for amps of LED current |
| Firmware | `magicband-reader.yaml` | PASS | — | See below |

## Firmware cross-check

Checked against `esphome/magicband-reader.yaml` and ESPHome's source:

- **I²C:** SDA GPIO8, SCL GPIO9, 50 kHz (ESPHome default), internal pull-ups
  on (default; they sit in parallel with the 4.7 kΩ), bus scan on.
- **PN532:** `pn532_i2c`, address 0x24 (ESPHome default), polled every 250 ms.
- **LEDs:** `esp32_rmt_led_strip` on GPIO10, WS2812, **GRB** (the WS2812B
  datasheet's order; `ring_color_order` changes it), `ring_leds` LEDs
  (default 24), off at boot, gamma 2.8.
  **There's no brightness cap**, which is why the supply is sized for full
  white.
- **I²S:** LRCLK GPIO5, BCLK GPIO6, DOUT GPIO7, external DAC, mono. The
  MAX98357A needs no MCLK. *Not verified:* whether ESPHome's mono mode fills
  one I²S slot or both. If only one, the (L+R)/2 mix halves the level, which
  only affects volume.
- **Logs:** on UART0, so use the board's **UART** USB port for the first
  install and serial logs.

## Build and test sequence

Do each stage in order. Unplug the charger before changing any wiring.

**Stage 0: breadboard.** With the meter on continuity, check each rail from
row 1 to row 63. If a rail is split, the bridge jumpers (L+29–35, L−30–36)
fix it. Fit them anyway.

**Stage 1: ESP32 and power.**
1. Insert the ESP32 only. With USB on the **UART** port and nothing else
   connected, install the reader firmware from the web installer and set up
   Wi-Fi. Unplug USB.
2. Set up the USB-C breakout (5V jumper closed, 1A jumper cut), plug in
   the charger, and measure **4.75–5.25 V** at its terminals before wiring
   anything to it. Unplug, then wire the hubs and rail feeds, and fit a21
   and a22. Connect the charger.
3. Measure: hub 5 V to GND **4.75–5.25 V**; ESP32 5V pin 4.75–5.25 V; 3V3
   pin **3.2–3.4 V**.
4. Logs (Home Assistant → ESPHome → the reader → Logs): it boots and
   connects to Wi-Fi. *Expected warnings:* the PN532 isn't found yet.
5. **Stop if:** the rail is below 4.75 V, the charger cuts out, or anything
   gets warm.

**Stage 2: PN532.**
1. **Check the module first**, on its own: power it from the 5 V hub
   (VCC, GND only, nothing on SDA/SCL). Measure SDA and SCL to GND: they must
   read **below 3.6 V** (expect roughly 2.5–3.3 V or near 0). **Stop if
   either reads near 5 V**: that clone has pull-ups to 5 V and mustn't be
   connected to the ESP32. Set switch 1 ON, switch 2 OFF.
2. Unplug, fit the pull-ups and the four PN532 jumpers, and power up.
3. Measure: PN532 VCC 4.75–5.25 V; SDA and SCL idle at **3.2–3.4 V**.
4. Logs: the I²C scan finds a device at **0x24**, and the PN532 reports its
   firmware version with no errors. Tap a band: its ID appears in the log.
5. **Stop if:** no device at 0x24 (check the switches and the SDA/SCL
   order), or setup errors repeat.

**Stage 3: level shifter and ring.**
1. Fit the 74AHCT125, its tie-off jumpers, 0.1 µF and the rail bridges at
   rows 42–43. Before fitting the chip, check with the meter: e34, a38, j36,
   j39 to GND = 0 Ω; j34, a37, j35, j38 to 5 V = 0 Ω.
2. Wire the ring: 5V/GND from the hubs, 1000 µF at its pads (stripe to
   GND), data from c36 through the 470 Ω at the ring end. Connect **ground
   first**, then 5 V, then data.
3. Power up. Measure: IC pin 14 to pin 7 = 4.75–5.25 V.
4. In Home Assistant, turn on **Ring**: white 30 %, then red, green and
   blue 100 % each. All LEDs light; colours are correct.
5. **Stop if:** wrong colours (check `ring_leds`, and `ring_color_order`:
   GRB for most NeoPixels, RGB for the 4310 strip), flicker or random
   colours (check the shifter wiring, the 470 Ω and the common ground), or
   the rail drops below 4.75 V.

**Stage 4: amplifier and speaker.**
1. Fit the amplifier, its supply wires from the hubs, the 100 µF and the
   three I²S jumpers; connect the speaker.
2. Power up. Measure: amplifier Vin to GND 4.75–5.25 V; SD pin to GND about
   **0.45 V** (between 0.16 and 0.77 V means mono mix).
3. The start-up sound plays. Press **Test welcome**: the ring turns green
   and the tap-in sound plays.
4. **Stop if:** no sound (check LRC/BCLK/DIN order, and SD isn't at 0 V),
   loud hum, or the ESP32 restarts when sound plays.

**Stage 5: everything at once (load test).**
1. Set **Ring** to white 100 % and the **Speaker** volume to 100 %, and
   press **Test welcome** repeatedly for a minute, then tap bands.
2. Measure the hub voltage while that runs: **at least 4.75 V**. If your
   meter can measure up to 10 A, the charger-to-hub current should stay
   **under 3 A** (expect ≈ 1.5–2.6 A).
3. Afterwards, check the ESP32's *Uptime* hasn't reset, and nothing is hot:
   the power wires, hubs, USB-C breakout and the 74AHCT125 should be
   barely warm.
4. **Stop if:** the voltage dips below 4.75 V, the charger cuts out, the
   ESP32 restarts, or anything is hot.

Then run the full checklist in
[hardware/README.md](../README.md#checking-a-build-works).

## Sources

- Espressif ESP32-S3-DevKitC-1 v1.1 user guide (pin tables, power options),
  board schematic (USB-to-5V Schottky diodes, SGM2212-3.3 regulator) and
  PCB drawing (25.40 mm board, header positions, J1/J3 sides).
- Elechouse PN532 NFC RFID Module User Guide V3 and module schematic
  (switch settings, header order, level shifter, pull-ups, VCC to VBAT).
- TI SN74AHCT125 datasheet (supply range, input thresholds, output levels,
  pinout, unused inputs).
- Worldsemi WS2812B datasheet (supply limits, VIH = 0.7 × VDD, GRB order).
- Analog Devices MAX98357A datasheet and Adafruit's MAX98357 guide (supply,
  logic levels, output power, SD/MODE, gain, supply current).
- Adafruit NeoPixel Überguide (60 mA per LED, bulk capacitor, data
  resistor placement, connection order).
- ESPHome 2026.10 source (I²C and PN532 defaults, gamma).

Not retrieved: Espressif's ESP32-S3 chip and WROOM-1 module datasheets, and
NXP's PN532 datasheet. The ESP32 and PN532 currents above are estimates.
