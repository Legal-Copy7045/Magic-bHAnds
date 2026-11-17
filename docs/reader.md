# MagicBand Reader

A park-style touch point for Home Assistant. Tap an **original MagicBand** or a
**MagicBand+** on it: the ring spins, Home Assistant gets the band's ID, the
ring turns green with a chime, and a MagicBand+ also lights up green
and buzzes.

Config: [`esphome/magicband-reader.yaml`](../esphome/magicband-reader.yaml).

Inspired by
[foolishmortalbuilders/magicbandreader](https://github.com/foolishmortalbuilders/magicbandreader),
[dcivitano/Magic-Band-Reader](https://github.com/dcivitano/Magic-Band-Reader) and
[ncory/MagicReader](https://github.com/ncory/MagicReader). Like them, it
identifies bands by their NFC ID. Unlike them, it runs on one ESP32 with
ESPHome and connects to Home Assistant natively (Tags, entities, actions). No
code from those projects is used.

## Ways to build it

Breadboard (start here), Lonely Binary terminal base or point-to-point
wiring. They share the parts, GPIOs and features. See
**[hardware/README.md](../hardware/README.md)** for a comparison and a
step-by-step check that a build works.

## How bands are read

Both band types contain a standard 13.56 MHz NFC chip (ISO 14443-A) with a
fixed ID, which is the same ID a phone app such as *NFC Tools* shows. The
reader only reads that ID, so no encrypted Disney data is involved. Original
MagicBands give a 7-byte ID like `04-53-65-2A-C0-5F-80`.

## Parts and wiring (breadboard)

**Parts: the [shopping list](../hardware/shopping-list.md)** (the generic
parts the guides use, and their Adafruit equivalents).

**Build it: the [step-by-step breadboard build](../hardware/reader-breadboard/build.md)**,
with a check after each stage. The [build spec](../hardware/reader-breadboard/README.md)
behind it has the reviewed parts list, the hole-by-hole wiring and the
power budget.

![Breadboard layout](reader-breadboard.svg)

In short:

| Part | Specification |
|---|---|
| ESP32-S3 dev board | ESP32-S3-DevKitC-1 **N16R8** layout (Lonely Binary N16R8, or Espressif) |
| NFC reader | **PN532 NFC module V3** (AITRIP, Elechouse or similar), switches set to **I²C** (1 ON, 2 OFF), powered from **5 V**, with two 4.7 kΩ pull-ups to 3.3 V |
| LED ring | Any **5 V WS2812B ring** big enough for the PN532 to sit inside (the guides use a 35-LED ring, 78 mm inside; Adafruit's NeoPixel Ring 24 also works). For a housing a ring won't fit, a flexible strip works too: [LED options](../hardware/shopping-list.md#if-a-ring-wont-fit-flexible-led-options) |
| Amplifier + speaker | **MAX98357A** I²S amplifier kit with a **4 Ω 3 W speaker** (or Adafruit's 3006 breakout and 3351 speaker) |
| Level shifter | **SN74AHCT125N** DIP for the LED data line, 470 Ω at the ring end |
| Power | **USB-C charger, 20 W or more**, through a CH224K **USB-C PD trigger set to 5 V** (or Adafruit's HUSB238 set to 5 V 3 A) |

| ESP32-S3 pin | Goes to |
|---|---|
| **5V** | 5 V rail (remove this jumper before plugging USB into the ESP32) |
| **GND** | Ground |
| **3V3** | The two I²C pull-ups |
| **GPIO8** / **GPIO9** | PN532 **SDA** / **SCL** |
| **GPIO10** | 74AHCT125 → 470 Ω → ring **DIN** |
| **GPIO5** / **GPIO6** / **GPIO7** | MAX98357A **LRC** / **BCLK** / **DIN** |

- **LED and amplifier power come straight from two lever-connector hubs**,
  not through the breadboard rails, and every ground meets at the GND hub.
- **Placement:** put the PN532 antenna in the centre of the ring, under the
  lid, with **no metal** between it and the band. Read range is a few
  centimetres through plastic.

### Terminal base and point-to-point builds

Once the breadboard works, the same circuit can be built smaller: on the
Lonely Binary **terminal-block base**, or **point-to-point** with Dupont
leads on the ESP32's pins. Both use a small perfboard **interface board**
for the level shifter and I²C pull-ups, and the same power hubs. See
**[hardware/reader-wired](../hardware/reader-wired/README.md)** for the
hole-by-hole layout and tests.

| Terminal base | Point-to-point |
|---|---|
| ![Terminal base wiring](reader-terminal-base.svg) | ![Point-to-point wiring](reader-point-to-point.svg) |

### Powering it from a USB-C charger

![Power distribution](reader-power.svg)

Use a **USB-C charger of 20 W or more** (Apple 20 W, a laptop charger and
so on). At 5 V, USB-C gives **at most 3 A** whatever the charger's wattage,
which covers a ring-only reader (about 2.75 A worst case). Feed it in
through a **CH224K USB-C PD trigger** with its DIP switch set to 5 V,
checked with a meter and taped down, or an Adafruit HUSB238 breakout set to
5 V 3 A (keep its 5V jumper, cut its 1A jumper). Details and the current
budget:
[breadboard build spec](../hardware/reader-breadboard/README.md#power).

Don't run everything through the ESP32's own USB port. Keep that for the
first install, with the charger unplugged, and pull the ESP32's 5 V jumper
before plugging USB in later.

## Install

**Web installer: https://legal-copy7045.github.io/Magic-bHAnds/** (choose
*Install the reader*).

Install the firmware **before wiring anything else to the ESP32**, as step
1 of the build
([breadboard](../hardware/reader-breadboard/build.md),
[terminal base and point-to-point](../hardware/reader-wired/build.md)).

1. Plug the bare ESP32-S3 into your computer through the USB-C port
   labelled **UART**.
2. Open the web installer in Chrome or Edge, click **Install the reader**,
   then enter your Wi-Fi details when asked. Unplug it, then build the rest.
3. Add it in Home Assistant when it's discovered (ESPHome). Then open
   **Settings → Devices & services → ESPHome → the reader → Configure**, and
   turn on **Allow the device to perform Home Assistant actions**. That's
   needed for tag scans to reach Home Assistant.
4. Install the [MagicBand integration](integration.md) to manage people and
   bands.

Firmware updates then appear in Home Assistant as an update on the reader,
and install over Wi-Fi: no USB needed. If you ever do plug USB into the
built reader (for serial logs), **first disconnect the ESP32's 5 V wire**
from the 5 V rail or hub; the rest can stay powered.
The connection is encrypted: Home Assistant gives each reader its own key when
it first connects.

**Your ring or strip:** the web installer's firmware fits any of them. On
the reader's device page in Home Assistant, under **Configuration**, set:

- **LED count** (1–60, default 24): the number of LEDs in your ring or
  strip. Above 24 the reader caps their output at 24 ÷ count (35 LEDs: 68 %)
  so full white stays within the 20 W supply.
- **LED colour order:** GRB for most NeoPixels and generic WS2812B rings; RGB
  for Adafruit's silicone neon-like strip (4310). If green shows as red,
  switch it.
- **LED brightness** (5–100 %, default 100 %): scales everything the ring
  shows, including the Ring light in Home Assistant. It works on top of the
  power cap, so it can only make the ring dimmer, never over budget.
- **Idle glow** (0–100 %, default 30 %): the white glow while waiting for a
  band; 0 turns the ring off between taps.

**Customising further** (sounds, pins): in the ESPHome Device Builder the
reader shows up with **Take control**, which imports
`esphome/magicband-reader.yaml` as a package; change its substitutions
there.

## Using it with Home Assistant

**Name your bands.** Tap each band once, then go to **Settings → Tags**. Each
band appears with its ID: give it a name ("Alex's MagicBand+").

**React to a band.** Create an automation with the trigger **Tag → Alex's
MagicBand+**, for example to turn on the lounge lights.

**Entities on the reader:**

| Entity | What it does |
|---|---|
| **Ring** | The LED ring as a normal HA light, so you can use it as a night light too. It glows white while idle |
| **Last band** | ID of the last band read |
| **Response mode** | *Known bands only* (default: decided on the reader; new bands are denied), *Welcome every band*, or *Ask Home Assistant* (see below) |
| **Band scan** | Event entity: every scan appears in the logbook as *welcomed* or *denied* |
| **Known bands** | How many bands are on the reader's allowed list |
| **Allow last band**, **Forget last band**, **Forget all bands** | Manage the reader's list by hand, if you don't use the MagicBand integration |
| **Speaker** | Media player: Home Assistant can also play announcements and TTS through the reader |
| **Light up MagicBand+** | Send green + buzz to a MagicBand+ on a successful read (default on) |
| **Sound** | Chimes on/off |
| **Test welcome** | Plays the welcome sequence without a band |
| plus the MagicBand bridge entities | MagicBand light, Buzz, Command, Prefix mode and so on |

### No waiting on Home Assistant

Everything the reader does is handled on the reader itself: reading the band,
lights, sounds and the MagicBand+ feedback. Home Assistant is only told about
the scan, and the reader never waits for it. The one exception is *Ask Home
Assistant* mode.

### "Known bands only" mode (default): green for your bands, red for others, decided instantly

A band's first scan gets the denied sequence. The reader stores its allowed
list itself, with room for about 100 bands, so it answers instantly and keeps
working when Home Assistant is offline.

**Recommended:** manage people and bands with the
[MagicBand integration](integration.md). It logs scans, alerts you about new
bands, lets you give bands to people, including people who aren't HA users and
people with several bands, and keeps every reader's list in sync.

**Without the integration:** tap the band, then press **Allow last band** on
the reader's device page. **Forget last band** (tap it first) and **Forget
all bands** remove entries.

### "Ask Home Assistant" mode: let an automation decide

Use this only if HA needs to decide, for example based on time of day or who's
home. The ring spins until HA answers, and with no answer within 3 seconds it
shows red. Add an automation that answers:

```yaml
alias: "MagicBand reader: allow known bands"
triggers:
  - trigger: event
    event_type: tag_scanned
    event_data:
      device_id: YOUR_READER_DEVICE_ID   # optional: only this reader
actions:
  - if:
      - condition: template
        value_template: >
          {{ trigger.event.data.tag_id in ['04-53-65-2A-C0-5F-80', '04-11-22-33-44-55-66'] }}
    then:
      - action: esphome.magicband_reader_XXXXXX_accept
    else:
      - action: esphome.magicband_reader_XXXXXX_deny
```

## Phones and watches

Disney's phone and watch passes (MagicMobile in Apple and Google Wallet) use
the wallets' encrypted protocols, which need Apple's, Google's and Disney's
keys, and phones don't present a fixed NFC ID. So the reader can't recognise
a phone or watch. As an alternative, stick an NFC tag on the reader and scan
it with the Home Assistant Companion app. An automation on that tag can run
the reader's welcome sequence (press **Test welcome**, or call its actions).
That goes through Home Assistant, so it's slightly slower than a band.

## Sounds

The reader plays three sound files, embedded in the firmware at build time so
they play instantly with no network involved:

| File | When |
|---|---|
| `sounds/startup.wav` | Reader starts up |
| `sounds/tap_in.wav` | Band accepted |
| `sounds/error.wav` | Band denied |

The sounds were recorded by the project owner and are included in this repo,
in `esphome/sounds/`. The reader downloads them from GitHub when it's built,
so there's nothing to copy onto Home Assistant.

**Using your own sounds instead:**

1. Convert each one to **mono, 16-bit, 48 kHz WAV**. This keeps them small and
   matches the speaker. With ffmpeg:
   `ffmpeg -i in.wav -ac 1 -ar 48000 -sample_fmt s16 out.wav`
2. Either host them somewhere and put the URLs in `sound_startup`,
   `sound_tap_in` and `sound_error` at the top of the config, or put them in
   `/config/esphome/sounds/` on Home Assistant (File editor, Samba or Studio
   Code Server add-on) and set those values to `sounds/startup.wav` and so on.
3. Install the reader from the Device Builder. The files are embedded each
   time you build, and each must be under 5 MB.

## Notes

- The MagicBand+ feedback uses Bluetooth, so it reaches **any** MagicBand+
  nearby, not only the one on the reader. The reader transmits at 0 dBm (set
  `tx_power` under `magicband:`) to keep that local.
- Taps during a sequence are ignored; tap again once the reader is idle.
