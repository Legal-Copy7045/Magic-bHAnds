# MagicBand Bridge

Part 1 of [MagicbHAnds](../README.md). An ESP32-S3 running ESPHome that
broadcasts the Bluetooth messages MagicBand+ bands respond to, so Home
Assistant can light them up and make them vibrate. The bridge doesn't pair
with bands: any MagicBand+ in range reacts, so think of it as a room-wide
effect. Use more bridges for more coverage.

> Only **MagicBand+** has the Bluetooth receiver for effects. Original
> MagicBands work with the [reader](reader.md) instead.

## Install

**Web installer: https://legal-copy7045.github.io/Magic-bHAnds/**

1. **Prepare the board.** On IPEX boards, click the antenna on first. Plug into
   your computer through the USB-C port labelled **UART**, using a data cable.
2. **Flash it.** Open the web installer in Chrome or Edge, click **Install the bridge**,
   then enter your Wi-Fi details when asked. You don't compile or edit YAML.
   Give it Wi-Fi and add it to Home Assistant (next step) straight after
   flashing: a brand-new board with no Wi-Fi set starts its open setup hotspot
   right away, and until it's added to Home Assistant whoever connects first
   could claim it. They can't install code on it, but you'd have to erase it
   and flash it again over USB ([security.md](security.md), "First
   connection").
3. **Add it to Home Assistant.** HA shows a *Discovered* notification for
   "MagicBand Bridge 3fa2c1" through the ESPHome integration (the last six
   characters are unique to each board). Click **Add**, and leave **Allow the
   device to perform Home Assistant actions** off (the integration doesn't
   need it). If no notification
   appears: Settings → Devices & services → Add integration → ESPHome, then
   enter the board's IP address from your router.
4. **Test it.** Open the device page, hold the band nearby (a shake wakes it),
   and press **Test red buzz**.
5. **Automate it.** Install the [MagicbHAnds integration](integration.md) from
   HACS. It adds the **Send MagicBand effect** action (`magicband.send`) and
   installs the *MagicBand+ notification* blueprint, so you can build "flash
   my band when…" automations from the UI.

**Updates:** new firmware shows up in Home Assistant as an update on the device,
and you install it over Wi-Fi.

**Security:** the connection to Home Assistant is encrypted. Home Assistant
gives each board its own key when it first connects, so there's nothing to set
up.

**More coverage:** flash more boards the same way. See
[Multiple bridges](#multiple-bridges).

**Customising:** if you run the ESPHome Device Builder add-on, the bridge shows
up there with **Take control**. That imports `esphome/magicband-bridge.yaml` as
a package so you can edit it and build your own firmware. The official firmware
only accepts signed updates, so install your first own build over USB (see
[security.md](security.md), "Signed updates").

**If your Wi-Fi changes later** (a new router or password), you don't need
USB: when the bridge can't reach its Wi-Fi for **2 minutes** (or has none set
yet) it starts an open hotspot called **MagicBand Bridge Setup**. Join it from
a phone, pick the new network on the page that opens (or browse to
`http://192.168.4.1`) and enter its password; the hotspot goes away once the
bridge is back on Wi-Fi, and never starts while its Wi-Fi works. Plugging the
board into a computer and using the web installer's **Change Wi-Fi** (Improv
over USB) still works too. Someone nearby during a Wi-Fi outage could join the
hotspot and set a different network, taking the bridge offline, but can't
install firmware through it: the official firmware only accepts signed
updates. Your own builds don't have the hotspot (see [security.md](security.md),
"Setup hotspot").

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

## What you get in Home Assistant

**Entities on the device page:**

| Entity | What it does |
|---|---|
| **MagicBand** (light) | Pick any colour with the colour picker. Nearby bands glow it until you turn it off. The **Effects** list plays captured park animations (rainbow, colour cycle, lightning, …). |
| **Buzz** (button) | Vibrates bands using the **Vibration pattern** setting. |
| **Scene** (select) + **Play scene** (button) | Plays any of the 31 [predefined scenes](commands.md#scenes). |
| **Scene: Rainbow**, **Lightning**, **Colour cycle**, **Crossfade**, **Spin & buzz**, **Alternating** (buttons) | One-press scenes. |
| **Wake bands** (button) | Sends the fast-mode ping for 15 s, so bands react quickly to what follows. |
| **Fast mode** (switch, under Configuration) | On by default. Mixes the fast-mode ping into every broadcast. See [Fast mode](protocol.md#fast-mode-cc-03-00-01-00). |
| **Fast mode warm-up** (number, under Configuration) | 0–15 s, default 0. After 30 s of quiet, sends the fast ping on its own first. More reliable first effect, but delayed. |
| **Test red buzz**, **Test rainbow**, **Ping** | Quick tests. |
| **Command** (text, under Configuration) | Takes JSON commands so HA can send to one, several or all bridges. See [docs/commands.md](commands.md). |
| **Bluetooth proxy** (switch, under Configuration) | Off by default. Turn it on to also use this board as a Home Assistant Bluetooth proxy. |
| **Firmware** (update) | Installs new releases over Wi-Fi. |
| **Automatic updates** | Off by default. On: the bridge installs a new release by itself between 3 and 4 am (local time, by its internet clock), without Home Assistant starting it. Only signed releases install, and only one newer than the bridge has: it never goes back to an older release by itself. An update you start from **Firmware** installs whichever signed release the site offers. |
| **Time zone** | The bridge's local time zone for the automatic-update window (default Eastern, New York). It keeps time from an internet time server as well as from Home Assistant. |
| **Wi-Fi signal**, **Wi-Fi network**, **IP address**, **CPU temperature**, **Last restart**, **Reset reason**, **Free memory**, **Largest free block**, **Loop time** (diagnostic) | Its health, shown as tiles on the MagicbHAnds page. Sent sparingly (on a real change or every 5 minutes). |

**Per-board actions**, prefixed `esphome.magicband_bridge_<suffix>_`. Each
of these sends through that one board only. To send through several (or all)
bridges, use the MagicbHAnds integration's `magicband.send` (the blueprint
and `script.magicband_send` both use it), or write JSON to the Command entity.

| Action | Fields |
|--------|--------|
| `color` | `color`, `vibration` |
| `color_advanced` | `color`, `vibration`, `leds` (all/top_left/top_right/bottom_left/bottom_right), `on_seconds` (about 5.5–52, 0 = default), `fade_seconds` (0–3), `always_on` |
| `rgb` | `red`, `green`, `blue` (0–255), `vibration`, `always_on`, `flash` |
| `dual_color` | `inner`, `outer`, `vibration` |
| `five_color` | `colors` ("centre, top right, bottom right, bottom left, top left"), `vibration` |
| `crossfade` | `color1`, `color2`, `vibration` |
| `circle` | `vibration` |
| `animation` | `name`: a [scene](commands.md#scenes) id or label |
| `ping` | `fast` (bool) |
| `wake` | `seconds`: fast-mode ping on its own (default 15) |
| `off` | none, turns lights off |
| `raw` | `hex` (e.g. `E9 05 00 2E 0E E5 B3`), `duration_ms` (0 = default) |
| `stop` | none, stops broadcasting and clears the queue |

Colours: `red`, `red_orange`, `orange`, `yellow`, `off_yellow`, `lime`,
`lime_green`, `green`, `cyan`, `blue`, `midnight_blue`, `purple`,
`bright_purple`, `lavender`, `pink`, `white`, `unique`, `random`, `off`, or a
number 0–31.

Vibration: 0 = none, and 1–11 are distinct patterns, from a short tap to a
1-second pulse. See [docs/protocol.md](protocol.md#vibration-byte).

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
[docs/screek-bp2-poe.md](screek-bp2-poe.md) for backup, the first USB
install and reconnecting in Home Assistant.

### Bluetooth proxy

Each bridge can also work as an ESPHome **Bluetooth proxy**, extending Home
Assistant's Bluetooth range like a Screek or Shelly proxy does. Turn on the
**Bluetooth proxy** switch on the bridge's device page, under Configuration.
It's off by default, and it remembers its setting through restarts.

Proxying shares the radio with the band broadcasts. The bridge pauses
scanning for the ~2 seconds it broadcasts each command, then resumes, so the
proxy's effect on band range is small.

**Active or passive scanning** isn't a switch on the bridge: Home Assistant
chooses it. Go to **Settings → Devices & services → ESPHome → the bridge →
Configure → Bluetooth scanning mode** (Auto, Active or Passive). Auto is
fine; the bridge supports both.

## Range and reliability tips

- Bridges transmit at maximum power by default: +20 dBm on ESP32-S3. In
  regions with a 20 dBm EIRP limit (such as the EU) and a high-gain antenna,
  set `tx_power: 18dBm` or `15dBm` (on ESP32-S3 the steps are −24 to +18
  in 3 dB steps, plus 20).
- Bands only listen now and then. **Fast mode** (on by default) asks them to
  listen continuously. If the first effect after a quiet spell is often
  missed, set **Fast mode warm-up** to 5–10 s, or press **Wake bands** first.
  Shaking the band also wakes it.
- Each command starts with `E1 00` or `E2 00`, alternating, as seen in park
  captures. In testing this made repeated commands noticeably more reliable.
  It's on by default. The **Prefix mode** setting on the device page can turn
  it off, or set it to *Both (experimental)*, which also switches between
  `E1` and `E2` every 100 ms within each broadcast.
- On boards that are also Bluetooth proxies, scanning pauses during each
  ~2 second broadcast. In testing this improved both range and reliability.

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
