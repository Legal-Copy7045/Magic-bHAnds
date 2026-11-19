# Changelog

All notable changes to MagicbHAnds. The bridge firmware, reader firmware and
Home Assistant integration share one version number.

## [0.10.6] - 2026-11-19

### Fixed
- **Health tiles:** CPU temperature is shown in Home Assistant's own unit
  (°F or °C) and judged on the Celsius value; it showed Fahrenheit readings as
  "°C" and marked them as too hot. "Loop time" is now "Slowest loop" and only
  turns amber from 1 s (red from 3 s): a few hundred ms is normal.
- No firmware changes (the version number is shared, so devices offer the
  same firmware as 0.10.6).

## [0.10.5] - 2026-11-19

### Health of the readers and bridges
- **Firmware (reader and bridge):** new diagnostic sensors: **Wi-Fi signal**,
  **Wi-Fi network**, **IP address**, **CPU temperature**, **Last restart**
  (changes only when it restarts) and **Reset reason**, **Free memory**,
  **Largest free block** and **Loop time**. They're throttled so Home
  Assistant's history stays small: Wi-Fi signal and temperature are sent when
  they change noticeably (3 dB, 1 °C) or every 5 minutes at most; memory and
  loop time every 5 minutes. The time comes from Home Assistant.
- **Management page:** each reader and bridge card shows these as health
  tiles (Wi-Fi strength, up for, CPU temperature, free memory, loop time, IP
  address), coloured when something looks wrong. The SCREEK BP2-POE's own
  sensors show the same way.

## [0.10.4] - 2026-11-19

New features, plus security fixes from a review of the whole project.

### New
- **Band schedules and expiry.** Each band can have a daily time window
  (overnight windows work), days of the week and an expiry date
  (`magicband.set_band_access`, or the band's **Manage** on the page).
  Outside them the band is denied, the readers' lists follow within a
  minute, and `magicband_tap` reports `allowed: false`.
- **Enrolment.** `magicband.enrol` (or **Enrol bands** next to a person):
  for up to 15 minutes, every band tapped that nobody owns is given to that
  person, numbered if you give a nickname. Bands that belong to someone are
  never taken.
- **Personal welcome.** Each person can have a welcome colour; readers
  (0.10.4 firmware) welcome their bands in it, on the ring and on their
  MagicBand+.
- **Tap history.** The management page lists recent taps (`magicband.history`,
  admins), taps appear in Home Assistant's logbook ("welcomed at Front
  Door"), and each MagicBand+ shows a 7-day battery sparkline.
- **Charge me reminders.** When a MagicBand+ drops to the reminder level
  (Configure → Settings, default 20 %), it shows in Repairs and fires
  `magicband_battery_low`; the new **MagicbHAnds: charge me reminder**
  blueprint sends a phone notification. It resets once the band is charged.
- **Repairs.** A reader that rejects the allowed list, a list too long for
  the readers, a reader offline for 15 minutes and low batteries show in
  Settings → Repairs and clear themselves.
- **Reader health.** Each reader has an **Allowed list** sensor (up to date,
  not applied, sent but unconfirmed on older firmware, offline); the page
  shows it with firmware updates; the reader's idle glow turns amber while
  Home Assistant isn't connected.
- **Diagnostics download** with band IDs shortened and names replaced.
- **CI** builds and tests every branch, not just `main`.

See [docs/security.md](docs/security.md) for the security model and what's
left.

### Breaking changes and things to do
- **Bridge and reader firmware: no fallback setup hotspot.** ESPHome's captive
  portal accepts a firmware upload from anyone who joins it, and the open
  hotspot could be forced on by knocking a board off Wi-Fi for 90 seconds.
  Wi-Fi is now set and changed over USB with the web installer.
- **Admins only:** the actions that change who's allowed in (`add_person`,
  `update_person`, `remove_person`, `assign_band`, `unassign_band`,
  `remove_band`, `link_bluetooth`, `unlink_bluetooth`, `forget_bluetooth`)
  and those that list band IDs (`list`, `list_bluetooth_bands`,
  `list_heard`), and the MagicbHAnds sidebar page. The new `set_band_access`,
  `enrol`, `stop_enrolment` and `history` are admin-only too.
- **Turn off "Allow the device to perform Home Assistant actions"** on
  readers (ESPHome → the reader → Configure). The setup guides used to ask for
  it, but tag scans don't need it, and it would let a tampered reader call any
  action.
- `magicband.send` only accepts MagicBand bridges in `bridges`.
- `magicband.sync` returns `readers`, `applied` and `failed` (was `readers`).

### Integration
- Automatic Bluetooth pairing no longer gives an NFC tag the Bluetooth band's
  owner. Before, tapping any tag while the only unlinked band heard belonged
  to someone made that tag theirs and let it in. That case now asks for a
  manual link; other automatic links show a notification.
- Only real NFC IDs (4, 7 or 10 bytes of hex) are recorded, assigned or
  allowed. The reader's "Test welcome" button (`TEST`) and malformed or
  non-ASCII IDs are ignored; older stored IDs that aren't valid stay but are
  never allowed.
- `magicband.send` writes the bridges' Command entities with the caller's
  context, so Home Assistant's permissions and logbook apply.
- Readers that reject the allowed list are reported (notification and the
  `sync` result), and so is a list too long for the readers to store.
- Limits against made-up radio traffic: at most 25 unclaimed Bluetooth bands
  (long-unheard ones are dropped, linked or owned bands never), 60
  `magicband_heard` events a minute, and 100 unassigned NFC bands.
- A damaged storage file no longer stops the integration loading; damaged
  entries are skipped.
- The management page escapes everything it shows from entity attributes.
- The sidebar panel loads the page only through Home Assistant's own
  authenticated fetch and never reads the login token itself.

- Taps only count from MagicBand readers that are ESPHome devices, and only
  those get the allowed list. Before, any device with the reader's model
  counted, and other integrations (a phone registered with the mobile app)
  let any user choose a model and name, so a user could fake a tap from a
  "reader" with your front-door reader's name; and any ESPHome device that
  declared a `set_known_bands` action got every allowed ID.
- A band's beacon counts at most once every 30 seconds per adapter, so a
  replayed beacon can't flood events and history or fake the battery level.
- Bluetooth bands linked automatically to a tag nobody owns count towards the
  cap; links to NFC bands that are dropped are removed; a band's type no
  longer keeps an unassigned band from being dropped (any user can set it).
- `magicband.send`: at most 30 commands a minute per bridge, and raw
  `command:` dicts get the same time limits as the normal fields.

### Firmware
- Reader: holds 213 allowed bands (7-byte IDs), up from 106. Updating
  clears the reader's stored list once; Home Assistant sends it again as soon
  as the reader reconnects.
- Reader: logs at INFO and never logs band IDs (it used to print the
  allowed list on its USB port at every sync, and every tag read).
- Reader: a new allowed list is checked in full. A malformed list, or one too
  long to store, empties the reader's list (everyone is
  denied) instead of leaving the old one in place, so a revoked band can't
  stay allowed, and the reader tells Home Assistant whether it applied it.
- Reader: "Allow last band" only accepts real NFC IDs.
- All boards: one command broadcasts for at most 60 seconds.

### Build and release
- GitHub Actions pinned to commit SHAs; checkouts don't keep credentials; the
  release adds signed build-provenance attestations.
- The web installer serves its own copy of ESP Web Tools, checked against a
  fixed hash, instead of loading it from unpkg.

## [0.10.3] - 2026-11-19

### Integration
- **Waltograph lettering.** The logo wordmark and the management page's
  title and section headings use the Waltograph font (by Justin Callaghan,
  mickeyavenue.com, Creative Commons NonCommercial-ShareAlike). The font
  ships with the integration, with its readme and licence, and the page
  loads it from `/magicbhands_static/fonts/`. Body text, cards and numbers
  keep the original fonts.

## [0.10.2] - 2026-11-19

### Integration
- **Group, sort and find bands on the management page.** Group by person,
  band type, where (closest bridge), nearby or away, battery, last reader,
  allowed in, or Bluetooth linked; sort by owner, name, last tap, last
  heard, battery (lowest first), most taps or signal; a search box. The
  choice is remembered in that browser.
- **More ways to send to the bands.** New one-tap buttons (purple, pink,
  white, rainbow, colour cycle, lightning, spin and buzz, buzz, stop) and a
  "build your own" panel with every effect the bridges support: colours,
  colour picker, light shows, buzz strength, how long, which LEDs, fade-out,
  stay on, and sending through one bridge only (just the bands in that room)
  or all of them.

## [0.10.1] - 2026-11-19

### Integration
- **Management page branding.** The page now carries the MagicbHAnds logo and
  wordmark (the "HA" in blue), the brand's purple accent and a
  purple-blue-teal strip across the header, in light and dark mode. The logo
  is inline, so it shows wherever the page is served.
- **Band type: MagicBand+ or standard MagicBand.** Each tapped band has a
  **Band type** select. A band linked to its Bluetooth is a MagicBand+
  automatically. Mark the original NFC-only bands as *Standard MagicBand*
  and they're no longer listed as "haven't been heard over Bluetooth yet"
  (they never will be), and tapping them no longer starts the Bluetooth
  pairing window, so they can't be paired by mistake with a MagicBand+
  that's nearby. The management page asks about bands whose type isn't
  known yet, with one-tap buttons, and shows the type on each band card.

## [0.10.0] - 2026-11-19

### Integration
- **MagicbHAnds management page in the sidebar.** Assign new bands, link a
  band's Bluetooth to its NFC side, see every band (owner, last tap, nearby,
  battery, closest bridge), manage people, send to every band, and set up
  the readers and bridges, all on one live page. It's the page built for
  the home-dashboards project, packaged with the integration. Turn the
  sidebar entry off under **Configure → Settings**.

### Fixed
- **"Updating a disabled entity" warning:** the reader's **Last band name**
  is no longer written while it's disabled.
- **Deprecated device lookups:** the integration no longer calls
  `DeviceRegistry.async_get_device`, which Home Assistant has deprecated.
- The Configure screens kept resetting the integration's settings; they
  now keep them.

## [0.9.14] - 2026-11-19

### Fixed
- **A second "MagicBand" device under the integration.** The reader's
  **Last band name** sensor could create a device of its own instead of
  joining the reader's device. It now joins the reader's device directly,
  and the stray device is removed on start-up (its sensor moves back to the
  reader, keeping its entity ID).

## [0.9.13] - 2026-11-18

### Reader
- **Band light-up power** setting (Configuration, −24 to 0 dBm, default
  −12 dBm, was a fixed 0 dBm). Every MagicBand+ in range reacts to the
  welcome's light-up, because a broadcast can't be addressed to one band;
  turning this down limits it to the band on the reader.


### Hardware
- **Compact build tested on the USB-C PD supply** with the Wago hubs. The
  guide's hub port table is the tested one, and a fix is added: keep a short
  ground jumper from the ESP32 to the breadboard (and from L− to the
  amplifier's ground row) as well as the hub wires, or the sound crackles.
  The wired builds' guide says the same.

## [0.9.12] - 2026-11-18

### Integration
- **Renamed to MagicbHAnds** everywhere you see the integration: its name in
  Home Assistant and HACS, the set-up screen, its hub device, notifications
  and messages, the docs and the dashboard. Existing installs are renamed
  on the next start. Unchanged: the `magicband` domain and actions,
  entity IDs (the hub's sensors keep `sensor.magicband_…`), and the names
  of the bands, bridges and readers themselves.
- The project itself is **MagicbHAnds** too: README, docs, web installer,
  release titles, and a new logo (light and dark, and the integration's
  brand images). The repository name and its URLs are unchanged.

## [0.9.11] - 2026-11-18

### SCREEK BP2-POE
- **Bluetooth proxy switch**, the same as the MagicBand Bridge's, so the
  proxy can be turned off on either kind of bridge. It defaults to on, so
  nothing changes until you turn it off. Scan Interval and Scan Window only
  restart scanning while the proxy is on.

## [0.9.10] - 2026-11-18

### Integration
- **Last band name on every reader's page:** whose band was last tapped
  ("Jackie's MagicBand+ (Villains)", or your name for it), with the NFC ID,
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
