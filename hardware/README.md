# Ways to build the MagicBand Reader

The reader can be built several ways. They all use the same parts (an
ESP32-S3 N16R8, a PN532 NFC reader, a MAX98357A amplifier kit, a 74AHCT125
level shifter, a WS2812B LED ring, a USB-C PD trigger set to 5 V), the same
GPIOs and the same firmware features. Only the way the parts are joined
changes.

**Parts for every build: the [shopping list](shopping-list.md).**

**Start with the breadboard.** It's the reference build: quick to put
together, easy to probe, and everything can be rewired. Once it works, use
it to check each later build.

| # | Build | Step by step | Reference | Size | Soldering | Status |
|---|---|---|---|---|---|---|
| 1 | **Breadboard** | **[Build it](reader-breadboard/build.md)** | [Spec](reader-breadboard/README.md), [diagram](../docs/reader-breadboard.svg) | Large | The ring's wires only | Reviewed, first build |
| 2 | **Lonely Binary terminal base** | **[Build it](reader-wired/build.md)** | [Spec](reader-wired/README.md), [diagram](../docs/reader-terminal-base.svg) | Medium | Interface board, amplifier power, two power wires | Reviewed, not built |
| 3 | **Point-to-point wiring** | **[Build it](reader-wired/build.md)** | [Spec](reader-wired/README.md), [diagram](../docs/reader-point-to-point.svg) | Small | Interface board, every joint | Reviewed, not built |
| 3a | **Compact (solderless)**: point-to-point on a 400-point half breadboard | **[Build it](reader-wired/build.md#compact-solderless-version)** | [Spec](reader-wired/README.md#compact-solderless-version), [diagram](../docs/reader-compact.svg) | Small | The PN532 header and the ring's wires only | **Built and tested up to sound** (power, NFC, amplifier); ring and PD supply next |

All of them use a dev board (ESP32-S3-DevKitC-1 layout, such as the Lonely
Binary N16R8) and install from the web installer's *Install the reader*
button.

A custom PCB is planned for later, once these builds are proven. An early
design is out of date and has been taken out of this repository for now.

## Checking a build works

Run through this for every build, in order. Each step only needs the ones
before it.

1. **Board and firmware.** Install from the
   [web installer](https://legal-copy7045.github.io/Magic-bHAnds/), set up
   Wi-Fi, and add the device in Home Assistant. *Logs* show the version.
2. **NFC reader.** The log shows the PN532 found at start-up (no
   `Error sending setup` or `PN532 not found` lines). Tap a band: the log
   shows its ID and Home Assistant gets a tag scan.
3. **LEDs.** Turn on the **Ring** light in Home Assistant. Every LED lights
   in the right colour (wrong colours mean a wrong LED count or order;
   flicker or garbage usually means the level shifter or ground).
4. **Sound.** Restart the device: the start-up sound plays. Then tap a
   known and an unknown band for the tap-in and error sounds.
5. **Bluetooth.** Tap a known MagicBand+: it lights green and buzzes.
6. **Under load.** Set the ring to full white for a minute while tapping
   bands. The board shouldn't restart (check *Uptime*), and nothing should
   get hot.
7. **In its case.** Repeat steps 2 and 5 with everything closed up. NFC
   needs no metal between the antenna and the band.

Make a note of anything that differs between builds (read range,
sound volume, LED behaviour) and raise it as a GitHub issue.

## Other hardware in this folder

- [`reader-breadboard/`](reader-breadboard/README.md): build 1: the
  step-by-step build (`build.md`), the reviewed spec (`README.md`) and the
  script that draws its diagram.
- [`reader-wired/`](reader-wired/README.md): builds 2 and 3, with the
  shared interface board: step-by-step build, spec and diagram script.
- [`shopping-list.md`](shopping-list.md): the generic parts the guides use,
  their Adafruit equivalents, wire and tools.
- [`make_power_diagram.py`](make_power_diagram.py): draws the power
  diagram shared by every build.

The bridge needs no extra hardware: any ESP32-S3 board works (see
[docs/bridge.md](../docs/bridge.md)), as does a SCREEK BP2-POE.
