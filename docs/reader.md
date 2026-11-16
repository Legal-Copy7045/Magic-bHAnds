# MagicBand Reader

A park-style touch point for Home Assistant. Tap an **original MagicBand** or a
**MagicBand+** on it: the ring spins, Home Assistant gets the band's ID, the
ring and Mickey turn green with a chime, and a MagicBand+ also lights up green
and buzzes.

Config: [`esphome/magicband-reader.yaml`](../esphome/magicband-reader.yaml).

Inspired by
[foolishmortalbuilders/magicbandreader](https://github.com/foolishmortalbuilders/magicbandreader),
[dcivitano/Magic-Band-Reader](https://github.com/dcivitano/Magic-Band-Reader) and
[ncory/MagicReader](https://github.com/ncory/MagicReader). Like them, it
identifies bands by their NFC ID. Unlike them, it runs on one ESP32 with
ESPHome and connects to Home Assistant natively (Tags, entities, actions). No
code from those projects is used.

## How bands are read

Both band types contain a standard 13.56 MHz NFC chip (ISO 14443-A) with a
fixed ID, which is the same ID a phone app such as *NFC Tools* shows. The
reader only reads that ID, so no encrypted Disney data is involved. Original
MagicBands give a 7-byte ID like `04-53-65-2A-C0-5F-80`.

## Parts

| Part | Example | Notes |
|---|---|---|
| ESP32-S3 dev board | Lonely Binary / DevKitC-1 **N16R8** | Same board as the bridge |
| NFC reader | **PN532** module (Elechouse V3 or clone) | Set its DIP switches to **I2C** |
| LED ring | WS2812B ring, 24 LEDs | 12 or 16 also work: change `ring_leds` |
| Mickey head | WS2812B strip or rings, ~12 LEDs | Set `mickey_leds` |
| Amplifier | **MAX98357A** I2S board | Plus a 3 W 4–8 Ω speaker |
| Level shifter | 74AHCT125 (or a single SN74AHCT1G125) | 3.3 V → 5 V for the LED data line |
| Power | 5 V **3 A** supply | 36 LEDs at full white draw ~2 A. A USB-C charger works: see below |
| Odds and ends | 330 Ω resistor, 1000 µF capacitor | Resistor in series with LED data; capacitor across the LED 5 V/GND |

## Wiring

![Breadboard wiring](reader-breadboard.svg)

All of the reader's connections are on the DevKitC's left pin row, in
breadboard B (rows in the tables refer to it). The board is too wide to leave
free holes on a single breadboard, so its right-hand side needs support: a
second breadboard (A, as drawn), a wide "ESP32 breadboard", or a block of the
same height. Nothing connects to the right-hand side.

| ESP32-S3 pin | Goes to |
|---|---|
| **5V** | 5 V supply (+). Also the PN532 VCC, the MAX98357A VIN, the level shifter VCC and the LED 5 V |
| **GND** | Ground for everything (common ground is essential) |
| **GPIO8** | PN532 **SDA** |
| **GPIO9** | PN532 **SCL** |
| **GPIO10** | Level shifter input → 330 Ω → first LED of the **ring** **DIN** |
| **GPIO5** | MAX98357A **LRC** |
| **GPIO6** | MAX98357A **BCLK** |
| **GPIO7** | MAX98357A **DIN** |

- **LED chain order:** the ring comes first, then the ring's DOUT goes to the
  Mickey head's DIN. The firmware splits the chain into a **Ring** light and a
  **Mickey** light.
- **Power the LEDs from the 5 V supply directly**, not through the ESP32's
  USB.
- **Level shifter (74AHCT125):** tie its OE pin for the channel you use (1OE)
  to GND, and power it from 5 V.
- **Placement:** put the PN532 antenna in the centre of the ring, under the
  lid, with **no metal** between it and the band. Read range is a few
  centimetres through plastic.

### Using the Lonely Binary terminal base instead of a breadboard

The Lonely Binary **ESP32-S3 pluggable terminal block** base takes the board
and brings its pins out to push-in terminals. Every pin the reader needs is
on a terminal, apart from 5 V:

| Terminal | Goes to |
|---|---|
| Left **3V3** | PN532 **VCC** |
| Left **GND** (×2), right **GND** (×2) | Ground for the PN532, MAX98357A and level shifter |
| Left **7** | MAX98357A **DIN** |
| Left **8** | PN532 **SDA** |
| Left **9** | PN532 **SCL** |
| Left **10** | Level shifter input (LED data) |
| Right **5** | MAX98357A **LRC** |
| Right **6** | MAX98357A **BCLK** |
| **5V / GND pads** (bottom, solder a wire to each) | 5 V supply in |

- **5 V has no terminal.** Solder a red and a black wire to the 5V and GND
  pads by the USB ports, and run them to the 5 V supply.
- **Distribute 5 V and ground** with lever connectors (Wago 221 or similar)
  or a small power block. The supply feeds the board's 5V pad, the LED ring,
  the MAX98357A Vin and the level shifter's VCC, and every ground meets in
  one place.
- **Feed the LEDs straight from the supply,** not through the base.
- **The level shifter, 330 Ω resistor and 1000 µF capacitor** still need a
  home. A small 74AHCT125 level-shifter module, or a scrap of perfboard,
  sits in the cable run to the LED ring. Put the 1000 µF capacitor across the
  ring's 5V and GND where its cable starts.
- As always, **don't connect USB while the 5 V supply is on.**

### Powering it from a USB-C charger

A USB-C charger that can give **5 V at 3 A**, such as most Dell, Apple or
Anker USB-C chargers, makes a good supply. Feed it in through a **USB-C power
breakout board** (sometimes sold as a "USB-C 5V breakout" or "PD trigger"
set to 5 V), which gives you 5V and GND terminals for the + and − rails.

Don't run everything through the ESP32's own USB port. That port and its
protection parts on the DevKitC are only meant for the board itself, and the
LEDs can draw 2 A. Keep the ESP32's USB port for the first install, with the
charger unplugged.

## Install

**Web installer: https://legal-copy7045.github.io/Magic-bHAnds/** (choose
*Install the reader*).

1. Plug the ESP32-S3 into your computer through the USB-C port labelled
   **UART**, with the 5 V supply **disconnected**.
2. Open the web installer in Chrome or Edge, click **Install the reader**,
   then enter your Wi-Fi details when asked.
3. Add it in Home Assistant when it's discovered (ESPHome). Then open
   **Settings → Devices & services → ESPHome → the reader → Configure**, and
   turn on **Allow the device to perform Home Assistant actions**. That's
   needed for tag scans to reach Home Assistant.
4. Install the [MagicBand integration](integration.md) to manage people and
   bands.

Firmware updates then appear in Home Assistant as an update on the reader.
The connection is encrypted: Home Assistant gives each reader its own key when
it first connects.

**Customising** (LED counts, sounds, pins): in the ESPHome Device Builder the
reader shows up with **Take control**, which imports
`esphome/magicband-reader.yaml` as a package. Change `ring_leds` and
`mickey_leds` in its substitutions if your LED counts differ from 24 and 12.

## Using it with Home Assistant

**Name your bands.** Tap each band once, then go to **Settings → Tags**. Each
band appears with its ID: give it a name ("Alex's MagicBand+").

**React to a band.** Create an automation with the trigger **Tag → Alex's
MagicBand+**, for example to turn on the lounge lights.

**Entities on the reader:**

| Entity | What it does |
|---|---|
| **Ring**, **Mickey** | The LEDs as normal HA lights, so you can use them as a night light too |
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
