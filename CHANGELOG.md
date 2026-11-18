# Changelog

All notable changes to Magic bHAnds. The bridge firmware, reader firmware and
Home Assistant integration share one version number.

## [0.9.10] - 2026-11-18

### Integration
- **Last band name on every reader's page:** whose band was last tapped
  ("Morgan's MagicBand+ (Villains)", or your name for it), with the NFC ID,
  person and whether it was let in as attributes. It's the integration's
  own sensor, attached to the reader's device.

### Reader
- The firmware's own sensor is now **Last band ID** (diagnostic): the raw
  NFC ID. Its entity ID is unchanged.

### Home Assistant
- **Management dashboard** (`homeassistant/dashboards/magicband.yaml`):
  bands, people, readers and bridges on one page, with buttons to manage
  people and bands, sync readers, and wake or ping bands. Built-in cards
  only; it finds everything by itself.

## [0.9.9] - 2026-11-18

### Reader
- **The tap sequence is configurable** on the reader's device page
  (Configuration): **Checking colour**, **Checking circles**, **Circle
  time**, **Welcome colour**, **Welcome pulses**, **Denied colour**,
  **Denied pulses** and **Pulse time**. Defaults match 0.9.8: two white
  circles, one green pulse, two red pulses.

## [0.9.8] - 2026-11-18

### Reader
- **New tap sequence on the ring:** two quick white circles chase round it
  while the band is checked (one circle every 0.5 s, whatever the LED
  count), then **one green pulse** for a welcome or **two red pulses** for
  a denied band. Replaces the spin, the 3-second solid green and the red
  strobe.

### Integration
- **Security:** adapter names (**Heard by**, **Closest**) no longer read
  other integrations' stored settings. They come from the device registry
  only: a USB adapter's device by its Bluetooth address, an ESPHome proxy's
  by its Wi-Fi MAC (an ESP32's Bluetooth address is its base MAC + 2).


### Hardware
- **Compact build tested** up to sound: power, NFC (bands read, known
  welcomed, unknown denied) and the amplifier at 100 %, on USB power. Its
  section in the wired build guide is now the tested step-by-step, with
  the checks and readings from the build, and a note on other tag
  automations reacting to band taps.

## [0.9.7] - 2026-11-18

### Fixed
- **Linking dropped the owner.** Linking a Bluetooth band that belonged to
  someone to an NFC band that didn't yet belong to anyone left the band with
  no owner, so readers denied it. The NFC band now takes the Bluetooth
  band's owner (if it already has an owner, that one is kept), and readers
  get the updated allowed list straight away.

## [0.9.6] - 2026-11-18

### Integration
- **Your names for bands are used everywhere.** If you rename a band's
  device in Home Assistant, that name now shows in **Link a band's
  Bluetooth**, the pairing notification, `list_bluetooth_bands` and the
  `magicband_band_seen` event, and works as `bluetooth_band` in actions.
- **Linking keeps the name.** Linking a renamed Bluetooth band to its NFC
  band gives the merged device the name you chose.

### Hardware
- **Compact (solderless) build:** the point-to-point layout on a 400-point
  half breadboard with jumpers, with its own diagram
  (`docs/reader-compact.svg`) and steps in the wired build guide.

## [0.9.5] - 2026-11-18

### Fixed
- **Reader boot loop** (crash at start-up, then safe mode after 10 tries).
  The LED count, colour order, brightness and idle glow settings restore
  their values during set-up and then touched the ring before its driver
  was ready. They now wait until boot has finished. Readers in safe mode
  need reinstalling once over USB from the web installer.

## [0.9.4] - 2026-11-17

### Integration
- **Heard by** and **Closest** on every band's device page: which bridge,
  proxy or adapter heard its latest beacon, and which heard it strongest in
  the last 20 minutes (a rough "which room"). Shown by their Home Assistant
  device names, so "Kitchen MagicBand Bridge" rather than a Bluetooth
  address. The Signal and Last seen attributes use the same names.

## [0.9.3] - 2026-11-17

### Integration
- **Battery confirmed.** Bands put on charge went from 50 and 72 to 98, so
  the beacon's level byte is the battery percentage. Each band's
  **Battery** sensor is now a real battery sensor (battery icon, battery
  views, low-battery automations); existing entity IDs are kept.

### Removed
- The custom reader PCB (KiCad design, its firmware build and its web
  installer button) is out of date, so it's been taken out for now. It's in
  the git history and in release v0.9.2 and earlier, for when it's revisited.

## [0.9.2] - 2026-11-17

### Integration
- Bands sending the longer `C0 13` beacon (seen from a band just switched
  on) are recognised too. Each band records which beacon forms it has sent.

## [0.9.1] - 2026-11-17

### Integration
- **One device per band.** Every band tapped on a reader now has its own
  device with a **Last tap** sensor (reader, scans, owner, allowed). Linking
  its Bluetooth side merges the two into one device: Last tap, Nearby, Last
  seen, Signal and Battery together, named after its label or owner.
  Unlinking splits them again. `magicband.list` includes each band's
  Bluetooth side.

## [0.9.0] - 2026-11-17

### Integration
- **Bands over Bluetooth.** Every MagicBand+ sends a status beacon about
  every 15 minutes. The integration now recognises each band from it,
  although its Bluetooth address changes every time, and gives each one a
  device: **Nearby** (presence), **Last seen**, **Signal** and **Battery
  (unconfirmed)**. Stored, so it survives restarts.
- **Pairing Bluetooth with NFC.** Tapping a band on a reader links it to the
  Bluetooth band heard in the next 20 minutes, when it's clear which one;
  otherwise link it under **Configure → Link a band's Bluetooth** or with
  `magicband.link_bluetooth`. A Bluetooth band can also be given straight
  to a person.
- New actions: `list_bluetooth_bands` (raw beacons, level history, changing
  bits), `link_bluetooth`, `unlink_bluetooth`, `forget_bluetooth`. New event:
  `magicband_band_seen`.
- The beacon format as far as it's understood is in docs/protocol.md.

### Fixed
- The 10-minute reader sync and the start-up sync ran their callbacks off
  Home Assistant's event loop (Home Assistant warns about this). They now
  run on the loop.


### Reader
- **LED count and colour order are now settings** on the reader's device
  page (Configuration: *LED count* 1–60, *LED colour order* GRB/RGB), so the
  web installer's firmware works with any ring or strip; no "Take control"
  needed.
- **LED brightness** (5–100 %) and **Idle glow** (0–100 %, 0 = off)
  settings, so the ring can be tuned after installing.
- **Step-by-step build guides** for the breadboard and for the terminal
  base and point-to-point builds (`build.md` in each folder), with a check
  after every stage. The specs, shopping list and diagrams are now written
  for generic parts: a CH224K USB-C PD trigger set to 5 V, a 5-pin
  MAX98357A amplifier kit on its own cable, a 35-LED WS2812B ring; Adafruit
  equivalents are listed alongside.
- **Automatic power cap:** above 24 LEDs the output is capped at
  24 ÷ count, so full white stays within the 20 W supply (e.g. a generic
  35-LED WS2812B ring runs at up to 68 %).

## [0.8.3] - 2026-11-17

### Integration
- **Band messages get their own history.** `magicband.list_heard` now also
  returns `bands`: the last 200 messages from bands, kept separately from the
  30 most recent messages of any kind. Your bridges' own commands fill that
  30-entry list within a minute, so band messages used to be pushed out
  before you could look.

### Also in this release
- The reader's `ring_color_order` setting, the shopping list's generic
  alternatives, and the new power and interface-board diagrams (see 0.8.2).

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
