# Security

What MagicbHAnds protects, what it can't, and what to do about it. The short
version: **a MagicBand's NFC ID and Bluetooth beacon identify a band; they
don't prove it's genuine.** Treat a tap like a cheap RFID fob, not a key.

## What a tap does and doesn't prove

| | Communication | The band itself |
|---|---|---|
| **Reader to Home Assistant** | Encrypted (ESPHome Noise), keyed per device | – |
| **NFC tap** | – | Only the tag's ID. It isn't secret: a phone, Flipper Zero or Proxmark can read it from a few centimetres and copy it to a blank or emulated tag. The band doesn't prove anything cryptographically. |
| **Bluetooth beacon** | – | A fixed pattern broadcast in the clear. Anyone can record it and replay it, so "nearby" and "closest" can be faked. |

So the encrypted link protects *what the reader says*, not *whether the band
on the reader is real*.

### Using it with locks, alarms and presence

- **Door locks:** an allowed tap is as strong as a basic RFID fob. Add a
  second factor for anything that matters, for example: only unlock when a
  household member's phone is home, ask for a confirmation on a phone, or
  use the tap to unlock only during the day. Match the reader by device
  (`trigger.event.data.reader_device_id`), not just by name.
- **Presence:** don't disarm an alarm or unlock anything because a band is
  "nearby" over Bluetooth.
- **The reader is outside the house.** Anyone who opens it can reach its USB
  port and reflash it, and the ESP32 doesn't have secure boot or flash
  encryption turned on, so they could read its Wi-Fi password and its
  Home Assistant key and pretend to be the reader. Keep the electronics
  where they can't be reached (inside the wall or door, with only the antenna
  and ring outside), and decide in Home Assistant, not on the reader. Its
  firmware logs at INFO and never logs band IDs, so the USB port doesn't
  print them, but anyone with the USB port can change its Wi-Fi (Improv),
  which takes it offline.
- **Only MagicBand readers count.** A tap is only accepted from an ESPHome
  device built from the reader firmware, and only those get the allowed list.
  Other integrations (a phone registered with the mobile app, for one) let any
  logged-in user choose a device's model and name, so they can't pose as a
  reader. An ESPHome device you've added that is compromised still could.

## Who can change who's allowed in

Everything that changes access (people, assigning bands, access schedules,
guest passes, lockdown and the other house settings, enrolment, linking
Bluetooth) and the actions that return everything at once
(`list`, `history`, `list_bluetooth_bands`, `list_heard`) need an
**administrator** in Home Assistant, and so does the MagicbHAnds sidebar page. Other users can only:
use the bands (`magicband.send`, at most 30 commands a minute per bridge),
send the readers their allowed list again (`magicband.sync`, at most 6 a
minute; it sends the same list), play a light show on the readers
(`magicband.play_show`, at most 12 a minute per reader; a tap takes over the
ring), and list the bridges. A test checks no other action is open. Each
reader's own `play_show` action, which any user can also call directly, is
limited on the reader as well (12 shows a minute, so MagicbHAnds' own calls
are never dropped).

**Enrolment** (giving the next unknown bands tapped to one person) never lets
the tap that enrols a band in: that tap is reported as not allowed
(`allowed: false`, `enrolled: true`), and only the band's next tap opens
anything. Anyone who taps an unknown band during the window (up to 15
minutes) gets it enrolled, so start enrolment on the reader you're standing
at (the page's **Enrol bands tapped on** choice, or `device_id` on
`magicband.enrol`) rather than on any reader, and stop it when you're done.

**Band IDs are not hidden from other users**, though: entity attributes (the
last-tap sensors, the reader's "Last band ID" and "Last band name"), history,
notifications and Home Assistant's own tag entities show them to every
logged-in user. Only give Home Assistant accounts to people you'd trust with
a copy of the bands.

**Readers are paired with MagicbHAnds** (reader firmware 0.10.20 and
later). The integration gives each reader a secret key the first time it
syncs and keeps it where only administrators can read it. A paired reader
then only takes a new allowed list, welcome colours, or an "Ask Home
Assistant" answer (`set_known_bands`, `set_band_colours`, `accept`, `deny`)
when the key comes with it, and its **Allow last band** button does nothing
(manage bands in MagicbHAnds). So other Home Assistant users, who can call
any ESPHome action, can't add a band to a reader. A paired reader never takes a
different key over the network, not even right after a restart or a power
cut: only the key holder can release it (`magicband.unpair_reader`, to move
it to another Home Assistant; this Home Assistant then leaves it alone until
`magicband.pair_reader` takes it back), or someone with the reader in hand can erase it
over USB (the web installer's **Erase device**) and add it again. The key is in
Home Assistant's backups, so restoring a backup keeps your readers paired. If
you lose it (a fresh install without a backup), erase the reader over USB.
**First pairing needs a tap on the reader**: when MagicbHAnds first pairs
with it, the ring breathes blue and Repairs asks you to tap any band on it
within 2 minutes; the tap finishes pairing (and does nothing else). The first
request wins: while it waits, no other key can replace it, and asking again
with the same key doesn't extend the wait. Once a wait has run out, that key
must leave a 2-minute gap before asking again, so nobody can hold a new
reader's pairing open indefinitely. Any Home Assistant user can call an
unpaired reader's own `pair` action, so someone else could ask first; then
MagicbHAnds' own request is refused and it notices and says so in Repairs:
**don't tap**, wait 2 minutes and sync again. Only a tap while *MagicbHAnds*
asks you to should finish pairing.
The **Paired with MagicbHAnds** sensor on the reader shows its state.

Home Assistant users who aren't administrators can still use the readers'
and bridges' own controls: a reader's **Response mode** (e.g. *Welcome every
band*), the bridges' Command entity and actions, and (on readers that aren't
paired) the readers' ESPHome actions. On a paired reader, **Forget all
bands** and **Forget last band** are ignored (the allowed list only changes
through MagicbHAnds), so nobody can empty it between syncs. The reader's own decision only drives
its lights, sound and its "Band scan" event entity, so **don't open a lock
from the reader's event entity**; use the `magicband_tap` event, whose
`allowed` comes from Home Assistant.

**Bridges limit their own airtime** (firmware 0.10.20 and later), however the
commands arrive (`magicband.send`, the Command entity or the bridge's
actions): they earn half a second of broadcasting for every second, up to
30 seconds, so a stream of commands can't keep a bridge on air and its
Bluetooth proxy keeps scanning at least about half the time.

**Automatic Bluetooth pairing never changes access.** If linking a band would
give an NFC tag a new owner (and so let it in), it's left for an
administrator to confirm.

## Readers' allowed list

The integration sends the allowed list to every reader and each reader
replies whether it applied it. The integration checks each list against the
reader's buffer sizes before sending it: the welcome colours (4,096
characters) and welcome sounds (1,600) send only the entries that fit, and
Repairs names the reader and how many were left out (those bands are welcomed
in the reader's default colour and sound, and still let in). If a reader can't
store the whole allowed list (about 213 bands of 7 bytes) or the list is
malformed, the reader **empties** its
list (denies everyone) rather than keep an old one, and it shows in
**Settings → Repairs** ("<reader> didn't take the allowed list", or "Too many
allowed bands for the readers"). A reader that's offline keeps its last list
until it reconnects; after 15 minutes offline it shows in Repairs too.

Guest passes and lockdown work through this list: a band whose pass hasn't
started, has ended or has no uses left, or whose owner doesn't get in during
lockdown, is left off it, so the reader denies it on its own. Changes reach
the readers within seconds (somebody leaving or coming home, the alarm, a
setting) or within a minute (a pass or night hours starting or ending). A
reader cut off from Home Assistant keeps its last list, so while it's offline
a lockdown or a pass's end isn't applied, and a pass's uses aren't counted.
Lockdown isn't a lock: it only changes who the readers welcome, and what that
opens is up to your automations.

Readers also store each band's welcome colour. On a paired reader
`set_band_colours` needs the key (above); on a reader that isn't paired yet,
any Home Assistant user can call it, but that only changes the colour a band
is welcomed in, not whether it's let in.

## Devices and updates

- **No factory-reset button.** The SCREEK BP2-POE firmware leaves out
  ESPHome's "Factory Reset" button: any Home Assistant user could press it,
  and a reset board accepts the next client that brings a new encryption key.
  Its **Safe Mode Boot** button is left out too (any user could press it, and
  the board would then sit without its API and Bluetooth proxy until safe mode
  times out); ESPHome's automatic safe mode after repeated boot failures stays.
- **Unknown bands are rate-limited.** A reader reports at most 6 bands it
  doesn't know a minute and 30 an hour to Home Assistant (a band tapped again
  soon after is always reported), so a tag emulator cycling made-up IDs at the
  door can't flood Home Assistant's tag list. Bands on the allowed list are
  never held back.
- **"Test welcome"** on a reader plays the welcome without sending a tag scan
  to Home Assistant, so it can't set off automations.

- **Leave "Allow the device to perform Home Assistant actions" off** for
  readers and bridges (ESPHome → the device → Configure). Tag scans and
  everything MagicbHAnds does work without it; with it on, a tampered device
  could call any action in Home Assistant (unlock a lock, disarm an alarm).
- **No setup hotspot.** The bridge and reader firmware don't start a fallback
  Wi-Fi hotspot: ESPHome's captive portal lets anyone who joins upload
  firmware. Wi-Fi is set (and changed) over USB with the web installer.
- **First connection.** A freshly flashed board accepts the first client that
  gives it an encryption key, normally Home Assistant when you add it. Add new
  boards promptly, on a network you trust.
- **Updates** come over HTTPS from this project's GitHub Pages site and are
  checked against the MD5 in the same manifest, which catches corruption.
  Releases, and the firmware the update entities download from the site, also
  carry signed build-provenance attestations. Check a file came from this
  project's workflow on `main` (pin the workflow and the branch: `--repo` alone
  accepts an attestation from any workflow run on any branch):

  ```
  gh attestation verify <file> --repo Legal-Copy7045/Magic-bHAnds --signer-workflow Legal-Copy7045/Magic-bHAnds/.github/workflows/firmware.yml --source-ref refs/heads/main
  ```

  A release made by pushing a tag yourself (rather than from the Actions page)
  was attested on that tag: use `--source-ref refs/tags/v<version>` for its
  files. Only commits on `main` are signed or released: the signing job checks
  that a tag's commit is on `main` before it touches the key.
- **Signed updates.** The official firmware (bridge, reader and BP2) only
  installs an update signed with the project's key, whether it comes from
  Home Assistant, the ESPHome Device Builder or anything else over the air. A
  compromised site or Home Assistant can't push new firmware to a device
  without that key. **The key is used automatically by CI, though: anyone who
  can push to `main` gets their firmware signed and published**, unless the
  `release-signing` environment has a required reviewer (see Accepted risks).
  - The key is RSA-3072 (ESP-IDF's Secure Boot V2 scheme). CI signs the
    builds in the `sign` job, which only `main` and release tags whose commit
    is on `main` reach: the private key is the `OTA_SIGNING_KEY` secret of the
    `release-signing` environment. That job installs its tools (esptool and
    every package it depends on) from hash-pinned requirements files
    (`.github/requirements-signing*.txt`, `pip install --require-hashes`), so
    a new release of a dependency on PyPI can't run in the job that holds the
    key. Each image is checked against the public key in
    `esphome/firmware-signing-key.pub.pem` before it is published; check a
    download yourself with `espsecure verify-signature --version 2 --keyfile
    esphome/firmware-signing-key.pub.pem <file>.ota.bin`.
  - The check is on update only. Secure boot isn't on and no eFuses are
    burned, so a USB flash (web installer or esptool) always works, and a
    device never refuses to boot.
  - The first signed release installs like any other (the firmware before it
    doesn't check). From then on, an unsigned image or one signed with
    another key is refused, and the update entity reports the failure.
  - If the key is ever lost or replaced, each device has to be flashed once
    over USB with firmware signed by the new key.
  - **Automatic updates** (a switch on each device, off by default) installs a
    new release between 3 and 4 am without Home Assistant starting it; the
    same signature check applies, so it only ever installs signed releases,
    and it only installs a release **newer** than the one running: a site
    serving an older signed release can't roll devices back through it. (An
    update started by hand from Home Assistant still installs whatever signed
    release the site offers, older ones included; ESP-IDF has no
    anti-rollback without secure boot.)
  - Signing is added to the official builds only (`.github/scripts/
    signed_build.py`); the device files in `esphome/` don't switch it on.
- **The web installer** serves its own copy of ESP Web Tools, checked against
  a fixed hash when the site is built.
- **Building your own firmware** ("Take control") pulls the add-on and
  component from this repository's `main` branch at build time, so a build
  picks up whatever `main` holds then. Your own builds aren't signed, so a
  device running official firmware refuses them over the air: flash your
  first build over USB, after which your builds update each other as usual. The CI build installs ESPHome by
  version, not by hash, so its toolchain is only as trustworthy as PyPI and
  PlatformIO.

## Limits on what nearby radios can do

- At most 25 Bluetooth bands that nobody owns are kept (including ones
  linked automatically to a tag nobody owns); beyond that, long-unheard ones
  are dropped and new ones ignored, so made-up beacons can't flood
  Home Assistant. Bands that belong to someone are never dropped.
- A band's beacon counts at most once every 30 seconds per adapter or proxy,
  so replaying a beacon can't flood events or history (real bands beacon
  every few minutes).
- At most 60 `magicband_heard` events a minute are fired.
- At most 100 unassigned, unnamed NFC bands are kept. Bands given to
  people are never dropped and have no limit of their own.
- Only real NFC IDs (4, 7 or 10 bytes of hex) are recorded or allowed.
- A bridge broadcasts one command for at most 60 seconds, and
  `magicband.send` sends at most 30 commands a minute to each bridge (raw
  `command:` dicts have the same time limits as the normal fields). Writing
  a bridge's Command entity directly skips that limit, but the bridge's own
  airtime budget (above) still applies.

## Privacy

**Tap pictures (optional).** If a reader is linked to a camera, each tap saves
a picture of whoever is at the reader (family and visitors alike). They're
kept in `magicbhands_snapshots` in Home Assistant's config folder, not the
public `www` folder, served only to administrators or through links signed
for an hour that the admin-only history action hands out (each picture has a
random 128-bit name; a made-up signature on a non-administrator's request is
refused),
deleted after the number of days you set (30 by default), and included in
Home Assistant backups.

**Welcome sounds (optional).** A person's own welcome sound is kept in
`magicbhands_sounds` in Home Assistant's config folder (not `www`). Only an
administrator can upload, replace, remove or download one (a non-administrator
adding a made-up signature to the link is refused); a reader plays it through
a link signed for five minutes that Home Assistant makes for that welcome,
from Home Assistant's internal URL, so on a LAN where that is `http://` the
sound travels unencrypted (see Accepted risks). Uploads are read in full,
checked to be MP3, WAV, FLAC or Ogg and limited to 2 MB (a larger file is
refused, not cut short).

Band IDs, who owns them, and Bluetooth beacon data (including from other
people's MagicBand+ passing by) are stored in Home Assistant, appear in
entity attributes and history (visible to every Home Assistant user), and
are in backups. The management page loads its fonts from Google Fonts. Anyone with a band's NFC ID
can copy the band, so treat Home Assistant backups and exports accordingly.

## The management page

The MagicbHAnds page talks to Home Assistant through a small allowlist (the
shim): it can only switch, select, set or press entities that belong to
MagicbHAnds readers and bridges (never a factory-reset, safe-mode or
"forget all" style button), call MagicbHAnds' own actions, and read history
and the logbook. The page escapes everything it shows that comes from Home
Assistant (names, errors, history). See Accepted risks for what the allowlist
doesn't protect against.

## The privacy guard (this repository)

The repository is public, so every push and pull request runs
`.github/scripts/privacy_guard.py`. It fails on commit addresses that aren't
GitHub no-reply addresses, on anything that looks like a credential, on
tracked secrets files, and on private terms the owner keeps in an Actions
secret (never in the repository). It checks commit messages and names, file
names and paths, every tracked file, and everything **each new commit adds**,
so a value added and removed again in one push is still caught (it stays in
the public history). A new branch or tag is checked from where it leaves
`main`. Binary files are checked by their readable text (ASCII and UTF-16
runs of 6 characters or more), and `.zip` files by their members' names and
contents. Matches are reported by commit, file, line and rule number, never
by the text that matched.

## Accepted risks

Design limits that stay, why they're acceptable, and what limits them. A
review doesn't need to report these again unless the description here is
wrong or its limits no longer hold.

- **One pairing key for all readers, visible to administrators in the
  recorder.** MagicbHAnds sends the same key to every reader, and each reader
  stores it in flash without encryption, so whoever opens one reader and reads
  its flash has the key for all of them. The key also travels in the reader
  actions MagicbHAnds calls, and Home Assistant records every action call
  (`call_service` events) with its data, so it is in the recorder database and
  backups and visible to administrators. *Why acceptable:* the key only
  controls what the readers' own lights and sounds do; who is let in is
  decided by Home Assistant (`magicband_tap`'s `allowed`), which the key
  doesn't change. *Limits:* only administrators can read events and the
  config entry; a reader's flash needs physical access to the electronics
  (keep them inside, see above); exclude `call_service` from the recorder if
  you don't want it stored.
- **The page runs with the signed-in user's full Home Assistant access.** It
  is a same-origin frame of the Home Assistant front end, so script running in
  it could use the whole `hass` object, not only the shim. *Why acceptable:*
  the shim's allowlist guards against bugs in the page (a wrong entity,
  a stray button press), not against injected script; the page escapes
  everything it renders and only administrators can open it. *Limits:* an
  injection bug in the page would run as that administrator, so anything new
  the page shows must be escaped like the rest.
- **Home Assistant's own tag list can still grow slowly.** Every unknown band
  a reader reports becomes a tag in Home Assistant's tag registry, which
  MagicbHAnds doesn't prune. *Why acceptable:* the reader reports at most 6
  unknown bands a minute and 30 an hour, so a flood of made-up IDs grows the
  list by at most 720 a day, and someone has to stand at the reader to do it.
  *Limits:* delete stray tags under Settings → Tags; MagicbHAnds keeps at most
  100 unassigned bands of its own.
- **Welcome sounds can cross the LAN unencrypted.** The reader fetches a
  person's welcome sound from Home Assistant itself, through a link signed for
  five minutes made from Home Assistant's internal URL (handed to the reader
  through Home Assistant's ESPHome media proxy); when that URL is `http://`,
  someone on the LAN can capture the sound. *Why acceptable:* it is a short
  sound the reader plays out loud at the door anyway. *Limits:* the link stops working after
  five minutes and names only that sound; set an `https://` internal URL if
  your sounds are private.
- **Refused-tap lockout can lock the household out.** With **Refused-tap
  lockout** on (off by default), anyone with a few cards or a tag emulator
  can make enough refused taps (five by default) to lock the reader for the
  lockout time, and do it again; while locked out the reader ignores every
  tap, the household's included. *Why acceptable:* it is opt-in, for readers
  where someone trying cards at the door is the bigger worry; the reader's
  **Tap lockout** sensor shows it and **End lockout now** clears it. *Limits:*
  leave it off on a reader that opens a door you rely on; the lockout time is
  at most 60 minutes.
- **Anyone who can push to `main` can ship signed firmware.** CI signs and
  publishes whatever `main` holds, and devices with Automatic updates install
  it overnight. *Why acceptable:* it's what makes releases automatic; signing
  still stops anyone who controls only the site, Home Assistant or another
  branch. *Limits:* the owner should give the `release-signing` environment a
  **required reviewer** (Settings → Environments → release-signing → Required
  reviewers) so every signed build waits for approval, and protect `main`;
  tags whose commit isn't on `main` are never signed; Automatic updates never
  install an older release.
- **The privacy guard reports, it doesn't prevent.** It runs after a push, so
  a match is already public until the history is rewritten. It doesn't open
  compressed streams inside other binaries (PDF streams, compressed PNG text,
  fonts), files over 20 MB, or archives other than `.zip`, and it only knows
  the private terms the owner listed. Without the secret (a pull request from
  a fork) private terms aren't checked. *Limits:* strip metadata from images
  and documents before adding them, and run the guard locally with your
  terms before pushing.

## Reporting a problem

Open a GitHub issue without exploit details and ask for a private contact,
or use GitHub's private vulnerability reporting if it's enabled.
