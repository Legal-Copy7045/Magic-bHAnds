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

## Repo layout

| Path | What |
|------|------|
| `esphome/components/magicband/` | ESPHome external component (C++), which builds and broadcasts packets |
| `esphome/magicband-bridge.yaml` | Example device config for an ESP32-S3, exposing actions to HA |
| `esphome/secrets.example.yaml` | Template for `secrets.yaml` |
| `homeassistant/` | Example scripts and automations |
| `docs/protocol.md` | What's known about the packet format |

## Hardware

Any ESP32-S3 board works, e.g. an ESP32-S3-DevKitC-1 or a Seeed XIAO ESP32-S3.
You need a USB **data** cable. The board needs no other parts or wiring: it
just needs USB power somewhere central in the house.

If your board isn't a DevKitC-1, change `board:` in the YAML. For a XIAO, use
`seeed_xiao_esp32s3`.

## Setup

1. In Home Assistant, install the **ESPHome Device Builder** add-on/app.
2. Copy `esphome/components/` and `esphome/magicband-bridge.yaml` into
   `/config/esphome/`, using the Samba, File editor or VS Code add-ons.
3. Add `wifi_ssid`, `wifi_password`, `ota_password`, `fallback_ap_password` and
   `api_encryption_key` to `/config/esphome/secrets.yaml`. See
   `secrets.example.yaml`.
4. Plug the ESP32-S3 into the computer running your browser. In the ESPHome
   dashboard, choose **Install → Plug into this computer** for the first flash.
   Later updates go over Wi-Fi.
   - If the board isn't detected, hold **BOOT**, tap **RESET**, then release
     **BOOT**.
5. HA discovers the device. Adopt it, then open its device page and press
   **Test red buzz**. Have the band nearby; a shake can help wake it.
6. Copy `homeassistant/magicband_scripts.yaml` into your `scripts.yaml`, and
   use the automations file as inspiration.

## Actions exposed to Home Assistant

The device is named `magicband-bridge`, so each action is prefixed
`esphome.magicband_bridge_`.

| Action | Fields |
|--------|--------|
| `color` | `color`, `vibration` (0–15) |
| `dual_color` | `color1`, `color2`, `vibration` |
| `five_color` | `colors` ("red, orange, yellow, green, blue"), `vibration` |
| `crossfade` | `color1`, `color2`, `vibration` |
| `circle` | `vibration` |
| `ping` | none |
| `raw` | `hex` (e.g. `E9 05 00 2E 0E E5 B3`), `duration_ms` (0 = default) |
| `stop` | none, stops broadcasting and clears the queue |

Colours: `red`, `red_orange`, `orange`, `yellow`, `off_yellow`, `lime`,
`lime_green`, `green`, `cyan`, `blue`, `midnight_blue`, `purple`,
`bright_purple`, `lavender`, `pink`, `white`, `off`, `random`, or a number
0–31.

Example from Developer Tools → Actions:

```yaml
action: esphome.magicband_bridge_color
data:
  color: pink
  vibration: 4
```

## Component options

```yaml
esp32_ble:
  id: ble

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
