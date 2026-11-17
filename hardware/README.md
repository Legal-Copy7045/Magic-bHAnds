# Ways to build the MagicBand Reader

The reader can be built several ways. They all use the same parts (an
ESP32-S3 N16R8, a PN532 NFC reader, a MAX98357A amplifier, a 74AHCT125 level
shifter, a WS2812B LED ring and a speaker), the same GPIOs and the same
firmware features. Only the way the parts are joined changes.

**Start with the breadboard.** It's the reference build: quick to put
together, easy to probe, and everything can be rewired. Once it works, use
it to check each later build.

| # | Build | Size | Soldering | Firmware (web installer button) | Status |
|---|---|---|---|---|---|
| 1 | **[Breadboard](reader-breadboard/README.md)** ([diagram](../docs/reader-breadboard.svg)) | Large | Ring and capacitor pads only | *Install the reader* | Reviewed, first build |
| 2 | **[Lonely Binary terminal base](reader-wired/README.md)** | Medium | Interface board, two power wires | *Install the reader* | Reviewed, not built |
| 3 | **[Point-to-point wiring](reader-wired/README.md)** | Small | Interface board, every joint | *Install the reader* | Reviewed, not built |
| 4 | **[Custom PCB](reader-pcb/README.md)** (26 × 58 mm, ordered assembled) | Smallest | None (factory-assembled) | *Reader on the custom PCB* | **Parked**: not yet updated for the ring-only design and the review |

Builds 1–3 use a dev board (ESP32-S3-DevKitC-1 layout, such as the Lonely
Binary N16R8) and the same firmware. Build 4 has the ESP32-S3 module on the
PCB, so it has its own firmware build,
[`esphome/magicband-reader-pcb.yaml`](../esphome/magicband-reader-pcb.yaml):
the same reader with logs and Wi-Fi setup on the native USB port. It gets
updates on its own channel, so neither firmware can be installed over the
other by an update.

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

- [`reader-breadboard/`](reader-breadboard/README.md): the reviewed
  breadboard build (build 1) and the script that draws its diagram.
- [`reader-wired/`](reader-wired/README.md): the terminal base and
  point-to-point builds (2 and 3), with the shared interface board.
- [`reader-pcb/`](reader-pcb/README.md): KiCad project, Gerbers and JLCPCB
  files for build 4, with the scripts that generate them.

The bridge needs no extra hardware: any ESP32-S3 board works (see
[docs/bridge.md](../docs/bridge.md)), as does a SCREEK BP2-POE.
