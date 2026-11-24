<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-dark.png">
    <img src="docs/images/logo.png" alt="MagicbHAnds" width="520">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/Legal-Copy7045/Magic-bHAnds/releases"><img alt="Release" src="https://img.shields.io/github/v/release/Legal-Copy7045/Magic-bHAnds?label=release"></a>
  <a href="https://github.com/Legal-Copy7045/Magic-bHAnds/actions/workflows/firmware.yml"><img alt="Build" src="https://github.com/Legal-Copy7045/Magic-bHAnds/actions/workflows/firmware.yml/badge.svg"></a>
  <a href="https://hacs.xyz"><img alt="HACS" src="https://img.shields.io/badge/HACS-custom-blue"></a>
</p>

MagicbHAnds brings Disney MagicBands into **Home Assistant**. It has two
parts, which you can use separately or together, plus a Home Assistant
integration that ties them up.

| | What it does | Bands | Hardware |
|---|---|---|---|
| **Part 1: [MagicBand Bridge](docs/bridge.md)** | Lights up and buzzes bands from automations: any colour, animations, vibration patterns | MagicBand+ (Bluetooth) | An ESP32-S3 board, nothing else |
| **Part 2: [MagicBand Reader](docs/reader.md)** | A park-style tap point. Two white circles chase round the ring, Home Assistant knows whose band it is, a green glow (welcome) or two red pulses (denied) with sound, and a MagicBand+ lights up too | Original MagicBands and MagicBand+ (NFC) | ESP32-S3, PN532 NFC reader, LED ring (or strip), amplifier and speaker, powered by a USB-C charger. [Shopping list](hardware/shopping-list.md) |
| **[MagicbHAnds integration](docs/integration.md)** (HACS) | People and their bands (with or without a Home Assistant user), a log of every tap, the *Send MagicBand effect* action and the automation blueprints | Both | None |

## Quick start

**Building a reader?** Get the parts from the
[shopping list](hardware/shopping-list.md) and follow a step-by-step
build: the [breadboard](hardware/reader-breadboard/build.md) first, then the
[terminal base or point-to-point](hardware/reader-wired/build.md) or the
[compact (solderless)](hardware/reader-compact/build.md) version.
Each starts by flashing the bare ESP32 and checks every stage as you go. A
bridge needs no extra hardware.

1. **Flash the firmware** from the web installer:
   **https://legal-copy7045.github.io/Magic-bHAnds/**. Choose *Install the
   bridge* or *Install the reader*, then enter your Wi-Fi details. No YAML is
   needed. To change Wi-Fi later, the device starts a setup hotspot when it
   can't reach its Wi-Fi for 2 minutes (or use the web installer over USB).
2. **Add the device** in Home Assistant when it's discovered (ESPHome).
3. **Install the MagicbHAnds integration** from HACS:
   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Legal-Copy7045&repository=Magic-bHAnds&category=integration)
   Restart Home Assistant, then add **MagicbHAnds** under Settings → Devices &
   services.
4. **Readers:** leave **Allow the device to perform Home Assistant actions**
   (the reader's ESPHome entry → Configure) **off**. Tag scans don't need it,
   and a reader outside your door shouldn't be able to call any action
   (see [docs/security.md](docs/security.md)).

Then:
- **Bridge:** call `magicband.send` from any automation, or use the
  *MagicBand+ notification* blueprint the integration installs.
- **Reader:** tap a band, then add it under **MagicbHAnds → Configure → Add or
  assign a band** and give it to a person.

## Features

**MagicBand Bridge** ([guide](docs/bridge.md))
- Palette colours, any RGB colour, two- and five-colour layouts, crossfades
  and 31 predefined park scenes, with one-press scene buttons
- Fast mode: mixes in the park's "fast mode" ping so bands respond sooner
- 11 vibration patterns, on-time, fade-out and stay-on control
- A MagicBand light entity with a colour picker and animation effects
- Several bridges for whole-house coverage, all addressed at once by default
- An optional Bluetooth proxy on the same board
- Also runs on other ESPHome boards, such as the SCREEK BP2-POE

**MagicBand Reader** ([guide](docs/reader.md), [ways to build it](hardware/README.md), [shopping list](hardware/shopping-list.md))
- Reads original MagicBands and MagicBand+ by their NFC ID
- An LED ring (or a flexible strip for tighter housings), with start-up,
  tap-in and error sounds
- Several ways to build it, each with a wiring diagram, a hole-by-hole wiring
  table and step-by-step instructions with checks:
  [breadboard](hardware/reader-breadboard/build.md),
  [terminal base and point-to-point](hardware/reader-wired/build.md),
  [compact (solderless)](hardware/reader-compact/build.md)
- Any LED count (1–100), RGB or SK6812 RGBW rings, and the whole tap
  sequence (colours, circles, welcome and denied timings, a dimmer idle glow
  at night, by set hours or sunset to sunrise) set from the reader's device
  page
- 28 light shows, played at start-up, from the device page, from
  `magicband.play_show` or on a schedule (blueprint), including holiday,
  birthday and passport-stamp shows
- Health sensors (Wi-Fi signal, memory, loop time, CPU temperature, restart
  reason) for spotting trouble
- Runs from one USB-C charger (20 W or more)
- Decides green or red on the device, instantly, even with Home Assistant
  offline
- Lights up and buzzes a MagicBand+ on a successful tap

**MagicbHAnds integration** ([guide](docs/integration.md))
- People with any number of bands, optionally linked to a Home Assistant
  person
- New bands are denied and announced; add them in a couple of clicks
- Allowed lists synced to every reader, with each reader's status shown and
  problems (a reader offline, a list it rejected) in Home Assistant's Repairs
- **Schedules and expiry** per band: a daily time window, days of the week,
  an end date
- **Enrolment**: tap a person's bands one after another to add them all
- **Personal welcome**: each person's bands welcomed in their own colour, on
  the ring and on their MagicBand+
- **Tap history** on the management page and in the logbook, and a battery
  sparkline for each MagicBand+
- **Charge reminders** for MagicBand+ (Repairs, an event, and a phone
  notification blueprint)
- A management page in the sidebar for bands, people, readers and bridges
  (administrators only), with health tiles for each reader and bridge
- `magicband_tap` events and per-person "last tap" sensors
- The `magicband.send` action and the bundled blueprints
- Logs which MagicBand+ devices Home Assistant's Bluetooth hears, and when,
  so you can see bands responding to a bridge
- Guest passes (start and end, number of uses, daily hours), lockdown (by
  hand, when nobody's home, at night or while the alarm is armed),
  birthday and holiday shows after a welcome, and a tap passport with
  streaks and stamps

## Releases and versions

The bridge firmware, the reader firmware and the integration share **one
version number** (see [`VERSION`](VERSION)). Each release is a
[GitHub Release](https://github.com/Legal-Copy7045/Magic-bHAnds/releases)
with notes from the [changelog](CHANGELOG.md), the firmware files and the
integration attached.

- **Firmware updates** appear in Home Assistant as an update on each bridge
  and reader, and install over Wi-Fi. Each device downloads its firmware itself
  from this project's site and only installs releases signed with the project's
  key. Turn on **Automatic updates** on a device to have it install new releases
  (only ever newer than the one it runs) by itself between 3 and 4 am in the device's **Time zone** (default
  Eastern). Devices keep time from an internet time server, so this works
  without Home Assistant.
- **Integration updates** appear in HACS.

To make a release: bump `VERSION` and the versions it lists (CI checks they
match), add a `CHANGELOG.md` section, and merge to `main`. Then go to
**Actions → Build, test & release → Run workflow**, tick **release**, and run
it on `main`. It tags `v<VERSION>` and publishes the GitHub Release. This is
the only way to release: pushing a `v*` tag yourself doesn't release (that run
only builds and tests, and the `release-signing` environment gives its key to
`main` only). Every push to `main` signs the firmware and publishes it to the update site,
so the GitHub account that can push to `main` is what protects releases: give
it two-factor authentication, and keep the `release-signing` environment
limited to `main` (see [docs/security.md](docs/security.md#accepted-risks)).

## Repo layout

| Path | What |
|---|---|
| `components/magicband/` | ESPHome component that broadcasts MagicBand+ commands |
| `esphome/magicband-bridge.yaml` | Bridge firmware (web installer, "Take control") |
| `esphome/magicband-reader.yaml` | Reader firmware (web installer, "Take control") |
| `esphome/magicband-addon.yaml` | The MagicBand parts as a package for any ESPHome board |
| `esphome/screek-bp2-poe*.yaml` | SCREEK BP2-POE as a PoE proxy and bridge |
| `esphome/sounds/` | The reader's sounds (the project owner's recordings) |
| `custom_components/magicband/` | The MagicbHAnds integration (HACS) |
| `homeassistant/` | Blueprints (notification, charge me), example scripts and automations, and the [management dashboard](homeassistant/dashboards/magicband.yaml) |
| `hardware/` | [Ways to build the reader](hardware/README.md), the [shopping list](hardware/shopping-list.md) (with generic alternatives), and the power diagram's generator |
| `hardware/reader-breadboard/` | Breadboard build: step-by-step build, spec and wiring table, and the diagram's generator |
| `hardware/reader-wired/` | Terminal base and point-to-point builds, with the interface board: step-by-step build and spec |
| `hardware/reader-compact/` | Compact (solderless) build: step-by-step build |
| `web/` | The web installer page |
| `docs/` | Guides: [bridge](docs/bridge.md), [reader](docs/reader.md), [integration](docs/integration.md), [commands](docs/commands.md), [protocol](docs/protocol.md), [SCREEK BP2-POE](docs/screek-bp2-poe.md), [security](docs/security.md); reader wiring diagrams; [ideas for later](docs/ideas.md) |
| `tests/` | Integration tests |

## Caveats

- Bands sleep to save battery. A sleeping band may need a shake or a longer
  burst before it reacts.
- The protocol is unofficial and reverse-engineered. See
  [docs/protocol.md](docs/protocol.md).
- This is for home tinkering. Don't run it anywhere near the parks.
- The reader builds have been reviewed against the parts' datasheets. The
  [compact build](hardware/reader-compact/build.md)
  has been built and tested on the USB-C PD supply (power, NFC, sound at
  100 %, a load test before the ring was fitted), and its 35-LED ring is
  wired and lights correctly (idle glow, all LEDs, colours, 5.1 V); the tap
  sequence and the load test with the ring are still to be confirmed. The breadboard, terminal-base and point-to-point
  builds have been reviewed but not built.
  Follow each build's staged tests, which check voltages before anything is
  connected to the ESP32.

## Security

A band's NFC ID and Bluetooth beacon identify it but don't prove it's
genuine, so a tap is about as secure as a basic RFID fob. Read
[docs/security.md](docs/security.md) before using MagicbHAnds to open a door.

## Credits

This project builds on other people's work.

**Protocol research**
- **[emcot.world: Disney MagicBand+ Bluetooth Codes](https://emcot.world/Disney_MagicBand%2B_Bluetooth_Codes)**:
  the community reverse-engineering wiki this project is based on. It covers
  the packet layouts, timing byte, vibration patterns, LED masks, colour
  palette, RGB command and the captured show animations. See
  [docs/protocol.md](docs/protocol.md).
- **[Haw8411/magic-band-plus-lights](https://github.com/Haw8411/magic-band-plus-lights)**
  (MIT): a Flipper Zero MagicBand+ app. Its preset list filled out the
  bridge's scenes, and its "Fast mode" (pre-warm and interleaved `CC 03 00 01 00`
  pings) is the basis for the bridge's Fast mode. The payloads are protocol
  data; no code was copied.
- **[xxfunprojectsxx/esp32_magicband](https://github.com/xxfunprojectsxx/esp32_magicband)**:
  an ESP32-S3 MagicBand+ broadcaster that we used to cross-check the command
  byte layouts and colour codes. No code was copied (that repo has no
  licence); this project's firmware was written independently.
- **[Adafruit: BLE Beacon NeoPixels](https://learn.adafruit.com/ble-beacon-neopixels)**:
  Adafruit's MagicBand+ beacon project, referenced by the emcot.world wiki.
  It was also one of the first sources found for this project.

**MagicBand reader projects** (inspiration for the reader; no code used)
- [Adafruit: Magic Band Reader](https://learn.adafruit.com/magic-band-reader):
  a Feather RP2040 reader. Its side-light NeoPixel strip is one of the
  flexible LED options for tight housings.
- [foolishmortalbuilders/magicbandreader](https://github.com/foolishmortalbuilders/magicbandreader):
  a Raspberry Pi reader with a pixel ring, Mickey and sounds.
- [dcivitano/Magic-Band-Reader](https://github.com/dcivitano/Magic-Band-Reader):
  an Arduino reader with an RC522, NeoPixels and a DFPlayer.
- [ncory/MagicReader](https://github.com/ncory/MagicReader): a Raspberry Pi
  reader with per-band sequences that triggers MagicBand+ effects through an
  ESP32 broadcaster.

**Sounds**
- The reader's start-up, tap-in and error sounds in `esphome/sounds/` were
  recorded by the project owner.

**Software and tools**
- [ESPHome](https://esphome.io): the firmware framework. The `magicband`
  component's raw-advertising approach follows ESPHome's `esp32_ble_beacon`
  component.
- [ESP Web Tools](https://esphome.github.io/esp-web-tools/) and
  [Improv Wi-Fi](https://www.improv-wifi.com): browser flashing and Wi-Fi
  setup on the install page.
- [Home Assistant](https://www.home-assistant.io): automations, the ESPHome
  integration and blueprints.
- [Espressif ESP-IDF](https://github.com/espressif/esp-idf): the ESP32
  Bluetooth stack.

**Font**
- **Waltograph** v4.2 by Justin Callaghan ([mickeyavenue.com](http://mickeyavenue.com/)),
  with Bill Shelly, Joshua Jones, Robert Johnson, John Hornbuckle, John Hansen,
  John Yaglenski and Erwin Denissen. It's used for the logo wordmark and the
  management page's headings. It's released under the
  [Creative Commons NonCommercial-ShareAlike licence](http://creativecommons.org/licenses/nc-sa/1.0/)
  for personal, noncommercial use. The font is in
  `custom_components/magicband/frontend/fonts/` with its own readme
  (`waltograph.txt`) and licence (`license.txt`), unchanged. The logo images made
  with it (`docs/images/logo*.png`, `custom_components/magicband/brand/*logo.png`)
  are shared under the same NonCommercial-ShareAlike licence.

**Hardware**
- Developed for the Lonely Binary ESP32-S3 N16R8 IPEX board, which uses the
  ESP32-S3-DevKitC-1 layout.
- The reader builds were checked against Espressif's DevKitC-1 guide,
  schematic and drawings; Elechouse's PN532 V3 manual and schematic; TI's
  74AHCT125, Worldsemi's WS2812B and Analog Devices' MAX98357A datasheets;
  and Adafruit's product pages and guides (NeoPixel Überguide, MAX98357A,
  HUSB238, PN532).

MagicBand and MagicBand+ are trademarks of Disney. The Waltograph font is a
fan-made lettering inspired by Disney's; it is not Disney's own typeface. This is an unofficial hobby
project with no affiliation to, or endorsement from, Disney, Adafruit or any of
the projects above.

## Development

```bash
pip install esphome
cd esphome
# Build against the local component instead of the copy on GitHub main:
esphome -s component_source ../components compile magicband-bridge.yaml
```

Hardware diagrams are generated, not drawn by hand:

```bash
python3 hardware/reader-breadboard/make_diagram.py > docs/reader-breadboard.svg
python3 hardware/reader-wired/make_diagrams.py terminal-base  > docs/reader-terminal-base.svg
python3 hardware/reader-wired/make_diagrams.py point-to-point > docs/reader-point-to-point.svg
python3 hardware/reader-wired/make_diagrams.py interface-board > docs/reader-interface-board.svg
python3 hardware/reader-wired/make_diagrams.py compact        > docs/reader-compact.svg
python3 hardware/make_power_diagram.py > docs/reader-power.svg
```

Releases: see [Releases and versions](#releases-and-versions). Once a
version is merged to `main`, devices offer the update in Home Assistant.
