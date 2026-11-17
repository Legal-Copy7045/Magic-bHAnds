# Changelog

All notable changes to Magic bHAnds. The bridge firmware, reader firmware and
Home Assistant integration share one version number.

## [0.8.2] - 2026-11-17

### Fixed
- **SCREEK BP2-POE: "requested passive mode but is operating in active
  mode … needs to be power cycled".** Home Assistant now chooses each
  proxy's active or passive scanning (ESPHome integration → the device →
  Configure → Bluetooth scanning mode). The firmware's own Scan Active Mode
  switch overrode that choice, so it's been removed. Delete the old entity
  once it shows as unavailable. Scan Interval and Scan Window stay.

### Docs
- Bridge and BP2-POE guides: where to set active or passive scanning.
- **Shopping list** (`hardware/shopping-list.md`): exact Adafruit parts for
  all three reader builds, checked against Adafruit's product pages, and the
  three parts Adafruit doesn't sell. The builds now use them:
  - NeoPixel Ring 24 (the PN532 fits inside it).
  - 3 W 4 Ω enclosed speaker.
  - 470 Ω data resistor.
  - Snap-action connectors as the power hubs.
  - 22 AWG stranded power wiring.
  - HUSB238 USB-C PD breakout with the Raspberry Pi 27 W supply.
- **Diagrams for the terminal base and point-to-point builds**, with the
  interface board drawn hole for hole on an Adafruit Perma-Proto.
- Reader install steps: flash the bare ESP32 first; disconnect the ESP32's
  5 V before plugging in USB later.
- Flexible LED strip options linked from every reader build guide, and a
  new `ring_color_order` setting for strips that aren't GRB (Adafruit's
  silicone neon-like strip is RGB). The published firmware is unchanged
  (GRB).
- Shopping list: wire sets, solder, flux, heat shrink, Kapton tape, tools,
  and a wiring guide (wire type, colour, length limit and how to finish
  each connection).
- **Pictures instead of text diagrams:** a power distribution diagram for
  all builds (both USB-C PD board options, hubs, every branch with wire,
  length and current) and an interface board close-up with every wire in
  and out labelled. The wiring diagrams now name either power board.
- Shopping list: generic (non-Adafruit) alternatives and what to check for
  each, including a CH224K DIP-switch PD board set to 5 V.

## [0.8.1] - 2026-11-17

### Changed
- **The reader drives a single LED ring** (16 or 24 LEDs, set `ring_leds`).
  The Mickey head is gone, which keeps a reader within a 5 V 3 A USB-C
  supply. The ring glows white while waiting for a band.

### Hardware
- **Reviewed breadboard build** (`hardware/reader-breadboard/`), checked
  against the Espressif, Elechouse, TI, Worldsemi, Analog Devices and
  Adafruit documentation:
  - Corrected diagram: the ESP32 board's orientation and header spacing were
    wrong.
  - PN532 on 5 V with 4.7 kΩ I²C pull-ups.
  - LED and amplifier power straight from lever-connector hubs.
  - 330 Ω resistor at the ring end.
  - Rated capacitors, USB-C charger power (20 W or more), a current budget,
    and a staged build-and-test plan.
- **Terminal base and point-to-point builds** (`hardware/reader-wired/`)
  brought in line with the review, around a small perfboard interface board
  for the level shifter and I²C pull-ups.
- The custom PCB is parked until the breadboard build is proven.

## [0.8.0] - 2026-11-17

### Added
- **31 predefined scenes** on every bridge, reader and BP2-POE: a **Scene**
  select with **Play scene**, plus one-press buttons for Rainbow, Lightning,
  Colour cycle, Crossfade, Spin & buzz and Alternating. Also available as
  `magicband.send` with `effect: animation`. Sources: emcot.world and
  Haw8411/magic-band-plus-lights.
- **Fast mode** (on by default): every broadcast mixes in the park's
  `CC 03 00 01 00` "fast mode" ping, which is believed to make bands listen
  continuously, so effects start sooner and repeats land. Optional
  **Fast mode warm-up**, and a **Wake bands** button (`effect: wake`).
- **Hearing bands respond:** the integration listens through Home Assistant's
  Bluetooth adapters and proxies for anything with Disney's Bluetooth ID. It
  logs the device address, signal strength, which proxy heard it and how long
  after the last send, and adds a `magicband_heard` event, a *Last band
  heard* sensor and `magicband.list_heard`.

- **Ways to build the reader** (`hardware/README.md`): breadboard (start
  here), Lonely Binary terminal base, point-to-point wiring, and a custom
  26 × 58 mm PCB (KiCad, routed, Gerbers and JLCPCB files), with a checklist
  to prove each build works.
- **Reader firmware for the custom PCB** (`magicband-reader-pcb.yaml`), in
  the web installer, built in CI with its own update channel.

### Changed
- The integration's setup screen describes what it does.

## [0.7.1] - 2026-11-16

### Security
- **Bridge and reader connections to Home Assistant are now encrypted.**
  Home Assistant gives each board its own key the first time it connects, so
  there's nothing to set up. Boards on 0.7.0 may show a one-off "disabled
  transport encryption" notice: confirm it, then install this update, and
  encryption is switched back on.
- **Unencrypted network firmware uploads are no longer accepted** by the
  installer firmware. Updates come through Home Assistant's Firmware update
  entity. "Take control" in the ESPHome Device Builder adds its own
  password-protected uploads.

### Added
- **Published firmware for the SCREEK BP2-POE**, built from the same shared
  MagicBand code as the bridge and reader. Install it from the web installer
  or the Device Builder, with no secrets needed. Updates then arrive through
  Home Assistant like the other boards. PSRAM is enabled for update headroom.
- CI fails if the single-file BP2-POE config drifts from the shared add-on.

### Fixed
- Starting a release from the Actions page can no longer be cancelled by a
  later push.

### Integration
- No functional changes; version bumped to match.

## [0.7.0] - 2026-11-16

First release with proper version numbers. Everything before this was
development builds (bridge 0.1.0–0.5.2, reader 0.6.0, integration 0.1.0–0.2.0).

### Added
- **Two-part project:** the MagicBand Bridge (Bluetooth effects for
  MagicBand+) and the MagicBand Reader (NFC tap point for original MagicBands
  and MagicBand+), tied together by the MagicBand integration.
- **Web installer for the reader**, alongside the bridge: no secrets or YAML
  needed, Wi-Fi set up in the browser, and updates over Wi-Fi from Home
  Assistant.
- **Integration icons and logo**, shown in Home Assistant 2026.3 and later.
- **`magicband.send` action**, which finds every bridge itself, and
  `magicband.list_bridges`.
- **The integration installs the *MagicBand+ notification* blueprint** and
  keeps it updated, including a copy imported from GitHub.
- **GitHub Releases** with firmware and the integration attached; CI checks
  that all versions match.

### Changed
- The blueprint now uses `magicband.send` and needs the MagicBand integration.
- Reader: LED data moved to GPIO10 (matches the Lonely Binary terminal base),
  and the I2S LRC/BCLK pins were swapped (GPIO5/GPIO6) for straight breadboard
  wiring.
- Reader devices get a unique name (`magicband-reader-xxxxxx`), like bridges.

### Fixed
- **Firmware updates over Wi-Fi failing** on bridges: the PSRAM on N16R8
  boards is now enabled, leaving memory for the HTTPS download alongside
  Bluetooth. Bridges on 0.5.2 or earlier need one USB re-install from the web
  installer to get this fix.

## Development history (before 0.7.0)

- **Bridge 0.5.x:** alternating E1/E2 prefix (more reliable repeats),
  experimental "both" prefix mode, MagicBand light on by default.
- **Bridge 0.4.x:** Bluetooth proxy scanning paused while broadcasting,
  +20 dBm on ESP32-S3.
- **Bridge 0.3.x:** multiple bridges, Command entity, optional Bluetooth
  proxy, reusable add-on package, SCREEK BP2-POE config.
- **Bridge 0.2.0:** decoded timing, RGB colour light, LED masks, animations.
- **Bridge 0.1.0:** first web-installable firmware.
- **Reader 0.6.0:** NFC reader with LED ring, Mickey head, sounds, on-device
  known bands.
- **Integration 0.1.0–0.2.0:** people and bands, reader sync, `magicband.send`.
