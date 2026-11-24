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
- Installs the **MagicBand+ notification**, **charge me reminder** and
  **light show on a schedule** blueprints and keeps them up to date.
- Plays the readers' **light shows** (`magicband.play_show`).
- Per band: an **access schedule** (time window, days, expiry) and a **band
  type** (MagicBand+ or standard MagicBand). Per person: a **welcome
  colour** for the ring and their MagicBand+.
- **Enrolment**, **tap history**, MagicBand+ **battery** levels with charge
  reminders, and problems (a reader offline, a list it rejected, a low
  battery) in **Settings → Repairs**.
- A **MagicbHAnds** sidebar page for administrators.

Example: Nana isn't a Home Assistant user, so she's just "Nana" with one band.
Morgan is linked to `person.morgan` and has two bands, "blue" and "plus".

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
   person**: leave it empty for visitors like Nana, set it for Morgan.

Within a couple of seconds every reader gets the updated list, and the next
tap is welcomed.

**Several bands for one person?** Use **Enrol bands** next to their name on
the MagicbHAnds page (or `magicband.enrol`): for the next 5 minutes (up to
15) every band tapped that nobody owns becomes theirs. Bands that already
belong to someone are never taken.

### Guests

Tick **Guest** when adding someone on the MagicbHAnds page (or
`magicband.add_person` with `guest: true`), enrol their band, then open
**Access** under their name to set the pass:

- **Pass starts** and **Pass ends**: their bands work only between these
  (either can be empty);
- **Uses left**: how many welcomed taps the pass has (empty: no limit). Each
  welcome uses one; at 0 the band is taken off the readers' lists;
- **Each day** from–until and **On** (weekdays): a daily window, e.g. a dog
  walker on Mon/Wed/Fri 11:00–14:00.

The same with `magicband.set_guest_pass`. The pass is on the person, so it
covers every band they're given (each band's own access schedule still
applies too). Uses are counted by Home Assistant as taps arrive; a reader
that's cut off from Home Assistant keeps its last list, so a pass can go a
tap or two over while it's offline. Guests don't get a tap passport. Turning
**Guest** off removes the pass.

### Lockdown

The **Lockdown** card at the top of **People and access** (or
`magicband.set_settings`) locks the house down so that only the people marked
**Gets in during lockdown** (in **Access** under their name) are let in. It applies:

- **Lockdown now**: by hand;
- **When nobody's home**: while `zone.home` counts nobody home (the people
  tracked by Home Assistant);
- **At night**: between two times (default 23:00–06:00);
- **While an alarm is armed**: while the alarm panel you pick is armed (any
  armed mode) or triggered.

The readers' lists change within a few seconds of somebody leaving, coming
home or the alarm changing, and within a minute of the night hours starting
or ending. **Lockdown** (`binary_sensor.magicbhands_lockdown`) is on during
lockdown; its `reasons` attribute says why. With nobody marked, nobody gets
in during lockdown.

Up to **100 unassigned bands** are kept: beyond that, the longest-unseen
ones without an owner or nickname are dropped (tap one again to bring it
back). Only real NFC IDs (4, 7 or 10 bytes) are recorded, so the reader's
**Test welcome** never shows up as a band.

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
everything, read live from Home Assistant. A row of chips under the header
jumps to each section, and a status strip lists problems first (a reader
offline, its list not applied, locked out or not paired, lockdown on, a band
battery at 20% or less), above the totals (click one to jump to it).

- **Needs attention** (only when there's something): **New bands to
  assign** (a band nobody owns yet, tapped on a reader: pick who it's for, or
  add them, and give it a nickname), **Link Bluetooth to a band** (join a
  MagicBand+'s Bluetooth side to its NFC side; **Wake bands** makes bands
  advertise), **Which kind of band?** (MagicBand+ or standard), and reader
  problems and low batteries, with what to do.
- **Recent taps:** the last 300 taps, 10 at a time (**Newer** and **Older**
  page through them), let in, turned away or enrolled (administrators only).
  Hover a time for the full date. A turned-away band nobody owns has
  **Assign…**, which jumps to it under New bands.
- **People and access:** **Lockdown** first, then who the readers let in,
  one card per person (a row on a computer, stacked on a phone). Each has a
  one-line access summary; **Access** has Allowed, Gets in
  during lockdown, Guest and the guest pass; **Welcome and birthday** has the
  person's **welcome colour** (the readers welcome their bands in it, on the
  ring and on their MagicBand+), welcome sound and birthday. **Enrol bands**:
  the next bands tapped that nobody owns become theirs (a banner shows the
  time left and a Stop button).
- **Bands:** owner, NFC ID, type, last tap, nearby, battery and closest
  bridge (a standard MagicBand has no Bluetooth, so it shows none of those).
  **Group by** person, band type, where (closest bridge), nearby or
  away, battery, the reader it was last tapped on, allowed in, or whether its
  Bluetooth is linked. **Sort by** owner, name, last tap, last heard, battery
  (lowest first), most taps or signal. A search box finds a band by name,
  owner, nickname or ID. Grouping and sorting are remembered in that browser.
  Each band's **Manage** also sets its **own hours**: a daily time window
  (an end earlier than the start means overnight), days of the week and an
  expiry date; the card shows the rule ("07:00–21:00, Mo Tu We Th Fr, until
  24 Dec"). A guest's pass applies on top. Each MagicBand+ shows a 7-day
  battery sparkline; click it for a larger 7- or 30-day chart (current level,
  lowest, last charged).
- **Readers:** **Re-send list to readers**, how long camera pictures are kept,
  and the **Ring preview** (LEDs or Diffused) are above the cards. Each card
  has status tags in its title (Online or Offline, Locked out, Night, Not
  paired, Lets every band in), a **live twin of its ring** (the same number
  of LEDs, showing what the real ring shows: idle or night glow, the chase
  while a band is read, the welcome with the person's name, the turned-away
  pulses, the amber offline pulse), whether it has the current allowed list,
  its last band, and the everyday controls (response mode, sound, volume, ring
  light, camera, Test welcome, Play show). **Health** has tiles for Wi-Fi
  strength and network, how long it's been up and why it last restarted, CPU
  temperature, free memory, loop time and IP address (firmware 0.10.5 or
  later), and **Restart**; closed, it shows a one-line summary. The header
  shows the first reader's ring, live (on a phone only the live line: the
  Readers section shows the ring). The **Readers OK** total counts readers
  that are online, have the list, are paired and aren't locked out. (A page that embeds this one can put
  its own emblem in the middle of the twin by setting
  `window.MBH_READER_EMBLEM` to SVG drawn in a 100 × 100 box.)
  **Ring and tap settings** has the reader's settings in groups: Waiting for a
  band, Night (set hours or sunset to sunrise, with tonight's times in the
  reader's own **Time zone** setting), Reading
  a band, Welcome (with a picture of its shape, Light up MagicBand+ and Band
  light-up power), Denied, Refused-tap lockout, Shows, and Hardware (ring
  type, LED count, colour order, max brightness: these restart the reader,
  so a change there has to be made twice). They're the same settings as on
  the reader's device page; see [reader.md](reader.md) for what each does.
- **Camera (optional):** each reader card has a **Camera** choice. Pick a
  camera that sees the reader (a Ring doorbell's live view works) and every
  tap on that reader saves a picture, shown in **Recent taps**. Leave it on
  **No camera** if you don't have one. Pictures are kept for 30 days
  (above the reader cards, or Configure → Settings), in
  `magicbhands_snapshots` in the config folder, and only administrators can
  see them.
- **Bridges and band effects:** each bridge's fast mode, Bluetooth proxy,
  **Wake bands**, **Ping** and health tiles. **Send to every band in range**,
  through the bridges: one-tap buttons (colours, rainbow, colour cycle,
  lightning, spin and buzz, buzz, stop), and **More: build your own**: one,
  two or five colours, a fade between two colours, a spinning circle, any
  colour from a picker, any of the firmware's light shows, or a buzz on its
  own. Set how hard it buzzes, how long it stays lit, which LEDs, the
  fade-out, and whether it stays on until you send Stop. **Through** sends it
  through every bridge (the whole house) or just one, which reaches only the
  bands near that bridge.
- **Celebrations and tap passport:** holiday and birthday shows after a
  welcome, and everyone's taps, streaks and stamps (the stamps they have,
  the next tap-count stamp, and all 16 in a fold-out).

The page is for Home Assistant **administrators** (it manages who the
readers let in).

**Light shows:** `magicband.play_show` plays one of the readers' 17 light
shows (`show`, or `Random`) on every reader or the ones you pick
(`device_id`), and the blueprint **MagicbHAnds: light show on a schedule**
plays one every hour (or every few hours) between two times of day:
Settings → Automations & scenes → Blueprints → *MagicbHAnds: light show on a
schedule* → Create automation.

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

The integration installs three blueprints for you:

- **MagicBand+ notification**: light up and buzz bands when something
  happens.
- **MagicbHAnds: charge me reminder**: a phone notification when a MagicBand+
  battery drops to the reminder level (see [Charge reminders](#charge-reminders)).
- **MagicbHAnds: light show on a schedule**: plays one of the readers' light
  shows every hour or every few hours between two times of day (see
  [Light shows](#management-page) above).

They go in `blueprints/automation/magicband/`, or, if you'd already imported
one from GitHub, that copy is updated in place. Each integration update
refreshes them and reloads automations, so you never need to re-import them.

## Celebrations and the tap passport

After a welcome, the reader plays one show (reader firmware 0.10.24 or
later). MagicbHAnds sends it once the reader's own **Band scan** event says
it welcomed the band, so a tap the reader turned away never gets a show:

1. **Stamp**, if the tap earned a passport badge;
2. **Birthday**, on the person's birthday (set it under their name, in **Welcome
   and birthday**, or `update_person` with `birthday: "07-14"`);
3. the day's holiday show: New Year (31 Dec and 1 Jan), Valentine, St
   Patrick, Easter, Stars and Stripes (Memorial Day, Independence Day, Labor
   Day, Veterans Day), Halloween, Thanksgiving, Hanukkah (all eight days) and
   Christmas (24 and 25 Dec).

Each can be turned off in the **Celebrations and tap passport** section. The **Coming up**
buttons preview a show on the reader. `magicband.play_show` with
`show: Today` plays today's holiday show (or a random everyday one), which
the light-show blueprint offers too.

The **tap passport** counts every welcomed tap per person (not guests): taps,
days, the current and best streak of days in a row, and 16 stamps: First
tap; 10, 50, 100, 250, 500 and 1,000 taps; Early bird (4–7 am); Night owl
(after 10 pm); Weekender (Saturday and the Sunday after); 7- and 30-day
streaks; Holiday tap and Holiday hopper (5 different holidays); Birthday tap
and Four seasons. A new stamp fires **`magicband_badge`** (`person`,
`person_id`, `ha_person`, `badge`, `name`, `how`, `icon`), shows next to the
tap in **Recent taps**, and plays the Stamp show. Passports are kept in
`.storage/magicband.passport`; removing a person removes theirs.

### Welcome sounds

Each person can have their own welcome sound. Open **People → Welcome and
birthday** under their name, choose **Upload…** and pick an MP3,
WAV, FLAC or Ogg file (up to 2 MB; a few seconds is best). **Play here**
plays it in the browser, **Play on readers** on every reader's speaker, and
**Remove** goes back to the reader's tap-in sound.

When a reader welcomes one of that person's bands it plays their sound
instead of its tap-in sound. The file stays in Home Assistant
(`<config>/magicbhands_sounds/`, not the public `www` folder). The readers
only learn which bands have a sound of their own (reader firmware 0.10.26 or
later); when one of them welcomes such a band, Home Assistant plays the
sound on that reader's speaker through a link that works for a few minutes.
So a welcome sound needs Home Assistant running; Home Assistant plays it as
soon as it's back (even before it has sent the reader its list again), and
while the reader can't reach Home Assistant it plays its own tap-in sound
(reader firmware that does so). The reader's **Sound** switch and its **Sound
at night** setting still apply. A reader holds about 106 bands with a sound
of their own and welcome colours for about 180 bands: past that, Home
Assistant sends what fits and a repair names the reader; the bands left out
get the reader's tap-in sound or Welcome colour.

When Home Assistant is connected but can't play someone's sound, the reader
would stay silent for them, so MagicbHAnds hands the sound back to the
reader where it can:

- **The sound file is missing, or playing it fails** (a media or network
  error): that welcome is silent, the failure is logged,
  and that person's bands come off the readers' list straight away, so the
  readers play their own tap-in sound for them from the next tap. Uploading
  the sound again (or **Play on readers** working again) puts them back.
- **MagicbHAnds is disabled, removed or reloaded**: the readers that are
  online get an empty list first, so they play their tap-in sound for every
  band (a reload sends the list again straight away). Not when Home Assistant
  is only restarting: the readers keep the list and Home Assistant plays the
  sounds again once it's back.
- **A reader is released** (`magicband.unpair_reader`): it gets an empty list
  before it's released.

Still silent: a reader whose speaker entity is missing or disabled in Home
Assistant (fix the entity); a reader that is offline when MagicbHAnds is removed keeps its
last list until it's re-flashed or set up with MagicbHAnds again; and
during an ordinary restart of Home Assistant, a band tapped after the reader
has reconnected but before MagicbHAnds has loaded, or a welcome whose
**Band scan** arrives more than 15 seconds late, gets no sound.

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
  reader_device_id: ...     # match readers by this, not by name
  name: Morgan's MagicBand  # the band's name as shown in Home Assistant
  enrolled: false           # true if this tap enrolled the band
  celebration: Halloween    # the show played after the welcome, or null
  badges: []                # passport stamps this tap earned
```

`allowed` is Home Assistant's own decision: the owner is allowed in, their
guest pass and the band's access schedule (if any) allow it now, and the
house isn't in lockdown (or they get in during lockdown). Taps also appear in the
**logbook** ("Morgan's MagicBand: welcomed at Lounge reader").

Two more events:

- **`magicband_enrolled`** (`band`, `person`, `count`): a band was given to
  someone during enrolment.
- **`magicband_battery_low`** (`bluetooth_band`, `name`, `person`, `battery`):
  a MagicBand+ dropped to the reminder level.
- **`magicband_lockout`** (`reader`, `reader_device_id`, `locked`): a reader's
  **Refused-tap lockout** started (`locked: true`) or ended. A notification
  shows in Home Assistant while it lasts (it goes when the reader reports it
  isn't locked out, also after the reader restarts); use the event to send one
  to your phone as well. A lockout that started or ended while the reader was
  cut off from Home Assistant (a restart or Wi-Fi drop) is announced when it
  reconnects; one that was already announced before it dropped isn't
  announced again. (Right after Home Assistant or MagicbHAnds starts, the
  first state a reader reports is taken as it is, without an event.)

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

Actions that change who's allowed in, or list band IDs, need a Home Assistant
**administrator**: `add_person`, `update_person`, `remove_person`,
`assign_band`, `unassign_band`, `remove_band`, `set_band_access`, `enrol`,
`stop_enrolment`, `set_guest_pass`, `set_settings`, `list`, `history`, `play_welcome_sound`, `link_bluetooth`, `unlink_bluetooth`,
`forget_bluetooth`, `list_bluetooth_bands` and `list_heard`. `send`, `sync`, `play_show` and `list_bridges` work for any user; `send`
only targets MagicBand bridges, and `play_show` only plays a light show. See [security.md](security.md).

| Action | Fields |
|---|---|
| `magicband.add_person` | `name`, `ha_person` (optional), `allowed`, `welcome_colour` (optional), `guest` (default false) |
| `magicband.update_person` | `person` (name or ID), `name`, `ha_person` (empty to unlink), `allowed`, `welcome_colour` (one of White, Warm white, Red, Orange, Yellow, Green, Cyan, Blue, Purple, Pink, Magenta; empty for the reader's own), `birthday` (`MM-DD`, empty to clear), `lockdown_exempt` (gets in during lockdown), `guest` (off removes the pass) |
| `magicband.set_guest_pass` | `person`, `starts` and `ends` (date and time), `uses` (welcomed taps left; empty = no limit), `from` and `until` (daily window), `days`, or `clear: true`. Makes the person a guest |
| `magicband.set_settings` | `lockdown`, `lockdown_away`, `lockdown_night`, `lockdown_from`, `lockdown_until`, `lockdown_alarm` (an alarm panel, empty for none), `holiday_shows`, `birthday_shows`, `passport`, `passport_shows`. Returns the settings and the current lockdown reasons |
| `magicband.remove_person` | `person` |
| `magicband.assign_band` | `band` (ID or `last`), `person`, `label` |
| `magicband.unassign_band` | `band` |
| `magicband.remove_band` | `band` |
| `magicband.set_band_access` | `band`, `from` and `until` (a daily window; `until` earlier than `from` means overnight), `days` (`mon` … `sun`; empty = every day), `expires` (date and time), or `clear: true` to remove every limit |
| `magicband.enrol` | `person`, `minutes` (1–15, default 5), `label` (optional; numbered per band): the next bands tapped that nobody owns become theirs |
| `magicband.stop_enrolment` | Ends enrolment now |
| `magicband.history` | `count` (up to 300, default 50): returns the latest taps, newest first |
| `magicband.sync` | Push the allowed list to all readers now. Returns `readers`, `applied` and `failed` (readers that refused it; from 0.10.4 a reader replies whether it stored the list) |
| `magicband.list` | Returns all people (with welcome colours, birthdays, guest passes, whether they'd get in now, and their passport) and bands (with access schedules), the readers' status, any enrolment, the welcome colours, the house settings, the lockdown reasons, today's holidays and birthdays, and the next holidays |
| `magicband.send` | Sends an effect through the bridges (see above) |
| `magicband.play_show` | `show` (one of the 28 shows; `Random`, the default, for an everyday one; `Today` for today's holiday show), `device_id` (readers; empty = all): plays it on the ring (reader firmware 0.10.17 or later; the celebration shows and Stamp 0.10.24). Returns `played`, `skipped` and `show` |
| `magicband.play_welcome_sound` | `person`, `device_id` (readers; empty = all): plays the person's own welcome sound on the readers' speakers, to try it out (even with the reader's sound off). Returns `played` and `skipped` |
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
restart. At most 25 Bluetooth bands that aren't linked or owned are kept
(the longest-unheard are dropped first).

### Charge reminders

When a MagicBand+ drops to the reminder level (**Configure → Settings →
Charge reminder at (%)**, default 20 %, 0 = off):

- it shows in **Settings → Repairs** ("Morgan's MagicBand+ needs charging"),
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
  (they hold 213 bands), and a reader offline for 15 minutes. Pairing (reader
  firmware 0.10.20+) adds **Tap a band on … to pair it**, shown only while
  MagicbHAnds' own pairing request waits on the reader (at most 2 minutes;
  it goes as soon as the reader says it's paired, and comes back when
  MagicbHAnds asks again), **Another pairing request is waiting** (don't tap),
  and **… is paired with someone else's key** if the tap paired the reader
  with another key (release it there, or erase it over USB; see
  [reader.md](reader.md#pairing-with-magicbhands)). A reader's repairs go
  when it is removed or released. A reader that
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
