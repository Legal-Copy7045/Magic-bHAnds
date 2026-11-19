# Ideas for later

Parked until the reader build is finished. Not started.

## Managing bands

- **Phone notification with owner buttons.** Tapping an unknown band sends
  "New band 04-A9-…: whose is it?" with a button for each person (and
  *Ignore*); one press assigns it. The same for "which Bluetooth band is
  this?" when pairing can't tell.
- *Done:* the ready-made dashboard (`homeassistant/dashboards/magicband.yaml`),
  the MagicbHAnds sidebar page, and enrolment (which covers adding a
  person's bands quickly).
- **Hide band IDs from users who aren't administrators** (the page would read
  full IDs from the admin-only `list`; Home Assistant's own tag entities
  would still show them).
- **Per-reader access:** choose which readers each person's band opens.
- **A built-in second check for doors** ("only if someone's home", "only in
  daylight", "confirm on my phone") on the tap event.

## Bluetooth

- **Name bands in Home Assistant's Bluetooth visualization** by attaching
  each beacon's current (rotating) address to the band's device.
  Unconfirmed whether the visualization uses device connections.
- **Read the MagicBand+ FCC filing** (fccid.io, FCC ID 2AYEL-7282) for the
  radio details (advertising interval, chipset). Needs fccid.io allowed in
  the environment's network settings.

## Reader

- **Sound level:** if it's too quiet at 100 % on the proper 5 V supply,
  normalise the sound files, and check whether ESPHome's mono output halves
  the level.

## Hardware

- **Custom PCB:** an early design exists in the git history (release
  v0.9.2 and earlier). It needs redoing for the ring-only design once the
  compact build is proven.
