# Ways to build the MagicBand Reader

The reader can be built several ways. They all use the same parts (an
ESP32-S3 N16R8, a PN532 NFC reader, a MAX98357A amplifier kit, a 74AHCT125
level shifter, a WS2812B LED ring, a USB-C PD trigger set to 5 V), the same
GPIOs and the same firmware features. Only the way the parts are joined
changes.

**Parts for every build: the [shopping list](shopping-list.md).**

**Start with the breadboard or the compact build.** The breadboard is the
reference layout: roomy, easy to probe, and everything can be rewired. The
compact build is the one that has actually been built and tested, and needs
no soldering beyond the PN532's header. Once one works, use it to check
each later build.

| # | Build | Step by step | Reference | Size | Soldering | Status |
|---|---|---|---|---|---|---|
| 1 | **Breadboard** | **[Build it](reader-breadboard/build.md)** | [Spec](reader-breadboard/README.md), [diagram](../docs/reader-breadboard.svg) | Large | The ring's wires only | Reviewed, not built |
| 2 | **Lonely Binary terminal base** | **[Build it](reader-wired/build.md)** | [Spec](reader-wired/README.md), [diagram](../docs/reader-terminal-base.svg) | Medium | Interface board, amplifier power, two power wires | Reviewed, not built |
| 3 | **Point-to-point wiring** | **[Build it](reader-wired/build.md)** | [Spec](reader-wired/README.md), [diagram](../docs/reader-point-to-point.svg) | Small | Interface board, every joint | Reviewed, not built |
| 3a | **Compact (solderless)**: point-to-point on a 400-point half breadboard | **[Build it](reader-compact/build.md)** | [Spec](reader-wired/README.md#compact-solderless-version), [diagram](../docs/reader-compact.svg) | Small | The PN532 header only (a ring without leads: its wires too) | **Built and tested** on the USB-C PD supply (power, NFC, sound at 100 %, load test before the ring); 35-LED ring wired and lighting; tap sequence and load test with the ring still to confirm |

All of them use a dev board (ESP32-S3-DevKitC-1 layout, such as the Lonely
Binary N16R8) and install from the web installer's *Install the reader*
button.

A custom PCB is planned for later, once these builds are proven. An early
design is out of date and has been taken out of this repository for now.

## Checking a build works

Run through this for every build, in order. Each step only needs the ones
before it.

**Where to look.** Most checks use the reader's entities on its device page
in Home Assistant (**Last band ID**, **Known bands**, **Allowed list**, the
**Firmware** version). For start-up messages, plug USB into the **UART** port
and open the web installer's **Logs & console** (on a built reader, unplug the
ESP32's 5 V wire first). The log shows warnings and errors, never band IDs.

1. **Board and firmware.** Install from the
   [web installer](https://legal-copy7045.github.io/Magic-bHAnds/), set up
   Wi-Fi, and add the device in Home Assistant. The device page shows the
   firmware version.
2. **NFC reader.** No `Error sending version command` in the start-up log
   (that means the PN532 isn't answering). Tap a band: **Last band ID** shows
   its ID, and Home Assistant gets a tag scan (Settings → Tags).
3. **LEDs.** Turn on the **Ring** light in Home Assistant. Every LED lights
   in the right colour (missing LEDs mean a wrong **LED count**, swapped
   colours a wrong **LED colour order**, odd whites on an RGBW ring a wrong
   **Ring type**; flicker or garbage usually means the level shifter or
   ground).
4. **Sound.** Restart the device: the start-up sound plays. Then tap a
   known and an unknown band for the tap-in and error sounds.
5. **Bluetooth.** Tap a known MagicBand+: it lights in the welcome colour
   and buzzes.
6. **Under load.** Set the ring to full white for a minute while tapping
   bands. The board shouldn't restart (**Last restart** doesn't change, the
   start-up sound doesn't play again), and nothing should get hot (**CPU
   temperature** is a rough guide).
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
- [`reader-compact/`](reader-compact/build.md): build 3a, step by step (its
  spec is in `reader-wired/README.md`).
- [`shopping-list.md`](shopping-list.md): the generic parts the guides use,
  their Adafruit equivalents, wire and tools.
- [`make_power_diagram.py`](make_power_diagram.py): draws the power
  diagram shared by every build.

The bridge needs no extra hardware: any ESP32-S3 board works (see
[docs/bridge.md](../docs/bridge.md)), as does a SCREEK BP2-POE.
