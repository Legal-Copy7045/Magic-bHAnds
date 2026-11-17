# MagicBand integration (HACS)

Manages **people** and their **bands** for your MagicBand readers:

- Logs every band tapped on any reader: when, where, and how many times.
- Alerts you when an unknown band is tapped. New bands get the **denied**
  sequence until you allow them.
- Lets you give bands to people. People **don't need to be Home Assistant
  users**, and one person can have **any number of bands**.
- Keeps every reader's allowed list in sync, so readers still answer
  instantly, and keep working if Home Assistant is offline.
- Fires a `magicband_tap` event and keeps a "last tap" sensor per person for
  automations.
- Adds a **Send MagicBand effect** action (`magicband.send`) that lights up or
  buzzes bands through every bridge, or the ones you pick.
- Installs the **MagicBand+ notification** blueprint and keeps it up to date.

Example: Nana isn't a Home Assistant user, so she's just "Nana" with one band.
Morgan is linked to `person.morgan` and has two bands, "blue" and "plus".

## Install

1. In **HACS**, open the **⋮** menu, choose **Custom repositories**, add
   `https://github.com/Legal-Copy7045/Magic-bHAnds` with type **Integration**,
   then install **MagicBand** and restart Home Assistant.
2. **Settings → Devices & services → Add integration → MagicBand.**
3. **For each MagicBand reader:** go to **Settings → Devices & services →
   ESPHome**, find the reader, click **Configure**, and turn on **Allow the
   device to perform Home Assistant actions**. Readers report scans as Home
   Assistant tag scans, which needs this setting.

Readers are found automatically: any ESPHome device built from
`esphome/magicband-reader.yaml` (firmware 0.6.0 or later).

## Adding people and bands

1. **Tap the band** on any reader. It's denied, and a notification says an
   unknown band was tapped.
2. Open **Settings → Devices & services → MagicBand → Configure → Add or
   assign a band.**
3. Choose the band (the latest unknown one is preselected), choose who it
   belongs to, or **➕ New person…**, and optionally label it ("blue band").
4. For a new person, enter their name. Optionally link a **Home Assistant
   person**: leave it empty for visitors like Nana, set it for Morgan.

Within a couple of seconds every reader gets the updated list, and the next
tap is welcomed.

The **Configure** menu also has **Add a person**, **Edit a person** (rename,
link or unlink an HA person, or turn **Allowed in** off to block all their
bands), **Remove a band** and **Remove a person**. Removing a person keeps
their bands but unassigns them, so they're denied.

## Entities

| Entity | |
|---|---|
| `sensor.magicband_last_tap` | Time of the last tap; attributes: band, label, person, HA person, allowed, reader |
| `sensor.magicband_<name>_last_tap` | One per person: when they last tapped any of their bands, plus their band list |
| `sensor.magicband_unknown_bands` | How many bands don't belong to anyone yet, with the most recent in its attributes |
| `sensor.magicband_last_band_heard` | When a MagicBand+ was last heard over Bluetooth; attributes: address, RSSI, which adapter/proxy heard it, payload, seconds after the last send |

**Every band gets its own device**, showing everything known about it. A
band tapped on a reader has its NFC side; a MagicBand+ heard over Bluetooth
has its Bluetooth side; once the two are linked (see
[Bands over Bluetooth](#bands-over-bluetooth)) they're **one device** with
both. It's named after its label or owner ("Nana's MagicBand+"), and its
model shows *MagicBand+* once Bluetooth is linked, *MagicBand* before.

| Entity | |
|---|---|
| `sensor.<band>_last_tap` | NFC side: when it was last tapped on a reader; attributes: NFC ID, label, person, HA person, allowed, reader, scans, first seen, linked Bluetooth band |
| `binary_sensor.<band>_nearby` | On while its beacon is heard; off after 35 minutes without one (two missed beacons) |
| `sensor.<band>_last_seen` | When its beacon was last heard; attributes: person, NFC band, which adapter heard it, beacon count, raw payload |
| `sensor.<band>_heard_by` | Which bridge, proxy or adapter heard its latest beacon, by its Home Assistant device name (e.g. "Kitchen MagicBand Bridge"); rename the device to change it |
| `sensor.<band>_closest` | The bridge, proxy or adapter that heard it strongest in the last 20 minutes: a rough "which room"; attributes list every one that heard it, strongest first |
| `sensor.<band>_signal` | Signal strength of the last beacon, and per adapter or proxy (diagnostic) |
| `sensor.<band>_battery` | Battery level in %, from its beacon, in steps (5, 15, 50, 60, 72, 80, 98, 100). A battery sensor, so it works in battery views and low-battery automations |

## Sending effects from automations

Use **`magicband.send`**. It finds every MagicBand bridge itself (any ESPHome
device with a MagicBand light and a Command entity), so you don't need any
scripts or templates.

```yaml
action: magicband.send
data:
  effect: color          # color, rgb, dual_color, five_color, crossfade,
                         # circle, animation, buzz, ping, "off", raw, stop
  color: red
  vibration: 1           # 0 = none, 1–11 = patterns
  always_on: true
```

- `bridges`: list of bridge Command entities to use. Leave it out for all
  bridges.
- `effect: "off"` must be **quoted** in YAML. A bare `off` means false.
- Other fields: `color2`, `colors`, `rgb_color`, `animation`, `leds`,
  `on_seconds`, `fade_seconds`, `flash`, `fast`, `hex`, `duration_ms`, or
  `command` for a raw command object. They're all in the action editor with
  descriptions.
- `magicband.list_bridges` returns the bridges it found.

Example: flash red three times when your team scores.

```yaml
- repeat:
    count: 3
    sequence:
      - action: magicband.send
        data: {effect: color, color: red, vibration: 1, always_on: true}
      - delay: 2
      - action: magicband.send
        data: {effect: "off"}
      - delay: 2
```

## The blueprint

The integration installs the **MagicBand+ notification** blueprint for you. It
goes in `blueprints/automation/magicband/`, or, if you'd already imported it
from GitHub, it updates that copy in place. Each integration update refreshes
it and reloads automations, so you never need to re-import it.

## Reacting to taps

Every tap on a reader fires a **`magicband_tap`** event:

```yaml
event_type: magicband_tap
data:
  band: 04-53-65-2A-C0-5F-80
  label: blue
  person: Morgan            # null for unknown bands
  person_id: 3f2c1a9b8d7e
  ha_person: person.morgan  # null if not linked (e.g. Nana)
  allowed: true
  known: true
  reader: Lounge reader
  reader_device_id: ...
```

Example: welcome Morgan by name.

```yaml
alias: "Morgan tapped in"
triggers:
  - trigger: event
    event_type: magicband_tap
    event_data:
      person: Morgan
      allowed: true
actions:
  - action: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.magicband_reader_speaker
      message: "Welcome home, Morgan!"
```

## Actions

| Action | Fields |
|---|---|
| `magicband.add_person` | `name`, `ha_person` (optional), `allowed` |
| `magicband.update_person` | `person` (name or ID), `name`, `ha_person` (empty to unlink), `allowed` |
| `magicband.remove_person` | `person` |
| `magicband.assign_band` | `band` (ID or `last`), `person`, `label` |
| `magicband.unassign_band` | `band` |
| `magicband.remove_band` | `band` |
| `magicband.sync` | Push the allowed list to all readers now |
| `magicband.list` | Returns all people and bands |
| `magicband.send` | Sends an effect through the bridges (see above) |
| `magicband.list_bridges` | Returns every bridge's Command entity |
| `magicband.list_heard` | Returns recent MagicBand+ Bluetooth traffic heard (last 30) |
| `magicband.list_bluetooth_bands` | Returns every MagicBand+ recognised over Bluetooth, with its battery history, signal per adapter, changing bits and last 50 raw beacons |
| `magicband.link_bluetooth` | `bluetooth_band` (ID, first characters, name or `last`), and `band` (NFC ID or `last`) or `person` |
| `magicband.unlink_bluetooth` | `bluetooth_band` |
| `magicband.forget_bluetooth` | `bluetooth_band`: deletes it and its entities |

For example, "allow whoever just tapped as Nana":

```yaml
action: magicband.assign_band
data:
  band: last
  person: Nana
```

## Hearing bands respond

The integration listens through Home Assistant's own Bluetooth: any
Bluetooth adapter on the Home Assistant machine, and every Bluetooth proxy
(the SCREEK BP2-POE, or a bridge with its **Bluetooth proxy** switch on). It
picks up every advertisement carrying Disney's company ID (`0x0183`) and
sorts it into:

- **command:** an effect or ping, i.e. a bridge talking to bands. Shows which
  proxies can hear which bridge, and how strongly.
- **band:** anything else with Disney's ID, e.g. a band answering a ping.

Each one fires a `magicband_heard` event with `address`, `name`, `rssi`,
`source` (the adapter or proxy that heard it), `payload`, `kind`,
`after_send` (seconds since the last `magicband.send`) and `likely_response`
(a band heard within 15 s of a send). Bands are logged at info level, and
commands at debug level:

```yaml
logger:
  logs:
    custom_components.magicband.listener: debug
```

To see it all, send **Ping** (or `magicband.send` with `effect: ping`), then
run `magicband.list_heard` in Developer Tools → Actions.

Things to know:
- A bridge doesn't listen while it is broadcasting (scanning pauses for the
  ~2 s burst), so another proxy or adapter hears replies better.
- MagicBand+ may use private Bluetooth addresses that change over time, so one
  band can appear under several addresses.
- Nothing is logged if Home Assistant has no Bluetooth adapter or proxy.

## Bands over Bluetooth

Every MagicBand+ sends a short Bluetooth status beacon about every 15
minutes (details: [protocol.md](protocol.md#band-beacons)). Its Bluetooth
address changes every time, but part of the beacon stays the same for each
band, so the integration recognises each band and gives it a device:
**Nearby**, **Last seen**, **Signal** and **Battery**.

**Whose band is it?** Each Bluetooth band can be linked to the band's NFC ID
(then it belongs to whoever owns that band), or given to a person directly:

- **Automatically, by tapping:** tap a band on a reader. For the next 20
  minutes (long enough for one beacon) the integration listens for unlinked
  Bluetooth bands. If exactly one is heard, or only one is already given to
  that band's owner, or one is at least 10 dB stronger than the rest, it's
  linked. Otherwise a notification asks you to link it by hand.
- **By hand:** **Configure → Link a band's Bluetooth**, or
  `magicband.link_bluetooth`. To tell two bands apart, put one in a metal
  tin (or out of range) for half an hour: the one still nearby is the other.

Linking merges the two sides into one device: the Bluetooth entities move
onto the band's device, and the Bluetooth-only device disappears.
Unlinking splits them again. `magicband.list` also shows each band's
Bluetooth side (nearby, battery, signal).
Each beacon also fires a `magicband_band_seen` event with `bluetooth_band`,
`name`, `person`, `band`, `battery`, `level`, `rssi`, `heard_by` and `new`.

**Range:** "nearby" means within range of a Bluetooth adapter or proxy that
Home Assistant uses. Adding proxies (any bridge's **Bluetooth proxy**
switch) extends it. Beacons are stored, so presence and history survive a
restart.

**Low battery reminder,** for example:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.morgan_s_magicband_battery
    below: 20
actions:
  - action: notify.notify
    data:
      message: "Morgan's MagicBand+ needs charging"
```

**Help work out the rest:** `magicband.list_bluetooth_bands` returns each
band's last 50 raw beacons, the history of its level byte and which bits
change. Charging a band fully and checking whether its **Battery** goes
back to 100 confirmed the battery reading.

## How it fits with the reader

- The integration is the **source of truth**. Each sync replaces the reader's
  own list, so manage bands here rather than with the reader's **Allow last
  band** button.
- Readers get the list when they connect to Home Assistant, after every
  change, and every 10 minutes.
- Keep the reader's **Response mode** on **Known bands only** (the default).
  Green or red is then decided on the reader, using the synced list.
- Data is stored in Home Assistant's `.storage/magicband.registry`, which is
  included in HA backups.
