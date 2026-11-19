# Build the compact (solderless) reader: step by step


The point-to-point build with **nothing soldered on the breadboard**: the
interface board is a **400-point half breadboard** at the same holes, and the
ESP32 stays in its **screwless terminal holder** (or uses female-to-male
jumpers on its pins). See the [compact diagram](../../docs/reader-compact.svg).

**Tested** (18 Nov 2026): power, the NFC reader (bands read, known bands
welcomed, unknown denied) and the amplifier at 100 %, first on USB, then on
the USB-C PD supply with the hubs (lowest reading under load: 4.95 V). Only
the ring is still to be tested.

**Rules for the whole build**

- **Unplug the power before changing any wiring.**
- **USB and the charger never feed the ESP32 together.** Once the hubs are
  fitted, unclip the **ESP32's 5 V wire** from the 5 V hub before plugging
  USB into the ESP32, and put it back afterwards.
- **Red is 5 V, black is ground**, everywhere.
- Any check that fails: stop and fix it before going on. The breadboard
  guide's [troubleshooting table](../reader-breadboard/build.md#troubleshooting)
  applies here too.

**Software:** Home Assistant with the ESPHome integration, and
[HACS](https://hacs.xyz) for the MagicbHAnds integration; Chrome or Edge on a
computer for the web installer, and a USB-C **data** cable (if the board isn't
detected, hold **BOOT**, press **RST**, then release BOOT). Add each new board
in Home Assistant as soon as it's discovered, on a network you trust (see
[docs/security.md](../../docs/security.md)).

### What you need

The [breadboard build's parts](../reader-breadboard/build.md#before-you-start)
(without its large breadboard), the 74AHCT125 and resistors from the
[wired build's list](../reader-wired/build.md#before-you-start), plus:

- a **400-point half breadboard**;
- **male-to-male** jumpers;
- **male-to-female** jumpers. If you only have male-to-male and
  female-to-female, push one into the other to make one;
- a soldering iron, for the PN532's header only;
- a multimeter.

Until the ring, the PD trigger and the lever connectors are fitted, it runs
from the **ESP32's own USB port**. On USB alone the board's 5V pin feeds the
breadboard's rails (about 4.6–4.9 V). Never connect the USB-C charger or PD
trigger at the same time.

### 1. Flash the ESP32

Install from the [web installer](https://legal-copy7045.github.io/Magic-bHAnds/)
over the **UART** port, enter Wi-Fi, and add the reader in Home Assistant.
Leave **Allow the device to perform Home Assistant actions** (ESPHome → the
reader → Configure) **off**: tag scans don't need it (see
[docs/security.md](../../docs/security.md)). Set **LED count** under the
reader's **Configuration** once it's online.

### 2. Solder the PN532's header

1. Use the **4-pin** right-angle header in the holes marked **GND, VCC,
   SDA, SCL**. Leave the 8-pin row (SPI) empty.
2. Push the short legs in from the **top** (the side with the labels and the
   chip). The plastic strip sits on top; the long legs point straight out
   past the board's edge.
3. Solder on the **bottom**: one pin first, check the header sits square,
   then the other three.
4. Check with the meter on continuity: **GND–VCC, VCC–SDA, SDA–SCL** must
   not beep.
5. Set the mode switches: **1 ON, 2 OFF** (I²C).

### 3. Check the breadboard

- Row 1 at the top, columns **a–e** left and **f–j** right.
- **L+ / L−** are the left-hand **+** and **−** rails, **R+ / R−** the
  right-hand ones (go by the colour markings).
- Each rail beeps from top to bottom.
- **a5–e5** beeps; **e5–f5** (across the middle gap) doesn't.
- A 400-point board's rails have 25 holes in groups of 5, so they don't line
  up with the row numbers. Any hole on the right rail will do: "L−10" means
  the left − rail, near row 10.

### 4. Pull-up resistors

- 4.7 kΩ (yellow, violet, red) from **a2 to a6**, and another from
  **b2 to b7**, lying flat.
- Check: **c2–c6** and **c2–c7** read about **4.7 kΩ**, **c6–c7** about
  **9.4 kΩ**.

### 5. Level-shifter links (chip not fitted yet)

| Left side | Right side | Rails |
|---|---|---|
| a10 → L− | j9 → R− | **L+20 → R+20** |
| a13 → L+ | j10 → R+ | **L−21 → R−21** |
| a14 → L− | j11 → R+ | |
| a16 → L− | j12 → R− | |
| | j14 → R+ | |
| | j15 → R− | |

Fit **0.1 µF** across **h9–h10**: a ceramic "104" either way round, or a
0.1 µF electrolytic with its **stripe in h9**.

### 6. Check the links

Meter on continuity:

- **To L−** (beep): e10, e14, e16, f12, f15, h9.
- **To L+** (beep): e13, f10, f11, f14, h10.
- **L+–R+** and **L−–R−** beep (the rail bridges).
- **L+–L−** gives no steady beep (a short chirp from the capacitor is fine).

If the right-hand ground holes (f12, f15, h9) don't beep, the **L−21 → R−21**
bridge is missing.

### 7. Fit the 74AHCT125

- Straighten its legs against the table first.
- Fit it **notch towards row 1** with **pin 1 in e10**: pins 1–7 down
  column e (rows 10–16), pins 14–8 down column f.
- Press it in evenly, and check no leg has folded under.

### 8. Connect the ESP32 (USB unplugged)

From the holder's terminals with male-to-male jumpers (press the terminal's
release, push the pin in, let go, tug to check), or from the ESP32's pins
with male-to-female jumpers. Go by the printed labels:

| ESP32 | Breadboard |
|---|---|
| **3V3** | **c2** (any of a2–e2 is the same connection) |
| **8** | **d6** |
| **9** | **d7** |
| **10** | **d11** |
| **5V** | **L+**, near row 28 |
| **GND** (any) | **L−**, near row 29 |

### 9. Power up

1. With USB unplugged, check: **L+–L−** gives no steady beep; **c2–L+**
   doesn't beep; **c2–L−** gives no steady beep.
2. Plug USB into the ESP32's **UART** port.
3. Measure: **L+–L−** about 4.6–4.9 V; **c2–L−** 3.2–3.4 V.
4. The reader shows **online** in Home Assistant.

### 10. PN532: check it before connecting its data lines

1. USB unplugged. Plug the PN532's header legs into **a24–a27**, one per
   row; it stands on its edge. Note which row each pin landed in (here
   **GND 24, VCC 25, SDA 26, SCL 27**).
2. Jumpers: **GND row → L−**, **VCC row → L+**. Leave SDA and SCL loose.
3. Plug USB in and measure to L−: VCC about 4.6–4.9 V, **SDA and SCL below
   3.6 V** (2.3 V and 1.1 V on the tested board).
   - **Near 5 V: stop.** That module would damage the ESP32.

### 11. PN532: data lines

1. USB unplugged. Jumpers: **SDA row → c6**, **SCL row → c7**.
2. Plug USB in. This restarts the reader, which only looks for the PN532 at
   start-up.
3. **c6** and **c7** read 3.2–3.4 V to L−.
4. The web installer's **Logs & console** (USB is plugged in; press **RST**
   to see start-up) shows no `Error sending version command`, which would
   mean the PN532 isn't answering.
5. Tap a band flat on the PN532's antenna. **Last band ID** shows its ID (and
   **Last band name** its name, once the MagicbHAnds integration is set up),
   and a band nobody owns is **denied**: the reader's **Band scan** event shows
   *denied* (there's no ring or speaker yet, so nothing lights or sounds).

### 12. Let a band in

1. **Settings → Devices & services → MagicbHAnds → Configure → Add or assign
   a band**: pick the band, choose its owner, submit. (Several bands for one
   person: **Enrol bands** next to their name on the MagicbHAnds page, then
   tap them one after another.)
2. The reader's **Known bands** goes up by one within seconds.
3. Tap again: **welcomed**.

Linking the band's Bluetooth side (**Configure → Link a band's Bluetooth**)
passes ownership across if the NFC band has no owner yet. Linking alone
used to drop it, before 0.9.7.

### 13. Amplifier (USB unplugged)

| Connection | Holes |
|---|---|
| ESP32 **5** / **6** / **7** | **f17** / **f18** / **f19** |
| 100 µF | **stripe in g23**, other leg **g24** |
| Ground | **L− → f23** |
| Amplifier cable (by the labels on the amplifier) | **LRC h17**, **BCLK h18**, **DIN h19**, **GND h23**, **VIN h24** |
| Speaker | into the amplifier's 2-pin socket |

Leave the amplifier's 5 V (**L+ → f24**) off for now.

### 14. Power up the amplifier

1. With USB unplugged, check: **f23–L−** beeps; **f24–L−** gives no steady
   beep; **f17, f18, f19** don't beep to L−.
2. Plug USB in. Set the reader's **Speaker** volume to about 30 %.
3. Fit **L+ → f24** with it running. **f24–L−** reads about 4.6–4.9 V.
4. Tap a band: tap-in sound (known) or error sound (unknown).
5. Raise the volume a step at a time. On the tested build, 100 % ran from a
   USB supply without the reader restarting. If yours restarts, step back
   down until the PD supply is fitted.

### 15. The ring (power off)


1. Solder the ring's wires with the 470 Ω at DIN and the 1000 µF across its
   pads ([breadboard step 5](../reader-breadboard/build.md#step-5-wire-the-led-ring)).
2. Connect its data to **c12** through the 470 Ω. Its power goes to the hubs
   in the next step (port 4).

### 16. Power: PD trigger and hubs (tested 18 Nov 2026)

Set the PD trigger to 5 V (it read 5.1 V), then make up the two 5-way
lever-connector hubs:

  | Port | 5 V hub | GND hub |
  |---|---|---|
  | 1 | PD trigger **+** | PD trigger **−** |
  | 2 | **L+** rail (near row 25) | **L−** rail (near row 26) |
  | 3 | Amplifier **f24** (remove the L+ → f24 jumper) | Amplifier **f23** (remove the L− → f23 jumper) |
  | 4 | Ring 5V | Ring GND |
  | 5 | ESP32 5V (a wire soldered to the holder's 5V pad; remove its 5V → L+ jumper) | ESP32 GND (soldered to the holder's GND pad) |

  - **Keep a short ground jumper from the ESP32 to the breadboard**
    (the holder's GND terminal → **L−**), and add **L− → f23** for the
    amplifier, as well as their hub wires. Without them the sound
    signals' only ground return runs through the hub, and the sound
    **crackles at any volume** on the PD supply.
  - The ESP32's 5 V wire in the hub is now the one to unclip before
    using USB.

### 17. First power-up on the charger

1. Unclip the ESP32's 5 V from the hub. Plug in the charger. Measure the 5 V
   hub to GND: **4.75–5.25 V**. Unplug the charger, clip the ESP32's 5 V back,
   plug the charger in again.
2. The reader comes online in Home Assistant, the start-up sound plays and
   the idle glow shows. Turn on **Ring**: red, green and blue at 100 % on all
   LEDs. Set **LED count** to your ring's, and **LED colour order** if the
   colours are swapped.
3. Tap a known band: the ring pulses in the welcome colour with the tap-in
   sound; an unknown band gets two red pulses and the error sound.

### 18. Load test

1. **Ring** white at 100 %, **Speaker** volume 100 %, press **Test welcome**
   for a minute, then tap bands.
2. The 5 V hub stays **at least 4.75 V** (tested: never below **4.95 V**, the
   sound stayed clean); the reader doesn't restart (no start-up sound, it
   stays online); nothing gets more than barely warm.

### 19. Final checks and the case

Run the [checklist in hardware/README.md](../README.md#checking-a-build-works),
then fit everything in its case: no metal between the PN532's antenna and the
band, and the ESP32 and its USB port out of reach (see
[docs/security.md](../../docs/security.md)). Repeat the NFC and Bluetooth
checks with it closed up.

### Other tag automations

Every tap is a Home Assistant **tag scan**, so any automation that triggers
on *any* `tag_scanned` event (for example, one that logs NFC tags around the
house) will run for band taps too. Make it ignore readers with this
condition:

```yaml
conditions:
  - condition: template
    value_template: >-
      {% set d = trigger.event.data.device_id %}{{ not d or 'magicband' not in (device_attr(d, 'model') or '') }}
```

The `not d` part matters: `device_attr` raises an error when a scan has no
device.
