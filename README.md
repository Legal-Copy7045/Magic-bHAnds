# Magic bHAnds

Trigger **Disney MagicBand+** lights and haptics from **Home Assistant**, using
an **ESP32-S3** running ESPHome as a Bluetooth LE broadcaster.

```
Home Assistant ──(ESPHome API)──> ESP32-S3 ──(BLE advertisements)──> MagicBand+
 automations / scripts              "beacon"                            lights + vibration
```

The ESP32 doesn't pair with or connect to the band. It broadcasts the same kind
of Bluetooth packets that park beacons send. Any MagicBand+ in range reacts, so
think of it as a room-wide effect. You can't easily target one band.

> Only works with **MagicBand+**. Original MagicBands (1.0/2.0) have no
> Bluetooth receiver for effects.

## Install

**Web installer: https://legal-copy7045.github.io/Magic-bHAnds/**

1. **Prepare the board.** On IPEX boards, click the antenna on first. Plug into
   your computer through the USB-C port labelled **UART**, using a data cable.
2. **Flash it.** Open the web installer in Chrome or Edge, click **Install**,
   then enter your Wi-Fi details when asked. You don't compile or edit YAML.
3. **Add it to Home Assistant.** HA shows a *Discovered* notification for
   "MagicBand Bridge 3fa2c1" through the ESPHome integration (the last six
   characters are unique to each board). Click **Add**. If no notification
   appears: Settings → Devices & services → Add integration → ESPHome, then
   enter the board's IP address from your router.
4. **Test it.** Open the device page, hold the band nearby (a shake wakes it),
   and press **Test red buzz**.
5. **Automate it.** Import the blueprint and build "flash my band when…"
   automations from the UI:

   [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FLegal-Copy7045%2FMagic-bHAnds%2Fblob%2Fmain%2Fhomeassistant%2Fblueprints%2Fautomation%2Fmagicband_notify.yaml)

**Updates:** new firmware shows up in Home Assistant as an update on the device,
and you install it over Wi-Fi.

**More coverage:** flash more boards the same way. See
[Multiple bridges](#multiple-bridges).

**Customising:** if you run the ESPHome Device Builder add-on, the bridge shows
up there with **Take control**. That imports `esphome/magicband-bridge.yaml` as
a package so you can edit it and build your own firmware.

**If Wi-Fi setup fails,** the board starts a hotspot called
"MagicBand Bridge Setup". Join it and pick your network.

## Hardware

The config targets an **ESP32-S3-DevKitC-1 N16R8** style board, such as the
Lonely Binary ESP32-S3 N16R8 IPEX. Any ESP32-S3 should work if you build your
own config (for a Seeed XIAO ESP32-S3: `board: seeed_xiao_esp32s3`,
`flash_size: 8MB`). The board needs nothing else wired to it, just USB power
somewhere central.

**IPEX boards: fit the antenna before powering on.** The module has no built-in
antenna, so without the external one, Wi-Fi and Bluetooth range is almost nil.
Press the small connector straight down until it clicks. You don't need the
pin headers.

The DevKitC-1 has two USB-C ports. Use the one labelled **UART** for the web
installer: the Wi-Fi setup step and logs run on that port.

## Repo layout

| Path | What |
|------|------|
| `components/magicband/` | ESPHome external component (C++) that builds and broadcasts the packets |
| `esphome/magicband-bridge.yaml` | Device config for the ESP32-S3 bridge, used by the web installer and "Take control" |
| `esphome/magicband-addon.yaml` | Reusable MagicBand package (component, actions, entities) for any ESPHome board |
| `esphome/screek-bp2-poe.yaml` | SCREEK BP2-POE config (PoE Bluetooth proxy + MagicBand) |
| `esphome/magicband-reader.yaml` | MagicBand Reader: NFC touch point with LED ring, Mickey and sound |
| `web/` | Web installer page |
| `.github/workflows/firmware.yml` | Builds firmware on every push and publishes the installer to GitHub Pages from `main` |
| `homeassistant/blueprints/` | Automation blueprint |
| `homeassistant/*.yaml` | Example scripts and automations, for YAML users |
| `docs/protocol.md` | What's known about the packet format |

## What you get in Home Assistant

**Entities on the device page:**

| Entity | What it does |
|---|---|
| **MagicBand** (light) | Pick any colour with the colour picker. Nearby bands glow it until you turn it off. The **Effects** list plays captured park animations (rainbow, colour cycle, lightning, …). |
| **Buzz** (button) | Vibrates bands using the **Vibration pattern** setting. |
| **Test red buzz**, **Test rainbow**, **Ping** | Quick tests. |
| **Command** (text, under Configuration) | Takes JSON commands so HA can send to one, several or all bridges. See [docs/commands.md](docs/commands.md). |
| **Bluetooth proxy** (switch, under Configuration) | Off by default. Turn it on to also use this board as a Home Assistant Bluetooth proxy. |
| **Firmware** (update) | Installs new releases over Wi-Fi. |

**Per-board actions**, prefixed `esphome.magicband_bridge_<suffix>_`. Each
of these sends through that one board only. To send through several bridges,
use the blueprint, `script.magicband_send`, or the Command entity.

| Action | Fields |
|--------|--------|
| `color` | `color`, `vibration` |
| `color_advanced` | `color`, `vibration`, `leds` (all/top_left/top_right/bottom_left/bottom_right), `on_seconds` (≈6–52, 0 = default), `fade_seconds` (0–3), `always_on` |
| `rgb` | `red`, `green`, `blue` (0–255), `vibration`, `always_on`, `flash` |
| `dual_color` | `inner`, `outer`, `vibration` |
| `five_color` | `colors` ("centre, top right, bottom right, bottom left, top left"), `vibration` |
| `crossfade` | `color1`, `color2`, `vibration` |
| `circle` | `vibration` |
| `animation` | `name`: lightning, orange_blink, color_cycle, rainbow, circle, crossfade, spin_buzz, show_e913 |
| `ping` | `fast` (bool) |
| `off` | none, turns lights off |
| `raw` | `hex` (e.g. `E9 05 00 2E 0E E5 B3`), `duration_ms` (0 = default) |
| `stop` | none, stops broadcasting and clears the queue |

Colours: `red`, `red_orange`, `orange`, `yellow`, `off_yellow`, `lime`,
`lime_green`, `green`, `cyan`, `blue`, `midnight_blue`, `purple`,
`bright_purple`, `lavender`, `pink`, `white`, `unique`, `random`, `off`, or a
number 0–31.

Vibration: 0 = none, and 1–11 are distinct patterns, from a short tap to a
1-second pulse. See [docs/protocol.md](docs/protocol.md#vibration-byte).

Example from Developer Tools → Actions:

```yaml
action: esphome.magicband_bridge_3fa2c1_color_advanced
data:
  color: pink
  vibration: 2
  leds: all
  on_seconds: 15
  fade_seconds: 2
  always_on: false
```

## Multiple bridges

One board covers roughly a room or two. For more coverage, flash more boards
with the web installer and place them where the bands are used. Each board
gets a unique name (`magicband-bridge-3fa2c1`) and shows up in Home Assistant
as its own device.

- **All bridges (the default).** The blueprint and `script.magicband_send`
  send through every bridge unless you pick specific ones. New bridges are
  included automatically.
- **Some bridges.** In the blueprint, pick the bridges' **Command** entities
  under *Bridges*. In scripts, pass `bridges:` with their entity IDs. See the
  `magicband_kitchen_buzz` example in `homeassistant/magicband_scripts.yaml`.
- **One colour picker for every bridge.** Create a light group: Settings →
  Devices & services → Helpers → Create helper → Group → Light group, then
  add every bridge's **MagicBand** light.

Bands that hear two bridges get the same command twice, a few milliseconds
apart, which should look the same as hearing it once (not yet confirmed on a
real band).

### Other ESPHome boards

The MagicBand parts live in a reusable package, `esphome/magicband-addon.yaml`.
Add it to any ESP32 that already runs ESPHome, including ones on Ethernet, to
make that board a bridge as well:

```yaml
packages:
  magicband: github://Legal-Copy7045/Magic-bHAnds/esphome/magicband-addon.yaml@main
```

**SCREEK BP2-POE:** a ready-made config is in `esphome/screek-bp2-poe.yaml`.
It keeps the board's PoE Bluetooth proxy behaviour, including its scan-tuning controls, and adds MagicBand. See
[docs/screek-bp2-poe.md](docs/screek-bp2-poe.md) for backup, the first USB
install and reconnecting in Home Assistant.

### Bluetooth proxy

Each bridge can also work as an ESPHome **Bluetooth proxy**, extending Home
Assistant's Bluetooth range like a Screek or Shelly proxy does. Turn on the
**Bluetooth proxy** switch on the bridge's device page, under Configuration.
It's off by default, and it remembers its setting through restarts.

Proxying shares the radio with the band broadcasts. The bridge pauses
scanning for the ~2 seconds it broadcasts each command, then resumes, so the
proxy's effect on band range is small.

## MagicBand Reader

A park-style touch point built from an ESP32-S3, a PN532 NFC reader, an LED
ring with a Mickey head and a small speaker. Tap an original MagicBand or a
MagicBand+: the ring spins, Home Assistant receives the band as a **Tag**, the
ring turns green with a chime, and a MagicBand+ also lights up and buzzes. An
optional mode lets HA decide green or red per band.

Parts, wiring and setup are in [docs/reader.md](docs/reader.md). The config
is `esphome/magicband-reader.yaml`.

## Component options

```yaml
esp32_ble:
  id: ble

light:
  - platform: magicband   # optional RGB light entity
    name: MagicBand

magicband:
  id: band
  duration: 2s      # broadcast length per command (100ms–30s)
  min_interval: 20ms
  max_interval: 40ms
  tx_power: max     # +20 dBm on ESP32-S3/C3, +9 dBm on the original ESP32
  pause_scanning: true    # pause Bluetooth-proxy scanning while broadcasting
  prefix_mode: alternate  # off / alternate (default) / both (experimental)
  queue_size: 8     # commands queued while one is broadcasting
```

Commands are queued and broadcast one after another, and they never block
ESPHome. The component drives BLE advertising directly, so it can't share a
device with `esp32_ble_beacon`, `esp32_improv` or `esp32_ble_server`. It can
share with `esp32_ble_tracker` and Bluetooth proxy scanning, but heavy scanning
reduces broadcast airtime.

## Range and reliability tips

- Bridges transmit at maximum power by default: +20 dBm on ESP32-S3. In
  regions with a 20 dBm EIRP limit (such as the EU) and a high-gain antenna,
  set `tx_power: 17dBm`.
- Bands only listen now and then. If commands are missed, shake the band.
- Each command starts with `E1 00` or `E2 00`, alternating, as seen in park
  captures. In testing this made repeated commands noticeably more reliable.
  It's on by default. The **Prefix mode** setting on the device page can turn
  it off, or set it to *Both (experimental)*, which also switches between
  `E1` and `E2` every 100 ms within each broadcast.
- On boards that are also Bluetooth proxies, scanning pauses during each
  ~2 second broadcast. In testing this improved both range and reliability.

## Caveats

- Bands sleep to save battery. A sleeping band may need a shake or a longer
  burst before it reacts.
- The protocol is unofficial and reverse-engineered. See
  [docs/protocol.md](docs/protocol.md).
- This is for home tinkering. Don't run it anywhere near the parks.

## Credits

This project builds on other people's work.

**Protocol research**
- **[emcot.world: Disney MagicBand+ Bluetooth Codes](https://emcot.world/Disney_MagicBand%2B_Bluetooth_Codes)**:
  the community reverse-engineering wiki this project is based on. It covers
  the packet layouts, timing byte, vibration patterns, LED masks, colour
  palette, RGB command and the captured show animations. See
  [docs/protocol.md](docs/protocol.md).
- **[xxfunprojectsxx/esp32_magicband](https://github.com/xxfunprojectsxx/esp32_magicband)**:
  an ESP32-S3 MagicBand+ broadcaster that we used to cross-check the command
  byte layouts and colour codes. No code was copied (that repo has no
  licence); this project's firmware was written independently.
- **[Adafruit: BLE Beacon NeoPixels](https://learn.adafruit.com/ble-beacon-neopixels)**:
  Adafruit's MagicBand+ beacon project, referenced by the emcot.world wiki.
  It was also one of the first sources found for this project.

**MagicBand reader projects** (inspiration for the reader; no code used)
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

**Hardware**
- Developed for the Lonely Binary ESP32-S3 N16R8 IPEX board, which uses the
  ESP32-S3-DevKitC-1 layout.

MagicBand and MagicBand+ are trademarks of Disney. This is an unofficial hobby
project with no affiliation to, or endorsement from, Disney, Adafruit or any of
the projects above.

## Development

```bash
pip install esphome
cd esphome
# Build against the local component instead of the copy on GitHub main:
esphome -s component_source ../components compile magicband-bridge.yaml
```

To release a new firmware version, bump `project_version` in
`esphome/magicband-bridge.yaml` and merge to `main`. Devices then offer the
update in Home Assistant.
