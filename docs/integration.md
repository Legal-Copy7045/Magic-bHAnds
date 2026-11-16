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
Jackie is linked to `person.jackie` and has two bands, "blue" and "plus".

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
   person**: leave it empty for visitors like Nana, set it for Jackie.

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
  person: Jackie            # null for unknown bands
  person_id: 3f2c1a9b8d7e
  ha_person: person.jackie  # null if not linked (e.g. Nana)
  allowed: true
  known: true
  reader: Lounge reader
  reader_device_id: ...
```

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

For example, "allow whoever just tapped as Nana":

```yaml
action: magicband.assign_band
data:
  band: last
  person: Nana
```

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
