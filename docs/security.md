# Security

What MagicbHAnds protects, what it can't, and what to do about it. The short
version: **a MagicBand's NFC ID and Bluetooth beacon identify a band; they
don't prove it's genuine.** Treat a tap like a cheap RFID fob, not a key.

## Threat model

MagicbHAnds is a home MagicBand reader for a family's front door, not a vault.
Nobody realistically targets it to get into a house: a burglar breaks a
window. So the hard lines are that the devices can never become a way in for
malicious code, and nothing private leaks: official firmware installs only
signed updates, the device-to-Home Assistant link is encrypted, changing who
gets in needs an administrator, the page can't be made to run injected
script, inputs and uploads are validated, and the signing key is out of
reach of anything but `main`. Nuisance and denial of service, by someone
standing at the door or by household members who have Home Assistant
access, is accepted in favour of convenience and listed under
[Accepted risks](#accepted-risks) rather than engineered around.

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
with the same key doesn't extend the wait. Any Home Assistant user can call an
unpaired reader's own `pair` action, so someone else can ask first.
MagicbHAnds asks you to tap only while the reader tells it its own request
is the one waiting. If a different key is waiting (the reader answers
`PAIRING_BUSY`), Repairs says so: **don't tap**, and MagicbHAnds asks
again by itself once that wait runs out. If a reader ever pairs with another
key anyway, MagicbHAnds says so in Repairs (the reader then refuses its lists
and answers) and how to recover: erase the reader over USB and add it again.
Someone with Home Assistant access can still block or race the pairing of a
new reader (see Accepted risks); only a tap while *MagicbHAnds* asks you to
should finish pairing.
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
until it reconnects, and is sent the current one as soon as it does; after 15
minutes offline it shows in Repairs too.

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
- **A flood guard on unknown bands.** A reader reports at most 60 bands it
  doesn't know a minute and 600 an hour to Home Assistant, in every mode (a
  band tapped again soon after is always reported), so a tag emulator cycling
  made-up IDs at the door can't grow Home Assistant's tag list without bound.
  That's far above what people can tap, so enrolling a family's bands or a
  queue of guests never hits it. Bands on the allowed list, or that have been
  on it, are never held back.
- **"Test welcome"** on a reader plays the welcome without sending a tag scan
  to Home Assistant, so it can't set off automations.

- **Leave "Allow the device to perform Home Assistant actions" off** for
  readers and bridges (ESPHome → the device → Configure). Tag scans and
  everything MagicbHAnds does work without it; with it on, a tampered device
  could call any action in Home Assistant (unlock a lock, disarm an alarm).
- **Setup hotspot (official bridge and reader firmware).** When the device
  can't reach its Wi-Fi for 2 minutes, or has none set yet, it starts an open
  hotspot ("MagicBand Reader Setup", "MagicBand Bridge Setup") with ESPHome's
  captive portal, where you pick a new network; it stops as soon as the
  device is back on Wi-Fi and never starts while Wi-Fi works. The captive
  portal also accepts a firmware upload, but that upload goes through the
  same signature check as every other update (ESP-IDF checks it before the
  image can boot), so an image not signed with the project's key is refused:
  nobody who joins can install their own code. *Its limits:* the hotspot has
  no password (a password published in this repository would protect
  nothing), so a stranger nearby during a Wi-Fi outage can join it and set a
  different network, taking the device offline until you set it back (see
  Accepted risks). Until a board has been added to Home Assistant, whoever
  joins its hotspot first could also claim it (see First connection): give it
  Wi-Fi and add it straight after flashing. It's added to the official signed builds only
  (`.github/scripts/signed_build.py`): the device files in `esphome/` and
  your own builds, which aren't signed, don't have it, since there anyone who
  joined could upload any firmware. The BP2-POE uses Ethernet and has none.
  Wi-Fi can still be set over USB with the web installer (Improv).
- **First connection.** A freshly flashed board accepts the first client that
  gives it an encryption key, normally Home Assistant when you add it. Add new
  boards promptly, on a network you trust. A brand-new bridge or reader with no
  Wi-Fi set starts its open setup hotspot straight away, and the API listens
  there too, so until the board has been added to Home Assistant whoever
  connects first could claim it with their own key. That can't be used to
  install code (updates must still be signed), but Home Assistant then can't
  add the board until you erase it and flash it again over USB. So give a new
  board its Wi-Fi in the web installer and add it to Home Assistant straight
  after flashing.
- **Updates** come over HTTPS from this project's GitHub Pages site and are
  checked against the MD5 in the same manifest, which catches corruption.
  Releases, and the firmware the update entities download from the site, also
  carry signed build-provenance attestations. Check a file came from this
  project's workflow on `main` (pin the workflow and the branch: `--repo` alone
  accepts an attestation from any workflow run on any branch):

  ```
  gh attestation verify <file> --repo Legal-Copy7045/Magic-bHAnds --signer-workflow Legal-Copy7045/Magic-bHAnds/.github/workflows/firmware.yml --source-ref refs/heads/main
  ```

  Releases come only from `main`: a merge that raises `VERSION` releases it
  from the same signed build (or **Run workflow** on `main`, to retry), and
  only commits on `main` are signed or released. The `sign` job runs only for `main` and
  checks the commit is on `main` before it touches the key, but what really
  guards the key is the `release-signing` environment that holds it: its
  deployment branches allow only `main` (no tag rule), so GitHub refuses the
  key to a pushed tag or any other branch, even one whose commit edits the
  workflow. A pushed `v*` tag only builds and tests; it isn't signed or
  released.
- **Signed updates.** The official firmware (bridge, reader and BP2) only
  installs an update signed with the project's key, whether it comes from
  Home Assistant, the ESPHome Device Builder, the setup hotspot or anything
  else over the air. A
  compromised site or Home Assistant can't push new firmware to a device
  without that key. **The key is used automatically by CI, though: anyone who
  can push to `main` gets their firmware signed and published**, so the
  account that can push to `main` is what protects releases: it should use
  two-factor authentication (see Accepted risks).
  - The key is RSA-3072 (ESP-IDF's Secure Boot V2 scheme). CI signs the
    builds in the `sign` job, which only `main` reaches: the private key is the
    `OTA_SIGNING_KEY` secret of the `release-signing` environment, which only
    `main` may use. That job installs its tools (esptool and
    every package it depends on) from hash-pinned requirements files
    (`.github/requirements-signing*.txt`, `pip install --require-hashes`), so
    a new release of a dependency on PyPI can't run in the job that holds the
    key. The images it signs are built in an earlier job whose toolchain isn't
    pinned that way (see Accepted risks). Each image is checked against the public key in
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
    and it only installs a release whose version in the site's manifest is
    **newer** than the one running. That version number isn't signed, so
    someone who controls the site could still offer an older signed release
    under a higher number (see Accepted risks). (An update started by hand
    from Home Assistant installs whatever signed release the site offers,
    older ones included; ESP-IDF has no anti-rollback without secure boot.)
  - Signing is added to the official builds only (`.github/scripts/
    signed_build.py`); the device files in `esphome/` don't switch it on.
- **The web installer** serves its own copy of ESP Web Tools, checked against
  a fixed hash when the site is built.
- **Building your own firmware** ("Take control") pulls the add-on and
  component from this repository's `main` branch at build time, so a build
  picks up whatever `main` holds then. Your own builds aren't signed, so a
  device running official firmware refuses them over the air: flash your
  first build over USB, after which your builds update each other as usual.

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
the public history). Each commit's files are listed NUL-separated and read one
by one, so no file name and no byte inside a file (a control character,
invalid UTF-8) can hide the rest of a commit. A new branch or tag is checked
from where it leaves `main`; a force push from where the old and new
histories meet, or the whole history when the old tip can't be found. Binary
files are checked by their readable text (ASCII and UTF-16 runs of 6
characters or more), and `.zip` files by their members' names and contents.
Matches are reported by commit, file, line and rule number, never by the text
that matched, and a file name or path that itself matches is never printed,
only its position in a git listing.

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
  MagicbHAnds doesn't prune. *Why acceptable:* the reader's flood guard reports
  at most 60 unknown bands a minute and 600 an hour, so a flood of made-up IDs
  grows the list by at most 14,400 a day, and someone has to stand at the
  reader with a tag emulator to do it; it's clutter, not a way in.
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
  tap, the household's included. The **Refused-tap lockout** switch and its
  **Lockout after**, **Lockout window** and **Lockout time** numbers are
  ordinary entities any Home Assistant user can change, though, so any user
  (not only an administrator) can turn it on, down to 2 refused taps for 60
  minutes. *Why acceptable:* it is off by default, meant for readers where
  someone trying cards at the door is the bigger worry; the reader's **Tap
  lockout** sensor shows it, **End lockout now** clears it, and the switch's
  history shows who turned it on. *Limits:* leave it off on a reader that
  opens a door you rely on and check it hasn't been turned on; the lockout
  time is at most 60 minutes.
- **Anyone who can push to `main` can ship signed firmware.** CI signs and
  publishes whatever `main` holds, and devices with Automatic updates install
  it overnight. *Why acceptable:* it's what makes releases automatic; signing
  still stops anyone who controls only Home Assistant, another branch or a
  tag from getting firmware signed, and anyone who controls only the site
  from installing firmware that wasn't signed (an older signed release is
  another matter, below). *Limits:* the account that can push to `main` is
  what protects releases, so it should use **two-factor authentication**;
  protect `main`, and keep the `release-signing` environment's deployment
  branches to only `main` (no tag rule), which is what keeps tags and other
  branches away from the key, whatever their copy of the workflow says.
- **Automatic updates trust the manifest's version number.** The "newer
  only" check compares the `version` in the site's manifest, which isn't
  signed, with the version of the firmware running. Someone who controls the
  update site (but not the key) can make a device with Automatic updates
  install an older *signed* release by listing it under a higher number.
  *Why acceptable:* it still runs only firmware you signed, never anyone
  else's code. *Limits:* manual installs can always downgrade anyway (ESP-IDF
  has no anti-rollback without secure boot); the site is this repository's
  GitHub Pages, published only from `main`; turn Automatic updates off on a
  device if you'd rather start each update yourself.
- **The signed firmware is only as clean as its build toolchain.** The `sign`
  job installs only hash-pinned tools, but the images it signs come from the
  `build` job, which installs ESPHome by version (not by hash) and fetches
  the PlatformIO platforms and toolchains unpinned (and caches them). A
  compromised release of ESPHome or one of its dependencies, of a PlatformIO
  package, or of GitHub's runners would end up inside firmware that is then
  signed and accepted by every device. *Why acceptable:* pinning every
  toolchain by hash isn't practical for ESPHome builds, and these are the
  same sources every ESPHome user builds from. *Limits:* signing proves an
  image came from this workflow on `main`, not that the toolchain was clean;
  the build is only as trustworthy as PyPI, PlatformIO and GitHub's runners;
  ESPHome is pinned to one version (`ESPHOME_VERSION`), updated deliberately.
- **Someone with Home Assistant access can block or race the first pairing
  of a new reader.** Any Home Assistant user can call an unpaired reader's
  own `pair` action, and whoever asks first holds its pairing for that wait,
  so a user who keeps asking with fresh keys can stop MagicbHAnds pairing a
  new reader, or have their own key waiting when you look at it. *Why
  acceptable:* their key only gets in if someone taps a band on the reader
  while MagicbHAnds says not to: it only asks for a tap while its own request
  is waiting, says **don't tap** when another key is, and says so if a reader
  ever pairs with another key. Who is let in is still decided by Home
  Assistant; the key only controls the reader's own list, lights and
  sounds. *Limits:* only readers that have never been paired (or were erased)
  are exposed; pair new readers promptly and tap only when Repairs asks you
  to; a reader paired with another key is erased over USB and added again.
- **Restarting a device.** Any Home Assistant user can press a device's
  restart button (**Restart**, or **Reboot Device** on the BP2); each press
  takes it offline for a few seconds while it starts again. Pressing it over
  and over never puts a device in safe mode: the button restarts cleanly
  (ESPHome's safe reboot clears its boot-loop counter first), and only
  unclean resets (a crash, the watchdog, a power cut) count towards safe mode.
  The BP2's raised safe-mode thresholds (20 failed starts within 30 seconds
  each) are only for real boot loops. *Why acceptable:* it's an availability
  nuisance only: it changes no setting and lets no one in, and restarting a
  device is something any user can do anyway. *Limits:* it needs a Home
  Assistant account and someone pressing the button for as long as it lasts.
- **Unknown-band flood guard.** A reader reports at most 60 bands it doesn't
  know a minute and 600 an hour to Home Assistant, the same in every mode
  (bands on its list, or that it has had on its list, aren't held back). On a
  reader that answers through **Ask Home Assistant**, a 61st new band in a
  minute (or a 601st in an hour) never reaches Home Assistant and is refused
  after 3 seconds. *Why acceptable:* nobody taps that fast at one reader, so
  it only bites during a tag-emulator flood, which it exists to bound; a
  family enrolling its bands or a queue of guests never comes close.
  *Limits:* a band tapped again soon after is always reported.
- **A stranger nearby can take a Wi-Fi device offline through its setup
  hotspot.** While a bridge or reader can't reach its Wi-Fi (a router
  restart, an outage, someone jamming it), it starts an open setup hotspot
  after 2 minutes, and anyone in range can join it and give the device a
  different network. *Why acceptable:* it's a nuisance, not a way in: the
  hotspot's firmware upload refuses anything not signed with the project's
  key, the device's encryption key and pairing aren't touched, and anyone at
  the device with a USB cable could change its Wi-Fi (Improv) anyway; in
  return a family changes Wi-Fi without unplugging anything. *Limits:* it
  only starts after 2 minutes without Wi-Fi and stops once the device is
  back; set the right network again through the hotspot or over USB. Builds
  you make yourself don't have the hotspot.
- **The privacy guard reports, it doesn't prevent.** It runs after a push, so
  a match is already public until the history is rewritten. It doesn't open
  compressed streams inside other binaries (PDF streams, compressed PNG text,
  fonts), files over 20 MB, or archives other than `.zip`, reports a binary
  file whose content it has already checked in the same run only once, and it
  only knows the private terms the owner listed. Without the secret (a pull request from
  a fork) private terms aren't checked. *Limits:* strip metadata from images
  and documents before adding them, and run the guard locally with your
  terms before pushing.

## Reporting a problem

Open a GitHub issue without exploit details and ask for a private contact,
or use GitHub's private vulnerability reporting if it's enabled.
