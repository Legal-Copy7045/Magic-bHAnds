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
   "MagicBand Bridge" through the ESPHome integration. Click **Add**. If no
   notification appears: Settings → Devices & services → Add integration →
   ESPHome → `magicband-bridge.local`.
4. **Test it.** Open the device page, hold the band nearby (a shake wakes it),
   and press **Test red buzz**.
5. **Automate it.** Import the blueprint and build "flash my band when…"
   automations from the UI:

   [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FLegal-Copy7045%2FMagic-bHAnds%2Fblob%2Fmain%2Fhomeassistant%2Fblueprints%2Fautomation%2Fmagicband_notify.yaml)

**Updates:** new firmware shows up in Home Assistant as an update on the device,
and you install it over Wi-Fi.

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
| `esphome/magicband-bridge.yaml` | Device config, used by the web installer and "Take control" |
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
| **Firmware** (update) | Installs new releases over Wi-Fi. |

**Actions** for scripts and automations, all prefixed `esphome.magicband_bridge_`:

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
action: esphome.magicband_bridge_color_advanced
data:
  color: pink
  vibration: 2
  leds: all
  on_seconds: 15
  fade_seconds: 2
  always_on: false
```

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
  tx_power: 9dBm    # -12dBm .. 9dBm
  queue_size: 8     # commands queued while one is broadcasting
```

Commands are queued and broadcast one after another, and they never block
ESPHome. The component drives BLE advertising directly, so it can't share a
device with `esp32_ble_beacon`, `esp32_improv` or `esp32_ble_server`. It can
share with `esp32_ble_tracker` and Bluetooth proxy scanning, but heavy scanning
reduces broadcast airtime.

## Caveats

- Bands sleep to save battery. A sleeping band may need a shake or a longer
  burst before it reacts.
- The protocol is unofficial and reverse-engineered. See
  [docs/protocol.md](docs/protocol.md).
- This is for home tinkering. Don't run it anywhere near the parks.

## Credits

The protocol information comes from the community reverse-engineering effort
documented at [emcot.world](https://emcot.world/Disney_MagicBand%2B_Bluetooth_Codes).

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
