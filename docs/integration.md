# MagicbHAnds integration (HACS)

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
Jackie is linked to `person.jackie` and has two bands, "blue" and "plus".

## Install

1. In **HACS**, open the **⋮** menu, choose **Custom repositories**, add
   `https://github.com/Legal-Copy7045/Magic-bHAnds` with type **Integration**,
   then install **MagicbHAnds** and restart Home Assistant.
2. **Settings → Devices & services → Add integration → MagicbHAnds.**
3. **For each MagicBand reader:** leave **Allow the device to perform Home
   Assistant actions** (ESPHome → the reader → Configure) **off**. Tag scans
   reach Home Assistant without it, and with it on, a tampered reader could
   call any action (see [security.md](security.md)).

Readers are found automatically: any ESPHome device built from
`esphome/magicband-reader.yaml`. Firmware 0.10.4 or later is needed for
welcome colours and for the reader to confirm it applied the allowed list
(older firmware shows **Sent (update the reader to confirm)**).

## Adding people and bands

1. **Tap the band** on any reader. It's denied, and a notification says an
   unknown band was tapped.
2. Open **Settings → Devices & services → MagicbHAnds → Configure → Add or
   assign a band.**
3. Choose the band (the latest unknown one is preselected), choose who it
   belongs to, or **➕ New person…**, and optionally label it ("blue band").
4. For a new person, enter their name. Optionally link a **Home Assistant
   person**: leave it empty for visitors like Nana, set it for Jackie.

Within a couple of seconds every reader gets the updated list, and the next
tap is welcomed.

**Several bands for one person?** Use **Enrol bands** next to their name on
the MagicbHAnds page (or `magicband.enrol`): for the next 5 minutes (up to
15) every band tapped that nobody owns becomes theirs. Bands that already
belong to someone are never taken.

The **Configure** menu also has **Add a person**, **Edit a person** (rename,
link or unlink an HA person, or turn **Allowed in** off to block all their
bands), **Link a band's Bluetooth**, **Remove a band**, **Remove a person**
and **Settings** (show the page in the sidebar; **Charge reminder at (%)**,
default 20, 0 = off). Removing a person keeps their bands but unassigns them,
so they're denied. A person's **welcome colour** and a band's **access
schedule** are set on the MagicbHAnds page (or with `update_person` and
`set_band_access`), not in Configure.

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
| `sensor.<band>_last_tap` | NFC side: when it was last tapped on a reader; attributes: NFC ID, label, person, HA person, allowed, reader, scans, first seen, linked Bluetooth band, band type |
| `select.<band>_band_type` | NFC side: **MagicBand+** (has Bluetooth), **Standard MagicBand** (NFC only) or **Not known yet**. Linking its Bluetooth makes it a MagicBand+ on its own; set the rest yourself (see [Bands over Bluetooth](#bands-over-bluetooth)) |
| `binary_sensor.<band>_nearby` | On while its beacon is heard; off after 35 minutes without one (two missed beacons) |
| `sensor.<band>_last_seen` | When its beacon was last heard; attributes: person, NFC band, which adapter heard it, beacon count, raw payload |
| `sensor.<band>_heard_by` | Which bridge, proxy or adapter heard its latest beacon, by its Home Assistant device name (e.g. "Kitchen MagicBand Bridge"); rename the device to change it |
| `sensor.<band>_closest` | The bridge, proxy or adapter that heard it strongest in the last 20 minutes: a rough "which room"; attributes list every one that heard it, strongest first |
| `sensor.<band>_signal` | Signal strength of the last beacon, and per adapter or proxy (diagnostic) |
| `sensor.<band>_battery` | Battery level in %, from its beacon, in steps (5, 15, 50, 60, 72, 80, 98, 100). A battery sensor, so it works in battery views and low-battery automations |

**On each reader's own device page** the integration adds:

| Entity | |
|---|---|
| **Last band name** | Whose band was last tapped on this reader (the name, not the ID); attributes: band ID, person, allowed, when |
| **Allowed list** (diagnostic) | Whether this reader has the current allowed list: *Up to date*, *Not applied* (the reader rejected it; the reason is in the `error` attribute and in Repairs), *Sent (update the reader to confirm)* (firmware before 0.10.4), *Reader offline* or *Waiting*; attributes: last sync, number of bands, whether it takes welcome colours |

## Management page

MagicbHAnds adds a **MagicbHAnds** entry to the sidebar: one page for
everything, read live from Home Assistant.

- **New bands to assign:** a band nobody owns yet, tapped on a reader. Pick
  who it's for (or add them) and give it a nickname.
- **Link Bluetooth to a band:** join a MagicBand+'s Bluetooth side to its NFC
  side.
- **Bands:** owner, NFC ID, type, last tap, nearby, battery and closest
  bridge. **Group by** person, band type, where (closest bridge), nearby or
  away, battery, the reader it was last tapped on, allowed in, or whether its
  Bluetooth is linked. **Sort by** owner, name, last tap, last heard, battery
  (lowest first), most taps or signal. A search box finds a band by name,
  owner, nickname or ID. Grouping and sorting are remembered in that browser.
- **Send to every band in range**, through the bridges: one-tap buttons
  (wake, ping, colours, rainbow, colour cycle, lightning, spin and buzz, buzz,
  stop), and **More: build your own**: one, two or five colours, a fade
  between two colours, a spinning circle, any colour from a picker, any of the
  firmware's light shows, or a buzz on its own. Set how hard it buzzes, how
  long it stays lit, which LEDs, the fade-out, and whether it stays on until
  you send Stop. **Through** sends it through every bridge (the whole house)
  or just one, which reaches only the bands near that bridge.
  Each band's **Manage** also sets its **access**: a daily time window
  (an end earlier than the start means overnight), days of the week and an
  expiry date; the card shows the rule ("07:00–21:00, Mo Tu We Th Fr, until
  24 Dec"). Each MagicBand+ shows a 7-day battery sparkline.
- **People:** who the readers let in, each person's **welcome colour** (the
  readers welcome their bands in it, on the ring and on their MagicBand+),
  and **Enrol bands** (the next bands tapped that nobody owns become theirs;
  a banner shows the time left and a Stop button).
- **Recent taps:** the last 30 taps, welcomed, denied or enrolled
  (administrators only).
- **Readers** and **bridges:** status, firmware and their settings (fast mode,
  Bluetooth proxy, response mode, sound, ring and so on). Each reader's
  **Health** line shows whether it has the current allowed list, whether it's
  offline, and whether a firmware update is waiting.

The page is for Home Assistant **administrators** (it manages who the
readers let in).

It finds everything by device and attribute, so new bands, readers and
bridges appear by themselves. Changes go through the integration's own
actions.

To hide the sidebar entry (for example, if you show the page inside your own
set of dashboards): **Configure → Settings → Show MagicbHAnds in the
sidebar**. The page itself is `custom_components/magicband/frontend/page.html`.

A simpler version built from Home Assistant's own cards is in
[`homeassistant/dashboards/magicband.yaml`](../homeassistant/dashboards/magicband.yaml),
if you'd rather have a normal dashboard.

## Sending effects from automations

Use **`magicband.send`**. It finds every MagicBand bridge itself (any ESPHome
device with a MagicBand light and a Command entity), so you don't need any
scripts or templates.

```yaml
action: magicband.send
data:
  effect: color          # color, rgb, dual_color, five_color, crossfade,
                         # circle, animation, buzz, ping, wake, "off", raw, stop
  color: red
  vibration: 1           # 0 = none, 1–11 = patterns
  always_on: true
```

- `bridges`: list of bridge Command entities to use. Leave it out for all
  bridges.
- `effect: "off"` must be **quoted** in YAML. A bare `off` means false.
- Other fields: `color2`, `colors`, `rgb_color`, `animation`, `leds`,
  `on_seconds`, `fade_seconds`, `flash`, `fast`, `seconds` (for `wake`),
  `hex`, `duration_ms`, or `command` for a raw command object (with the same
  time limits). They're all in the action editor with descriptions.
- At most 30 commands a minute go to each bridge; a bridge broadcasts one
  command for at most 60 seconds.
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

## The blueprints

The integration installs two blueprints for you:

- **MagicBand+ notification**: light up and buzz bands when something
  happens.
- **MagicbHAnds: charge me reminder**: a phone notification when a MagicBand+
  battery drops to the reminder level (see [Charge reminders](#charge-reminders)).

They go in `blueprints/automation/magicband/`, or, if you'd already imported
one from GitHub, that copy is updated in place. Each integration update
refreshes them and reloads automations, so you never need to re-import them.

## Reacting to taps

Every tap on a reader fires a **`magicband_tap`** event:

```yaml
event_type: magicband_tap
data:
  band: 04-53-65-2A-C0-5F-80
  label: blue
  person: Jackie            # null for unknown bands
  person_id: 3f2c1a9b8d7e
  ha_person: person.jackie  # null if not linked (e.g. Nana)
  allowed: true
  known: true
  reader: Lounge reader
  reader_device_id: ...     # match readers by this, not by name
  name: Jackie's MagicBand  # the band's name as shown in Home Assistant
  enrolled: false           # true if this tap enrolled the band
```

`allowed` is Home Assistant's own decision: the owner is allowed in and the
band's access schedule (if any) allows it now. Taps also appear in the
**logbook** ("Jackie's MagicBand: welcomed at Lounge reader").

Two more events:

- **`magicband_enrolled`** (`band`, `person`, `count`): a band was given to
  someone during enrolment.
- **`magicband_battery_low`** (`bluetooth_band`, `name`, `person`, `battery`):
  a MagicBand+ dropped to the reminder level.

Example: welcome Jackie by name.

```yaml
alias: "Jackie tapped in"
triggers:
  - trigger: event
    event_type: magicband_tap
    event_data:
      person: Jackie
      allowed: true
actions:
  - action: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.magicband_reader_speaker
      message: "Welcome home, Jackie!"
```

## Actions

Actions that change who's allowed in, or list band IDs, need a Home Assistant
**administrator**: `add_person`, `update_person`, `remove_person`,
`assign_band`, `unassign_band`, `remove_band`, `set_band_access`, `enrol`,
`stop_enrolment`, `list`, `history`, `link_bluetooth`, `unlink_bluetooth`,
`forget_bluetooth`, `list_bluetooth_bands` and `list_heard`. `send`, `sync` and `list_bridges` work for any user; `send`
only targets MagicBand bridges. See [security.md](security.md).

| Action | Fields |
|---|---|
| `magicband.add_person` | `name`, `ha_person` (optional), `allowed`, `welcome_colour` (optional) |
| `magicband.update_person` | `person` (name or ID), `name`, `ha_person` (empty to unlink), `allowed`, `welcome_colour` (one of White, Warm white, Red, Orange, Yellow, Green, Cyan, Blue, Purple, Pink, Magenta; empty for the reader's own) |
| `magicband.remove_person` | `person` |
| `magicband.assign_band` | `band` (ID or `last`), `person`, `label` |
| `magicband.unassign_band` | `band` |
| `magicband.remove_band` | `band` |
| `magicband.set_band_access` | `band`, `from` and `until` (a daily window; `until` earlier than `from` means overnight), `days` (`mon` … `sun`; empty = every day), `expires` (date and time), or `clear: true` to remove every limit |
| `magicband.enrol` | `person`, `minutes` (1–15, default 5), `label` (optional; numbered per band): the next bands tapped that nobody owns become theirs |
| `magicband.stop_enrolment` | Ends enrolment now |
| `magicband.history` | `count` (up to 300, default 50): returns the latest taps, newest first |
| `magicband.sync` | Push the allowed list to all readers now. Returns `readers`, `applied` and `failed` (readers that refused it; from 0.10.4 a reader replies whether it stored the list) |
| `magicband.list` | Returns all people (with welcome colours) and bands (with access schedules), the readers' status, any enrolment, and the welcome colours |
| `magicband.send` | Sends an effect through the bridges (see above) |
| `magicband.list_bridges` | Returns every bridge's Command entity |
| `magicband.list_heard` | Returns recent MagicBand+ Bluetooth traffic heard (last 30), and the last 200 band messages |
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
  linked and a notification says so (unlink it if it's wrong). Otherwise a
  notification asks you to link it by hand. Automatic linking never changes
  who a band belongs to: if the Bluetooth band was given to someone and the
  NFC band isn't theirs, nothing is linked and a notification asks you to
  confirm by linking by hand.
- **By hand:** **Configure → Link a band's Bluetooth**, or
  `magicband.link_bluetooth`. To tell two bands apart, put one in a metal
  tin (or out of range) for half an hour: the one still nearby is the other.

Linking by hand passes ownership across: if the NFC band doesn't belong to anyone yet, it takes the Bluetooth band's owner (and is allowed in if they are); if it already has an owner, that owner is kept. Linking merges the two sides into one device: the Bluetooth entities move
onto the band's device, and the Bluetooth-only device disappears.
Unlinking splits them again. `magicband.list` also shows each band's
Bluetooth side (nearby, battery, signal).
Each beacon also fires a `magicband_band_seen` event with `bluetooth_band`,
`name`, `person`, `band`, `battery`, `level`, `rssi`, `heard_by` and `new`.

**Standard MagicBands** (the original, NFC-only bands) have no Bluetooth,
so they'll never be heard. Set their **Band type** to *Standard MagicBand*
(on the band's device page, or with the buttons in the management page's
*Link Bluetooth to a band* box). Then:

- tapping one no longer starts listening for its Bluetooth, so it can't be
  linked by mistake to a MagicBand+ that happens to be nearby;
- the management page stops listing it as "not heard over Bluetooth yet".

A band whose Bluetooth gets linked becomes a *MagicBand+*, even if it was
marked standard. Bands that are neither linked nor marked show *Not known
yet*.

**Range:** "nearby" means within range of a Bluetooth adapter or proxy that
Home Assistant uses. Adding proxies (any bridge's **Bluetooth proxy**
switch) extends it. Beacons are stored, so presence and history survive a
restart.

### Charge reminders

When a MagicBand+ drops to the reminder level (**Configure → Settings →
Charge reminder at (%)**, default 20 %, 0 = off):

- it shows in **Settings → Repairs** ("Jackie's MagicBand+ needs charging"),
  and clears itself once the band has been charged;
- a **`magicband_battery_low`** event fires, once per discharge.

For a phone notification, create an automation from the **MagicbHAnds:
charge me reminder** blueprint and pick your phone (optionally only one
person's bands).

**Help work out the rest:** `magicband.list_bluetooth_bands` returns each
band's last 50 raw beacons, the history of its level byte and which bits
change. Charging a band fully and checking whether its **Battery** goes
back to 100 confirmed the battery reading.

## How it fits with the reader

- The integration is the **source of truth**. Each sync replaces the reader's
  own list, so manage bands here rather than with the reader's **Allow last
  band** button.
- Readers get the list (and the welcome colours) when they connect to Home
  Assistant, after every change, every 10 minutes, and within a minute of a
  band's access schedule opening or closing.
- Each reader replies whether it applied the list (firmware 0.10.4+). Its
  **Allowed list** sensor shows the result, and problems show in **Settings →
  Repairs**: a reader that rejected the list, a list too long for the readers
  (they hold 213 bands), and a reader offline for 15 minutes. A reader that
  can't apply a list empties its own list (denies every band) rather than
  keep an old one.
- Keep the reader's **Response mode** on **Known bands only** (the default).
  Welcome or deny is then decided on the reader, using the synced list.
- Data is stored in Home Assistant's `.storage/magicband.registry` (people
  and bands), `.storage/magicband.bluetooth` (Bluetooth bands) and
  `.storage/magicband.history` (the last 300 taps), all included in HA
  backups.
- **Diagnostics:** Settings → Devices & services → MagicbHAnds → ⋮ →
  **Download diagnostics** gives a summary for troubleshooting, with band IDs
  shortened and people's names replaced.
