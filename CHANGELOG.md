# Changelog

All notable changes to MagicbHAnds. The bridge firmware, reader firmware and
Home Assistant integration share one version number.

## [0.10.35] - 2026-11-24

### Fixed
- **"MagicBand Reader didn't take the allowed list" no longer cries wolf.** A
  reader that doesn't reply (typically for a few seconds after it restarts, for
  example into new firmware) is synced again 30 seconds later, and the repair
  only shows after three no-replies in a row. A reader that answers and refuses
  the list still gets the repair at once.

## [0.10.34] - 2026-11-24

Fourth round of regression fixes (small).

### Fixed
- Readers added before 0.10.32 are unlinked from MagicbHAnds at start-up, so
  removing one removes its device and sensors.
- Celebration and Stamp shows play only when the reader itself welcomed the
  band (not after a tap it refused).
- A lockout that starts while a reader is offline is announced after a Home
  Assistant restart too.
- "Tap a band" never outlasts the reader's wait after a restart or reload, and
  goes when MagicbHAnds is unloaded; the reader card's hint says to tap only
  when Repairs asks.
- Docs: restarting a device never leads to safe mode; a brand-new board should
  get its Wi-Fi and be added to Home Assistant straight after flashing (its
  setup hotspot is open until then).

## [0.10.33] - 2026-11-24

Second and third rounds of regression fixes, and security set for a home
device: convenience first, as long as nothing can put code on the devices.

### Easier
- **Wi-Fi setup hotspot is back** (reader and bridge, official builds): if a
  device can't reach Wi-Fi for 2 minutes it opens a "<name> Setup" hotspot where
  you pick the new network, no USB needed. Firmware uploaded through it must
  still be signed, so it can't install anyone else's code.
- **Unknown-band limit is only a flood guard now** (60 new bands a minute, 600
  an hour), so enrolling a family's bands at once always works; bands that have
  ever been on the reader's list are never held back.
- **No extra pairing fingerprint or on-device downgrade check**: you can still
  go back to an older release from Home Assistant if you need to. Automatic
  updates still only install newer releases.
- `docs/security.md` starts with a short threat model: a home reader, not a
  vault. Two-factor login on the GitHub account replaces the advice to add a
  required reviewer to releases.

### Fixed
- **Celebration and stamp shows after a welcome** now play (they were dropped
  since 0.10.24 because the reader refused them while it was still welcoming).
- Pairing prompts show only while MagicbHAnds' own request is waiting, go away
  as soon as the reader is paired, and say so if a reader paired with another
  key.
- A lockout that starts while a reader is briefly offline is announced when
  it comes back.
- Removing a reader added since 0.10.32 removes its MagicbHAnds sensors and
  repairs (older readers: 0.10.34).
- Bands with their own welcome sound get the reader's chime again when their
  sound is missing or fails, or when MagicbHAnds is unloaded or the reader is
  released.
- Assign and Link messages stay under the right band; Hanukkah is listed once
  when it runs into January.
- SCREEK BP2-POE: safe mode starts only after a real boot loop (20 failed starts
  in a row); restarting it from Home Assistant never counts towards it.
- Privacy guard: robust against unusual file names and bytes, checks force
  pushes from where histories meet, and never prints a matching file name.
- Releases are signed only from `main` (a pushed tag can't reach the key).

## [0.10.32] - 2026-11-24

Fixes from the first full regression run (`regression/RUNS.md`).

### Security
- **Welcome sounds and tap pictures:** downloads need an administrator or a
  genuinely signed link. Before, any signed-in user could add a made-up
  signature to the address and get the file.
- **First pairing:** the first request wins and can't be kept open by asking
  again; another key's request gets "busy", and MagicbHAnds says in Repairs not
  to tap and tries again by itself.
- **Readers:** Forget all bands and Forget last band do nothing while paired;
  unknown bands are reported to Home Assistant at most 6 a minute and 30 an
  hour; the reader's own play_show action is limited to 12 a minute.
- **SCREEK BP2-POE:** the Safe Mode Boot button (pressable by any user) is gone.
- **Automatic updates** only install newer releases, never an older one.
- **The page** can only control entities on MagicbHAnds readers and bridges.
- **Release pipeline:** the signing job only signs commits on main, installs
  its tools from hash-pinned requirements, and the build job no longer holds
  attestation permissions. Release verification pins the workflow and branch.
- **Privacy guard:** checks every commit in a push, new branches from where
  they left main, file names, and text inside binaries and zip files.
- `docs/security.md`: claims corrected, and a new **Accepted risks** section.

### Fixed
- **An unplugged reader showed as online** on the MagicbHAnds page.
- **Welcome sound uploads** were saved cut short, and the 2 MB limit never
  applied.
- **Removing a person in Configure** left their welcome sound and passport
  behind; **removing a band** left its Bluetooth band linked to it.
- **Refused-tap lockout:** the first lockout after a reader restart sent no
  notification, and a notification could stay up after a restart.
- **Welcome sounds** were silent after a Home Assistant restart until the next
  sync, and when Home Assistant was down (the reader now plays its own chime).
- Welcome-colour and sound lists that don't fit a reader are cut to whole
  entries with a repair, instead of failing on the reader.
- Changing LED count, brightness, colour order or idle glow no longer cuts off
  a tap's welcome or denied sequence.
- The page's "Tonight" times and live ring use the reader's **Time zone**.
- Sunset and sunrise times follow a **Time zone** change at once.
- After a power cut at night, the start-up sound honours **Sound at night**.
- The **Heartbeat** show ends dark; dim colours keep their mix even at the
  lowest LED brightness.
- Hanukkah days that fall in January are celebrated.
- The automatic-update install message is logged on the reader.
- Home Assistant deprecation warnings about the device registry.
- Page: the Time zone selects are labelled, the jump and status chips are full
  size on touch screens, Assign and Link errors show on their card, and a
  person's actions line up with the rest of the row.

### Regression suite
- New checks for every fix; 208 integration tests, 182 page checks, firmware
  and CI checks extended.

## [0.10.31] - 2026-11-23

### Firmware
- **Automatic updates:** a switch on each bridge, reader and BP2 (off by
  default). When on, the device looks for a new release at 02:55 and installs it
  between 03:00 and 04:00 local time (tried every 10 minutes), without Home
  Assistant starting it. Only signed releases install. On the MagicbHAnds page:
  the reader's Health fold-out and the bridge card.
- **Internet time and a Time zone setting:** each device keeps time from an
  internet time server (SNTP) as well as Home Assistant, so the update window
  (and the reader's night mode) keeps working while Home Assistant is down.
  **Time zone** (default Eastern, New York; also Central, Mountain, Arizona,
  Pacific, Alaska, Hawaii, UK, central Europe and UTC) sets local time for
  every clock on the device, instead of Home Assistant's zone.

## [0.10.30] - 2026-11-23

### Firmware
- **Signed updates:** the official bridge, reader and BP2 firmware only installs
  updates signed with the project's key (RSA-3072, ESP-IDF's Secure Boot V2
  scheme), from Home Assistant or any other over-the-air upload. Checked on
  update only: no secure boot, no eFuses, and a USB flash always works. This
  release installs as usual; later ones must be signed. Builds of your own
  aren't locked: install the first one over USB. See docs/security.md, "Signed
  updates".

### Build
- CI signs the firmware in a separate `sign` job that only `main` and release
  tags reach (the `release-signing` environment), checks every image against
  `esphome/firmware-signing-key.pub.pem`, then builds the site and release
  files from the signed images.

## [0.10.29] - 2026-11-22

### Reader
- **Fix:** on RGB rings a warm-white circle's tail faded to a bluish white
  (0.10.27's fix took RGB rings for RGBW ones). Dimmed LEDs now check whether
  the ring really has a white LED, so the tail stays warm to the end.

## [0.10.28] - 2026-11-22

### MagicbHAnds page
- **Fix:** the New bands count and list could stay empty when a reader was
  listed before the integration's own device (a reader's Allowed list sensor
  was taken for the unknown-bands sensor). Readers and bridges are no longer
  treated as service devices, and the unknown-bands and last-tap sensors are
  found by their attributes instead of by entity ID.
- **Fix:** a redraw no longer closes a drop-down or a number box in use: only
  the section with the focused control waits, and catches up when it's left.
- Reader, bridge and band cards and each reader settings group have their own
  message line: a short "done" after a change, and an error that stays (the
  control goes back to what Home Assistant has). Before, failures there were
  silent. The same for the band-type buttons and the camera picture days.
- Number settings are checked against their range and step before sending
  ("LEDs: 1–60"); settings that go below 0 (Night starts after sunset, Night
  ends after sunrise) get the ordinary keyboard on a phone, which has a minus.
- **Manage** on a Bluetooth-only band: **Link to…** an NFC band or a person,
  and **Forget this Bluetooth band** (asks for a second tap).
- **Owner, then name** puts bands nobody owns last (they came first).
- **Band light-up power** on each reader card, under Light up MagicBand+.
- A reader that isn't paired with MagicbHAnds yet says so under Health ("Not
  paired: tap a band on it within 2 min of pairing").
- Messages: the readers get the allowed list on their own a few seconds after
  each change, so "Push to readers" is now **Re-send list to readers** and the
  messages say so. The fold-out is called "Birthday, welcome sound, lockdown,
  guest pass" everywhere.
- On a phone the six totals at the top show two to a row again (the shared
  style sheet made them one per row).
- Loosening access takes a second tap: **Clear the pass**, turning **Guest**
  off (drops the pass) and **Always allowed**; Response mode **Welcome every
  band** has to be picked twice, and while it's on the reader card shows a red
  "Lets every band in" tag.

### MagicbHAnds page: layout and wording
- New order: header and status strip (problems first: a reader offline, its
  list not applied, locked out or not paired, lockdown on, a low band
  battery), **Needs attention** (only when there's something), **Recent
  taps**, **People and access** (Lockdown on top), **Bands**, **Readers**,
  **Bridges and band effects**, **Celebrations and tap passport**. A sticky
  row of chips under the header jumps to each section, and the totals jump to
  theirs.
- Needs attention: new bands, Bluetooth to link, "Which kind of band?",
  reader problems (with **Re-send list** and **End lockout now**) and band
  batteries at 20% or less. The cards share the row instead of leaving a gap.
- Recent taps say **Let in** / **Turned away**, show the full date and time on
  hover, and a turned-away band nobody owns has **Assign…**, which jumps to its
  New bands card.
- People: the fold-out is now two, **Access** (Allowed, Gets in during
  lockdown, Guest and the pass) and **Welcome and birthday** (welcome colour,
  sound, birthday). Each row has a one-line access summary ("Guest · Mo We Fr
  11:00–14:00 · 12 uses left · not now"). A band's **own hours** and the
  person's **guest pass (all their bands)** each say that the other applies
  too. Remove arms to "Tap again to remove Sam".
- Band cards: no Battery, Closest or Bluetooth rows on a standard (NFC-only)
  band; **Type** is under Manage once it's known. "7 bands", "Search bands".
- Reader cards: status tags in the title (Online/Offline, Locked out, Night,
  Not paired, Lets every band in), the ring, a status line, the everyday
  controls, Test welcome and Play show, then **Health** (tiles, network,
  Restart; a summary like "Wi-Fi good · up 1 d 6 h" while closed) and **Ring
  and tap settings**. **Re-send list to readers**, how long camera pictures are
  kept and the **Ring preview** (LEDs or Diffused, one choice for the page)
  are above the reader cards.
- Ring and tap settings regrouped: Waiting for a band (the circle settings
  show only when a Style is Circle), Night (when it runs first, with tonight's
  times, then the night style, glow and sound; **Quieter volume** only when
  Sound at night is Quieter), Reading a band, Welcome (with Light up
  MagicBand+ and Band light-up power), Denied, **Refused-tap lockout** (not
  the house Lockdown; **End lockout now** while locked out), Shows, and
  **Hardware** last (Ring type, LED count, Colour order, Max brightness: these
  restart the reader, so a change has to be made twice).
- Labels: Quieter volume, Night from/until, Night runs, One lap takes, Tail
  fades to, Pulses, Show for "Play show", LED count, Max brightness, Show when
  a new stamp is earned. "Nearby now" says the real window (35 min). Fast
  mode, Bluetooth proxy, Wake bands and Ping explain themselves.
- **Send to every band in range** moved to the bridges (its Wake and Ping
  were the same as each bridge's); the Link Bluetooth hint has its own **Wake
  bands** button.
- Times over a day old read "yesterday 9:14 am", "Tue 9:14 am", then the date.

### MagicbHAnds page: phones and accessibility
- People are cards instead of a wide table: a row of fields on a computer,
  stacked on a phone, with the Access and Welcome and birthday fold-outs as
  label-over-control rows, so nothing scrolls sideways or gets cut off.
- Phones: band facts stay in two columns in the body font (IDs stay
  monospaced); Recent taps puts the reader under the band and keeps the
  picture column whole; the night lockdown times sit together on their own
  line; the camera hint is under its row; the header drops its copy of
  reader 1's ring (the Readers section shows it) and keeps the live line;
  the section chips scroll sideways in one row.
- Touch screens get 44 px targets: buttons, toggles (larger, with a 44 px
  touch area), fold-out headings, 20 px check boxes, sliders, drop-downs and
  boxes.
- Health tiles fit four to a row on a phone; Wi-Fi shows just its quality
  (the dBm is in the tooltip) and Memory says "free" (largest block in the
  tooltip).
- Ring and tap settings: the unit sits inside each number box, so boxes end
  where the drop-downs end.
- Tap passport: the stamps someone has, "Next: Frequent visitor at 50 taps
  (33 to go)", and all 16 in a fold-out.
- The **Readers OK** total counts readers that are online, have the list, are
  paired and aren't locked out, and says how many problems there are
  ("Readers online" looked fine while a reader had problems).
- Toggles show their off state (an outlined track and knob), are switches to
  screen readers (on/off kept in step) and say what and whose ("Allowed:
  Sam", "Sound: Front Door Reader"). Every drop-down, box and slider has a
  label; reader settings use real labels (clicking one focuses its control).
- Dark mode: dark text on the purple buttons (Assign, Link, Send, the chosen
  Ring preview) and on toggles that are on; hint text is darker in light mode
  for contrast on grey panels.
- Keyboard: **Upload…** for a welcome sound is a real button; tap pictures are
  buttons, and the enlarged picture has **Close**, closes on Esc and returns
  the focus; the battery chart takes the focus and gives it back; visible
  focus outlines on buttons, toggles, fold-outs and chips. Band and person
  names are headings under their section.

## [0.10.27] - 2026-11-22

### Reader
- **Idle circle shape:** **Idle circle tail** (LEDs, 0 = a fifth of the ring),
  **Idle tail fade** (how bright the trail ends), **Idle circle heads** (1–4,
  spaced evenly) and **Idle circle direction** (Forward/Reverse), all apart from
  the tap's circle settings. On the MagicbHAnds page under *Waiting for a band*
  and drawn by the live twin.
- **Fix:** a warm-white circle's fading tail showed red. Dimmed LEDs (circle
  tails, pulses, the tap chase) are now set in the ring's own output steps in
  the colour's full-brightness mix, so a fading warm white (or orange, pink...)
  keeps its colour to the end instead of losing its green.

## [0.10.26] - 2026-11-22

### Reader
- **Idle style at night:** Static or Circle at night instead of **Idle
  style** (default **Same as day**), e.g. circling by day and a still glow in
  a dark hallway.
- **Quiet hours:** **Sound at night** on the night schedule. **Quieter** sets
  the speaker to **Night volume** (default 30 %) when night starts and puts
  the day volume back in the morning; **Off** plays no reader sounds at
  night.
- **Refused-tap lockout** (off by default): **Lockout after** refused taps
  (default 5) within **Lockout window** (60 s) stop the reader taking taps
  for **Lockout time** (5 min). The ring pulses red meanwhile and the new
  **Tap lockout** sensor is on. Works with Home Assistant offline.
- New action `set_band_sounds`: the bands whose owner has their own welcome
  sound; the reader doesn't play its tap-in sound for them.

### Home Assistant
- **Welcome sounds:** upload a sound for each person on the MagicbHAnds page
  (MP3, WAV, FLAC or Ogg, up to 2 MB). The reader that welcomes them plays it
  instead of its tap-in sound. Admin-only `magicband.play_welcome_sound`
  tries it out.
- A reader's lockout shows a notification and fires **`magicband_lockout`**.
- The page's reader settings have **Style at night**, **Sound** and **Volume**
  under Night, and a **Refused taps** group; the ring preview shows a lockout.

## [0.10.25] - 2026-11-22

### Reader
- **Idle style.** The ring can wait for a band with a steady glow
  (**Static**, as before) or a circle going round (**Circle**). The circle
  uses **Idle colour** and **Idle glow** (**Idle glow at night** at night)
  and its own speed, **Idle circle time** (default 3 s, 0.5–10 s), so it's
  set separately from the tap's checking circle.

### Home Assistant
- The reader's **Waiting for a band** settings on the MagicbHAnds page have
  **Style** and **Each circle**, and the ring preview shows the idle circle.

## [0.10.24] - 2026-11-20

### Home Assistant
- **Guest passes.** Tick **Guest** when adding someone, enrol their band, and
  give them a pass under **Birthday, lockdown, guest pass**: start and end
  dates and times, a number of welcomed taps (each welcome uses one), and a
  daily window on chosen weekdays. A band whose pass hasn't started, has
  ended or is used up is taken off the readers' lists. Admin-only
  `magicband.set_guest_pass`.
- **Lockdown.** Only the people marked **Gets in during lockdown** are let in
  while lockdown is on: by hand, when nobody's home (`zone.home`), during set
  night hours, or while a chosen alarm panel is armed. New
  `binary_sensor.magicbhands_lockdown` (attribute `reasons`); settings on the
  page or with the admin-only `magicband.set_settings`.
- **Birthdays and holidays.** Set each person's birthday; on the day their
  welcome is followed by the Birthday show. On holidays (New Year, Valentine's
  Day, St Patrick's Day, Easter, Memorial Day, Independence Day, Labor Day,
  Halloween, Veterans Day, Thanksgiving, Hanukkah, Christmas) every welcome is
  followed by that holiday's show. `play_show` takes `Today`, and so does the
  light-show blueprint.
- **Tap passport.** Taps, days, streaks and 16 stamps per person (not
  guests), shown on the page. A new stamp fires `magicband_badge`, shows in
  Recent taps, and plays the Stamp show after the welcome.
- `magicband_tap` events carry `celebration` and `badges`.

### Reader
- **Eleven new light shows:** Birthday, New Year, Valentine, St Patrick,
  Easter, Stars and Stripes, Halloween, Thanksgiving, Hanukkah, Christmas and
  Stamp. **Random** picks only the everyday shows. A show sent during a tap
  waits for the welcome to finish.

## [0.10.23] - 2026-11-20

### Home Assistant
- **A picture with each tap (optional).** Link a reader to a camera (any
  Home Assistant camera, e.g. a Ring doorbell's live view) on its card on the
  MagicbHAnds page, or with the admin-only `magicband.set_reader_camera`.
  Every tap on that reader then saves a picture, in the background so the
  tap and any unlock aren't delayed, and the **Recent taps** list shows it
  (click for full size). Readers without a camera work as before. Pictures
  are kept in `magicbhands_snapshots` in the config folder (not the public
  `www`), shown only to administrators through short-lived signed links,
  and deleted after 30 days (**Keep tap snapshots for** in MagicbHAnds →
  Configure → Settings, or next to **Recent taps** on the page; admin-only
  `magicband.set_snapshot_days`).

## [0.10.22] - 2026-11-20

### Security
- **First pairing needs someone at the reader.** A reader that had never
  been paired took the first key it was sent, so another Home Assistant user
  could claim a new reader before MagicbHAnds did. Now a first pairing
  waits (the ring breathes blue, for up to 2 minutes) until a band is tapped
  on the reader; that tap only confirms the pairing. While one request
  waits, the reader refuses any other key, so MagicbHAnds notices if someone
  else asked first. Repairs walks you through it. Readers that are already
  paired aren't affected.
- **A released reader stays released.** After `magicband.unpair_reader`,
  the next periodic sync asked to pair the reader again, so the same Home
  Assistant reclaimed it (or, with tap-confirmed pairing, kept another Home
  Assistant from pairing it). A released reader is now remembered and left
  alone: no pairing, allowed list, answers, light shows or offline repairs.
  The new admin-only **`magicband.pair_reader`** takes it back.

## [0.10.21] - 2026-11-20

### Security
- **A paired reader can't be taken over after a power cut.** 0.10.20 let a
  paired reader take a new key in the 10 minutes after a power-on, and any
  Home Assistant user can call the reader's `pair` action, so someone could
  pair it with their own key during that window. A paired reader now never
  takes a different key over the network: only the key holder can release
  it (new `unpair` action on the reader, and the admin-only
  `magicband.unpair_reader`), or it can be erased over USB with the web
  installer. The key is in Home Assistant's backups.

## [0.10.20] - 2026-11-20

### Security
- **Readers are paired with MagicbHAnds.** Any Home Assistant user can call
  ESPHome actions, so a non-admin could give a reader a new allowed list or
  answer an "Ask Home Assistant" tap. Now the integration pairs each reader
  with a secret key (kept where only administrators can read it), and a
  paired reader refuses `set_known_bands`, `set_band_colours`, `accept` and
  `deny` without it (a refused list leaves the current one in place). Its
  **Allow last band** button does nothing once paired. A paired reader takes
  a new key only within 10 minutes of a power-on, so after reinstalling Home
  Assistant, unplug the reader for a few seconds. New **Paired with
  MagicbHAnds** sensor on the reader.
- **`magicband.answer`** (administrators and automations): answers a reader
  in "Ask Home Assistant" mode, with the key. Use it instead of the reader's
  own accept / deny actions.
- **Bridges limit their own airtime.** `magicband.send`'s limit could be
  sidestepped by writing the bridge's Command entity or calling its actions,
  and a stream of commands kept the bridge broadcasting and its Bluetooth
  proxy from scanning. The bridge now earns half a second of broadcasting
  per second (up to 30 s), whatever sends the commands, and scans while it
  waits.

## [0.10.19] - 2026-11-20

### Security
- **The tap that enrols a band no longer counts as allowed.** During
  enrolment, an unknown band tapped on any reader was given to the person
  being enrolled and reported `allowed: true` on that same tap, so an unlock
  automation could open the door for a stranger's tag. That tap is now
  `allowed: false` (with `enrolled: true`); the band's next tap is let in.
- **Enrolment can be limited to one reader** (`device_id` on
  `magicband.enrol`, and **Enrol bands tapped on** on the page; with one
  reader the page uses it).
- **`magicband.play_show`** is limited to 12 shows a minute per reader,
  keeps the caller's context (the logbook shows who), and one reader failing
  no longer stops the rest. **`magicband.sync`** is limited to 6 a minute.
- **No "Factory Reset" button on the SCREEK BP2-POE:** any Home Assistant
  user could press it, and a reset board accepts the next client that brings
  a new encryption key.
- **"Test welcome"** no longer sends a tag scan to Home Assistant, so it
  can't set off automations that react to any tag.
- **CI:** releases are only made from commits on `main`, and the firmware
  published to the site on every `main` build (what the update entities
  download) now carries build-provenance attestations too.
- Tests now cover every admin-only action and check that only `send`,
  `sync`, `play_show` and `list_bridges` are open to every user. A few numbers
  on the page are escaped as well (defence in depth).

### MagicbHAnds page
- **The live twin looks like a park reader:** a brushed-silver ball with a
  flat grey face, seen slightly from the side, with the light ring around
  the face and an emblem in the middle. A page that hosts this one can set
  its own emblem (`window.MBH_READER_EMBLEM`, SVG in a 100 × 100 box; the
  face colour is `var(--tw-face)`).
- **LEDs or Diffused:** each reader card can show the ring as individual
  LEDs or as a smooth, diffused band of light (remembered in the browser).
- **The header shows the reader's ring, live,** in place of the "Status"
  line, with what it's doing and whether the page is live.

### Docs
- The build guides were checked against the real compact build: the
  35-LED ring's lead and how to tell its input end, the resistor and
  capacitor on the breadboard, 5.1 V at the ring, LED count 35, what to do
  if an update fails, and bands lighting up across the room. Builds that
  haven't been made yet are marked "reviewed, not built".
- `docs/security.md` lists the actions open to every user and their limits,
  and explains enrolment.

## [0.10.18] - 2026-11-20

### Reader
- **Seven more light shows** (17 in all): **Penguins** (gold arcs spinning
  round a black ring, then gold flashes with white sparkle), **Goal** (three
  hard red pulses, like the bands' red flash for a goal), **Aurora**, **Candy
  cane**, **Thunderstorm**, **Sunrise** and **Disco**. They're in Startup
  show, Show, `magicband.play_show` and the schedule blueprint.
- **Night now:** a new diagnostic sensor that's on while the night idle glow
  applies, so you can see Night mode (set hours or sunset to sunrise with its
  offsets) at work.

### MagicbHAnds page
- **Choosing from a drop-down takes effect on the page at once.** The page
  held off redrawing while a drop-down still had focus, so picking **Sunset
  to sunrise** didn't show its offset settings (or anything else) until you
  clicked elsewhere.
- The Night settings say whether the night glow is on now (from the
  reader), and explain the offsets: 120 = 2 hours after, −120 = 2 hours
  before.
- The live ring plays the new shows and follows the reader's Night now.

## [0.10.17] - 2026-11-20

### Reader
- **Ten light shows** for the ring, each a few seconds of colour: Rainbow
  rush, Fireworks, Comet chase, Colour parade, Twinkle, Heartbeat, Ocean,
  Fire, Pinwheel and Confetti (`components/magicband/shows.h`).
- **Startup show** (a setting): the show played when the reader starts:
  Off, Random or one show (default Rainbow rush).
- **Show** and **Play show**: pick a show (or Random) and press the button
  to play it; the reader's `play_show` action plays one by name. A band
  tapped during a show takes over the ring as usual.

### Home Assistant
- **`magicband.play_show`** plays a show (or Random) on every reader or the
  ones you pick, for automations and scripts.
- **Blueprint "MagicbHAnds: light show on a schedule"**: a show every hour
  (or every few hours) on the hour, between two times of day.

### MagicbHAnds page
- Each reader card has a **Play show** button, **Start-up show** and
  **Show** are in the Ring settings, and the live ring plays the shows too.
- **Recent taps** shows 10 at a time, with **Newer** and **Older** to page
  through the last 300.

### Fixed
- **Colours turned cool white as they faded.** The tail of the chasing
  circles, and the end of the welcome and denied fades, went faintly
  bluish-white in warm white (and other mixed colours): the ring's
  brightness curve keeps every channel that's on at one step or more, so a
  very dim warm white became one step of red, green and blue. Channels that
  should round to nothing now switch off, so fades keep their colour.
- **The wordmark was widely spaced on Windows.** The lighter Waltograph
  stored each letter's width twice and the two copies disagreed: Linux
  browsers read the right one, Windows read one nearly twice as wide (which
  also made the gaps between words look tiny). Both now match, and a test
  checks it.

## [0.10.16] - 2026-11-20

### Branding
- **One wordmark everywhere.** The lighter Waltograph is now a middle
  weight (thinned less) and keeps the original letter spacing (thinning had
  opened up the gaps), and the extra letter-spacing is gone. The MagicbHAnds
  page, the dashboard copy and the web installer use the same size (44-64
  px heading, 34 px section, 26 px sub-headings) and weight: the page's
  shared header style was making it bold and smaller. Logos re-rendered.

No firmware change.

## [0.10.15] - 2026-11-20

### MagicbHAnds page
- **Reader settings redesigned.** The reader card's fold-out, now **Ring and
  tap settings**, holds every ring and tap setting in groups: **Ring** (type,
  LED count, colour order, brightness), **Waiting for a band** (idle colour
  and glow), **Night** (glow and when: the set hours, or sunset and sunrise
  with their offsets; it shows tonight's times), **Checking a band**,
  **Welcome** (with a picture of the fade in, stay on and fade out) and
  **Denied**. Numbers show their units, and only the night settings that
  apply to the chosen night mode are shown.
- LED colour order is on the page now too.
- **A live twin of each reader's ring.** Each reader card shows its ring,
  with the real number of LEDs, doing what the real one does: the idle or
  night glow, the chasing circles while a band is read, then the welcome
  (with the person's name) or the denied pulses, the amber "waiting for Home
  Assistant" pulse, and a note while it plays a sound. It follows the
  reader's Ring light and settings, so it updates as soon as Home Assistant
  hears from the reader.

No firmware change.

## [0.10.14] - 2026-11-20

### Reader
- **Night mode:** the night idle glow can follow the sun. **Night mode**
  is **Set hours** (Night from / Night until, as before, the default) or
  **Sunset to sunrise**, moved by **Night starts after sunset** and **Night
  ends after sunrise** (minutes, -240 to 240; negative = before). The sun
  times come from Home Assistant's sun (`sun.sun`), are kept through
  restarts, and the set hours are used until they've arrived. Also on the
  MagicbHAnds page, in the reader's **Tap sequence** fold-out.

## [0.10.13] - 2026-11-19

Documentation only: the firmware and integration are unchanged.

### Docs
- Every guide checked against the current firmware and integration. The
  build walkthroughs cover Ring type, the new idle, night and welcome
  settings, and the RGBW option; the compact build's ring step is a full
  walkthrough (data path, power, capacitor, checks).
- The wired build's step numbers are fixed (Part 3 had a second "Step 3").
- The README, the integration guide and the installer page list the
  current features: schedules, band type, welcome colours, enrolment,
  history, battery reminders, Repairs, the admin-only page, no setup
  hotspot (change Wi-Fi over USB) and the band limits.
- Build status: the compact build's 35-LED ring is wired and lighting; its
  tap sequence is still to be confirmed.

## [0.10.12] - 2026-11-19

### Reader
- **Ring type:** a new setting for what the ring's LEDs are: **RGB** (as
  before, the default) or an SK6812 **RGBW** ring with **warm**, **neutral**
  or **cool white** LEDs. On an RGBW ring, White and Warm white come from the
  white LED (with a little colour added to make it warmer or cooler), and the
  power cap allows for its higher draw (18 LEDs' worth of everything on).
  One firmware fits every ring; changing the setting restarts the reader.
  The white mixes are first guesses, to be tuned on real rings.
- **The welcome has a shape now:** it comes on quickly (**Welcome fade
  in**, default 0.15 s), stays on (**Welcome hold**, default 1 s), then fades
  out (**Welcome fade out**, default 1 s), instead of one quick pulse.
  **Welcome pulses** repeats the whole thing. The denied pulses are
  unchanged (**Pulse time** now only sets those).
- All of these are also on the MagicbHAnds page, in the reader's **Tap
  sequence** fold-out.

## [0.10.11] - 2026-11-19

### Reader
- **Idle glow at night:** a second idle brightness (default 10 %) used
  between **Night from** and **Night until** (whole hours, default 22 to 6,
  in the reader's local time from Home Assistant). Set both hours the same to
  keep **Idle glow** all day. All three are also in the reader's **Tap
  sequence** fold-out on the MagicbHAnds page.
- **Warm white idle glow stays warm when dim.** Each colour channel keeps
  at least one step when dimmed, so a dim warm white became one step of
  red, green and blue: a cool white. The idle glow in Warm white is now mixed
  in the ring's own output steps (a "Warm glow" effect), keeping the same
  colour at any Idle glow, with a floor of 5 steps of red so it can.
- **LED count** now goes up to 100 (was 60). The power cap still holds
  full white to 24 LEDs' worth, so 100 LEDs run at up to 24 %.

### Branding
- A lighter cut of Waltograph (`waltograph42-light.otf`, made by
  `docs/images/make_light_font.py`) for the wordmark and headings, which were
  heavy and hard to read. The logos are re-rendered with it.
- The web installer uses the new branding: the purple and blue colours, the
  gradient strip and Waltograph headings (the font, its readme and licence
  are published with the site).

### Fixed
- The "didn't take the allowed list" repair no longer says the reader
  cleared its list when it only didn't answer in time.
- The reader's Tap sequence fold-out listed **Idle glow** twice.

## [0.10.10] - 2026-11-19

### Fixed
- **Reader 0.10.9 crashed at start-up**, so its update rolled itself back to
  the previous firmware. Restoring the new **Idle colour** setting at boot
  tried to light the ring before it was set up (the same cause as the 0.9.5
  boot loop). It now waits for the ring like the other settings; so do the
  "Home Assistant connected / disconnected" handlers. A new test fails if any
  setting can touch the ring before boot has finished.

## [0.10.9] - 2026-11-19

### Reader
- **Idle colour:** a new setting for the colour of the idle glow (the same
  colours as the others; default White). **Idle glow** still sets its
  brightness.
- **Circle tail:** a new setting for how many LEDs long the chasing trail is
  while a band is checked. 0 (the default) keeps the automatic length, a
  fifth of the ring.
- The "Home Assistant isn't connected" signal is now a slow amber pulse
  instead of a steady amber glow, so it can't be mistaken for an orange or
  yellow idle colour.
- Both settings are also on the MagicbHAnds page, in the reader's **Tap
  sequence** fold-out (with Idle glow).

## [0.10.8] - 2026-11-19

### New
- **Battery chart pop-out:** click a MagicBand+'s battery sparkline on the
  management page for a larger chart of its battery level over 7 or 30 days,
  with the current level, the lowest, when it was last charged and each
  reading (hover a point for its time). Esc, ✕ or a click outside closes it.
  A band whose battery hasn't changed in a week now shows a flat sparkline
  too, so there's always something to click.
- No firmware changes.

## [0.10.7] - 2026-11-19

### Fixed
- **Health tiles tidied:** five short tiles in one row (Wi-Fi, up for, CPU,
  memory, slowest loop) with the network and IP address on one line
  underneath; the restart reason is shortened ("updated", "power on",
  "crashed"), with the full text on hover; the SCREEK BP2-POE's uptime shows in
  the same format.
- **Recent taps** no longer says "Only administrators can see the tap
  history" when the page's host (such as a dashboards site with its own
  allowlist) refuses the action; it says what actually went wrong.
- No firmware changes.

## [0.10.6] - 2026-11-19

### Fixed
- **Health tiles:** CPU temperature is shown in Home Assistant's own unit
  (°F or °C) and judged on the Celsius value; it showed Fahrenheit readings as
  "°C" and marked them as too hot. "Loop time" is now "Slowest loop" and only
  turns amber from 1 s (red from 3 s): a few hundred ms is normal.
- No firmware changes (the version number is shared, so devices offer the
  same firmware as 0.10.6).

## [0.10.5] - 2026-11-19

### Health of the readers and bridges
- **Firmware (reader and bridge):** new diagnostic sensors: **Wi-Fi signal**,
  **Wi-Fi network**, **IP address**, **CPU temperature**, **Last restart**
  (changes only when it restarts) and **Reset reason**, **Free memory**,
  **Largest free block** and **Loop time**. They're throttled so Home
  Assistant's history stays small: Wi-Fi signal and temperature are sent when
  they change noticeably (3 dB, 1 °C) or every 5 minutes at most; memory and
  loop time every 5 minutes. The time comes from Home Assistant.
- **Management page:** each reader and bridge card shows these as health
  tiles (Wi-Fi strength, up for, CPU temperature, free memory, loop time, IP
  address), coloured when something looks wrong. The SCREEK BP2-POE's own
  sensors show the same way.

## [0.10.4] - 2026-11-19

New features, plus security fixes from a review of the whole project.

### New
- **Band schedules and expiry.** Each band can have a daily time window
  (overnight windows work), days of the week and an expiry date
  (`magicband.set_band_access`, or the band's **Manage** on the page).
  Outside them the band is denied, the readers' lists follow within a
  minute, and `magicband_tap` reports `allowed: false`.
- **Enrolment.** `magicband.enrol` (or **Enrol bands** next to a person):
  for up to 15 minutes, every band tapped that nobody owns is given to that
  person, numbered if you give a nickname. Bands that belong to someone are
  never taken.
- **Personal welcome.** Each person can have a welcome colour; readers
  (0.10.4 firmware) welcome their bands in it, on the ring and on their
  MagicBand+.
- **Tap history.** The management page lists recent taps (`magicband.history`,
  admins), taps appear in Home Assistant's logbook ("welcomed at Front
  Door"), and each MagicBand+ shows a 7-day battery sparkline.
- **Charge me reminders.** When a MagicBand+ drops to the reminder level
  (Configure → Settings, default 20 %), it shows in Repairs and fires
  `magicband_battery_low`; the new **MagicbHAnds: charge me reminder**
  blueprint sends a phone notification. It resets once the band is charged.
- **Repairs.** A reader that rejects the allowed list, a list too long for
  the readers, a reader offline for 15 minutes and low batteries show in
  Settings → Repairs and clear themselves.
- **Reader health.** Each reader has an **Allowed list** sensor (up to date,
  not applied, sent but unconfirmed on older firmware, offline); the page
  shows it with firmware updates; the reader's idle glow turns amber while
  Home Assistant isn't connected.
- **Diagnostics download** with band IDs shortened and names replaced.
- **CI** builds and tests every branch, not just `main`.

See [docs/security.md](docs/security.md) for the security model and what's
left.

### Breaking changes and things to do
- **Bridge and reader firmware: no fallback setup hotspot.** ESPHome's captive
  portal accepts a firmware upload from anyone who joins it, and the open
  hotspot could be forced on by knocking a board off Wi-Fi for 90 seconds.
  Wi-Fi is now set and changed over USB with the web installer.
- **Admins only:** the actions that change who's allowed in (`add_person`,
  `update_person`, `remove_person`, `assign_band`, `unassign_band`,
  `remove_band`, `link_bluetooth`, `unlink_bluetooth`, `forget_bluetooth`)
  and those that list band IDs (`list`, `list_bluetooth_bands`,
  `list_heard`), and the MagicbHAnds sidebar page. The new `set_band_access`,
  `enrol`, `stop_enrolment` and `history` are admin-only too.
- **Turn off "Allow the device to perform Home Assistant actions"** on
  readers (ESPHome → the reader → Configure). The setup guides used to ask for
  it, but tag scans don't need it, and it would let a tampered reader call any
  action.
- `magicband.send` only accepts MagicBand bridges in `bridges`.
- `magicband.sync` returns `readers`, `applied` and `failed` (was `readers`).

### Integration
- Automatic Bluetooth pairing no longer gives an NFC tag the Bluetooth band's
  owner. Before, tapping any tag while the only unlinked band heard belonged
  to someone made that tag theirs and let it in. That case now asks for a
  manual link; other automatic links show a notification.
- Only real NFC IDs (4, 7 or 10 bytes of hex) are recorded, assigned or
  allowed. The reader's "Test welcome" button (`TEST`) and malformed or
  non-ASCII IDs are ignored; older stored IDs that aren't valid stay but are
  never allowed.
- `magicband.send` writes the bridges' Command entities with the caller's
  context, so Home Assistant's permissions and logbook apply.
- Readers that reject the allowed list are reported (notification and the
  `sync` result), and so is a list too long for the readers to store.
- Limits against made-up radio traffic: at most 25 unclaimed Bluetooth bands
  (long-unheard ones are dropped, linked or owned bands never), 60
  `magicband_heard` events a minute, and 100 unassigned NFC bands.
- A damaged storage file no longer stops the integration loading; damaged
  entries are skipped.
- The management page escapes everything it shows from entity attributes.
- The sidebar panel loads the page only through Home Assistant's own
  authenticated fetch and never reads the login token itself.

- Taps only count from MagicBand readers that are ESPHome devices, and only
  those get the allowed list. Before, any device with the reader's model
  counted, and other integrations (a phone registered with the mobile app)
  let any user choose a model and name, so a user could fake a tap from a
  "reader" with your front-door reader's name; and any ESPHome device that
  declared a `set_known_bands` action got every allowed ID.
- A band's beacon counts at most once every 30 seconds per adapter, so a
  replayed beacon can't flood events and history or fake the battery level.
- Bluetooth bands linked automatically to a tag nobody owns count towards the
  cap; links to NFC bands that are dropped are removed; a band's type no
  longer keeps an unassigned band from being dropped (any user can set it).
- `magicband.send`: at most 30 commands a minute per bridge, and raw
  `command:` dicts get the same time limits as the normal fields.

### Firmware
- Reader: holds 213 allowed bands (7-byte IDs), up from 106. Updating
  clears the reader's stored list once; Home Assistant sends it again as soon
  as the reader reconnects.
- Reader: logs at INFO and never logs band IDs (it used to print the
  allowed list on its USB port at every sync, and every tag read).
- Reader: a new allowed list is checked in full. A malformed list, or one too
  long to store, empties the reader's list (everyone is
  denied) instead of leaving the old one in place, so a revoked band can't
  stay allowed, and the reader tells Home Assistant whether it applied it.
- Reader: "Allow last band" only accepts real NFC IDs.
- All boards: one command broadcasts for at most 60 seconds.

### Build and release
- GitHub Actions pinned to commit SHAs; checkouts don't keep credentials; the
  release adds signed build-provenance attestations.
- The web installer serves its own copy of ESP Web Tools, checked against a
  fixed hash, instead of loading it from unpkg.

## [0.10.3] - 2026-11-19

### Integration
- **Waltograph lettering.** The logo wordmark and the management page's
  title and section headings use the Waltograph font (by Justin Callaghan,
  mickeyavenue.com, Creative Commons NonCommercial-ShareAlike). The font
  ships with the integration, with its readme and licence, and the page
  loads it from `/magicbhands_static/fonts/`. Body text, cards and numbers
  keep the original fonts.

## [0.10.2] - 2026-11-19

### Integration
- **Group, sort and find bands on the management page.** Group by person,
  band type, where (closest bridge), nearby or away, battery, last reader,
  allowed in, or Bluetooth linked; sort by owner, name, last tap, last
  heard, battery (lowest first), most taps or signal; a search box. The
  choice is remembered in that browser.
- **More ways to send to the bands.** New one-tap buttons (purple, pink,
  white, rainbow, colour cycle, lightning, spin and buzz, buzz, stop) and a
  "build your own" panel with every effect the bridges support: colours,
  colour picker, light shows, buzz strength, how long, which LEDs, fade-out,
  stay on, and sending through one bridge only (just the bands in that room)
  or all of them.

## [0.10.1] - 2026-11-19

### Integration
- **Management page branding.** The page now carries the MagicbHAnds logo and
  wordmark (the "HA" in blue), the brand's purple accent and a
  purple-blue-teal strip across the header, in light and dark mode. The logo
  is inline, so it shows wherever the page is served.
- **Band type: MagicBand+ or standard MagicBand.** Each tapped band has a
  **Band type** select. A band linked to its Bluetooth is a MagicBand+
  automatically. Mark the original NFC-only bands as *Standard MagicBand*
  and they're no longer listed as "haven't been heard over Bluetooth yet"
  (they never will be), and tapping them no longer starts the Bluetooth
  pairing window, so they can't be paired by mistake with a MagicBand+
  that's nearby. The management page asks about bands whose type isn't
  known yet, with one-tap buttons, and shows the type on each band card.

## [0.10.0] - 2026-11-19

### Integration
- **MagicbHAnds management page in the sidebar.** Assign new bands, link a
  band's Bluetooth to its NFC side, see every band (owner, last tap, nearby,
  battery, closest bridge), manage people, send to every band, and set up
  the readers and bridges, all on one live page. It's the page built for
  the home-dashboards project, packaged with the integration. Turn the
  sidebar entry off under **Configure → Settings**.

### Fixed
- **"Updating a disabled entity" warning:** the reader's **Last band name**
  is no longer written while it's disabled.
- **Deprecated device lookups:** the integration no longer calls
  `DeviceRegistry.async_get_device`, which Home Assistant has deprecated.
- The Configure screens kept resetting the integration's settings; they
  now keep them.

## [0.9.14] - 2026-11-19

### Fixed
- **A second "MagicBand" device under the integration.** The reader's
  **Last band name** sensor could create a device of its own instead of
  joining the reader's device. It now joins the reader's device directly,
  and the stray device is removed on start-up (its sensor moves back to the
  reader, keeping its entity ID).

## [0.9.13] - 2026-11-18

### Reader
- **Band light-up power** setting (Configuration, −24 to 0 dBm, default
  −12 dBm, was a fixed 0 dBm). Every MagicBand+ in range reacts to the
  welcome's light-up, because a broadcast can't be addressed to one band;
  turning this down limits it to the band on the reader.


### Hardware
- **Compact build tested on the USB-C PD supply** with the Wago hubs. The
  guide's hub port table is the tested one, and a fix is added: keep a short
  ground jumper from the ESP32 to the breadboard (and from L− to the
  amplifier's ground row) as well as the hub wires, or the sound crackles.
  The wired builds' guide says the same.

## [0.9.12] - 2026-11-18

### Integration
- **Renamed to MagicbHAnds** everywhere you see the integration: its name in
  Home Assistant and HACS, the set-up screen, its hub device, notifications
  and messages, the docs and the dashboard. Existing installs are renamed
  on the next start. Unchanged: the `magicband` domain and actions,
  entity IDs (the hub's sensors keep `sensor.magicband_…`), and the names
  of the bands, bridges and readers themselves.
- The project itself is **MagicbHAnds** too: README, docs, web installer,
  release titles, and a new logo (light and dark, and the integration's
  brand images). The repository name and its URLs are unchanged.

## [0.9.11] - 2026-11-18

### SCREEK BP2-POE
- **Bluetooth proxy switch**, the same as the MagicBand Bridge's, so the
  proxy can be turned off on either kind of bridge. It defaults to on, so
  nothing changes until you turn it off. Scan Interval and Scan Window only
  restart scanning while the proxy is on.

## [0.9.10] - 2026-11-18

### Integration
- **Last band name on every reader's page:** whose band was last tapped
  ("Morgan's MagicBand+ (Villains)", or your name for it), with the NFC ID,
  person and whether it was let in as attributes. It's the integration's
  own sensor, attached to the reader's device.

### Reader
- The firmware's own sensor is now **Last band ID** (diagnostic): the raw
  NFC ID. Its entity ID is unchanged.

### Home Assistant
- **Management dashboard** (`homeassistant/dashboards/magicband.yaml`):
  bands, people, readers and bridges on one page, with buttons to manage
  people and bands, sync readers, and wake or ping bands. Built-in cards
  only; it finds everything by itself.

## [0.9.9] - 2026-11-18

### Reader
- **The tap sequence is configurable** on the reader's device page
  (Configuration): **Checking colour**, **Checking circles**, **Circle
  time**, **Welcome colour**, **Welcome pulses**, **Denied colour**,
  **Denied pulses** and **Pulse time**. Defaults match 0.9.8: two white
  circles, one green pulse, two red pulses.

## [0.9.8] - 2026-11-18

### Reader
- **New tap sequence on the ring:** two quick white circles chase round it
  while the band is checked (one circle every 0.5 s, whatever the LED
  count), then **one green pulse** for a welcome or **two red pulses** for
  a denied band. Replaces the spin, the 3-second solid green and the red
  strobe.

### Integration
- **Security:** adapter names (**Heard by**, **Closest**) no longer read
  other integrations' stored settings. They come from the device registry
  only: a USB adapter's device by its Bluetooth address, an ESPHome proxy's
  by its Wi-Fi MAC (an ESP32's Bluetooth address is its base MAC + 2).


### Hardware
- **Compact build tested** up to sound: power, NFC (bands read, known
  welcomed, unknown denied) and the amplifier at 100 %, on USB power. Its
  section in the wired build guide is now the tested step-by-step, with
  the checks and readings from the build, and a note on other tag
  automations reacting to band taps.

## [0.9.7] - 2026-11-18

### Fixed
- **Linking dropped the owner.** Linking a Bluetooth band that belonged to
  someone to an NFC band that didn't yet belong to anyone left the band with
  no owner, so readers denied it. The NFC band now takes the Bluetooth
  band's owner (if it already has an owner, that one is kept), and readers
  get the updated allowed list straight away.

## [0.9.6] - 2026-11-18

### Integration
- **Your names for bands are used everywhere.** If you rename a band's
  device in Home Assistant, that name now shows in **Link a band's
  Bluetooth**, the pairing notification, `list_bluetooth_bands` and the
  `magicband_band_seen` event, and works as `bluetooth_band` in actions.
- **Linking keeps the name.** Linking a renamed Bluetooth band to its NFC
  band gives the merged device the name you chose.

### Hardware
- **Compact (solderless) build:** the point-to-point layout on a 400-point
  half breadboard with jumpers, with its own diagram
  (`docs/reader-compact.svg`) and steps in the wired build guide.

## [0.9.5] - 2026-11-18

### Fixed
- **Reader boot loop** (crash at start-up, then safe mode after 10 tries).
  The LED count, colour order, brightness and idle glow settings restore
  their values during set-up and then touched the ring before its driver
  was ready. They now wait until boot has finished. Readers in safe mode
  need reinstalling once over USB from the web installer.

## [0.9.4] - 2026-11-17

### Integration
- **Heard by** and **Closest** on every band's device page: which bridge,
  proxy or adapter heard its latest beacon, and which heard it strongest in
  the last 20 minutes (a rough "which room"). Shown by their Home Assistant
  device names, so "Kitchen MagicBand Bridge" rather than a Bluetooth
  address. The Signal and Last seen attributes use the same names.

## [0.9.3] - 2026-11-17

### Integration
- **Battery confirmed.** Bands put on charge went from 50 and 72 to 98, so
  the beacon's level byte is the battery percentage. Each band's
  **Battery** sensor is now a real battery sensor (battery icon, battery
  views, low-battery automations); existing entity IDs are kept.

### Removed
- The custom reader PCB (KiCad design, its firmware build and its web
  installer button) is out of date, so it's been taken out for now. It's in
  the git history and in release v0.9.2 and earlier, for when it's revisited.

## [0.9.2] - 2026-11-17

### Integration
- Bands sending the longer `C0 13` beacon (seen from a band just switched
  on) are recognised too. Each band records which beacon forms it has sent.

## [0.9.1] - 2026-11-17

### Integration
- **One device per band.** Every band tapped on a reader now has its own
  device with a **Last tap** sensor (reader, scans, owner, allowed). Linking
  its Bluetooth side merges the two into one device: Last tap, Nearby, Last
  seen, Signal and Battery together, named after its label or owner.
  Unlinking splits them again. `magicband.list` includes each band's
  Bluetooth side.

## [0.9.0] - 2026-11-17

### Integration
- **Bands over Bluetooth.** Every MagicBand+ sends a status beacon about
  every 15 minutes. The integration now recognises each band from it,
  although its Bluetooth address changes every time, and gives each one a
  device: **Nearby** (presence), **Last seen**, **Signal** and **Battery
  (unconfirmed)**. Stored, so it survives restarts.
- **Pairing Bluetooth with NFC.** Tapping a band on a reader links it to the
  Bluetooth band heard in the next 20 minutes, when it's clear which one;
  otherwise link it under **Configure → Link a band's Bluetooth** or with
  `magicband.link_bluetooth`. A Bluetooth band can also be given straight
  to a person.
- New actions: `list_bluetooth_bands` (raw beacons, level history, changing
  bits), `link_bluetooth`, `unlink_bluetooth`, `forget_bluetooth`. New event:
  `magicband_band_seen`.
- The beacon format as far as it's understood is in docs/protocol.md.

### Fixed
- The 10-minute reader sync and the start-up sync ran their callbacks off
  Home Assistant's event loop (Home Assistant warns about this). They now
  run on the loop.


### Reader
- **LED count and colour order are now settings** on the reader's device
  page (Configuration: *LED count* 1–60, *LED colour order* GRB/RGB), so the
  web installer's firmware works with any ring or strip; no "Take control"
  needed.
- **LED brightness** (5–100 %) and **Idle glow** (0–100 %, 0 = off)
  settings, so the ring can be tuned after installing.
- **Step-by-step build guides** for the breadboard and for the terminal
  base and point-to-point builds (`build.md` in each folder), with a check
  after every stage. The specs, shopping list and diagrams are now written
  for generic parts: a CH224K USB-C PD trigger set to 5 V, a 5-pin
  MAX98357A amplifier kit on its own cable, a 35-LED WS2812B ring; Adafruit
  equivalents are listed alongside.
- **Automatic power cap:** above 24 LEDs the output is capped at
  24 ÷ count, so full white stays within the 20 W supply (e.g. a generic
  35-LED WS2812B ring runs at up to 68 %).

## [0.8.3] - 2026-11-17

### Integration
- **Band messages get their own history.** `magicband.list_heard` now also
  returns `bands`: the last 200 messages from bands, kept separately from the
  30 most recent messages of any kind. Your bridges' own commands fill that
  30-entry list within a minute, so band messages used to be pushed out
  before you could look.

### Also in this release
- The reader's `ring_color_order` setting, the shopping list's generic
  alternatives, and the new power and interface-board diagrams (see 0.8.2).

## [0.8.2] - 2026-11-17

### Fixed
- **SCREEK BP2-POE: "requested passive mode but is operating in active
  mode … needs to be power cycled".** Home Assistant now chooses each
  proxy's active or passive scanning (ESPHome integration → the device →
  Configure → Bluetooth scanning mode). The firmware's own Scan Active Mode
  switch overrode that choice, so it's been removed. Delete the old entity
  once it shows as unavailable. Scan Interval and Scan Window stay.

### Docs
- Bridge and BP2-POE guides: where to set active or passive scanning.
- **Shopping list** (`hardware/shopping-list.md`): exact Adafruit parts for
  all three reader builds, checked against Adafruit's product pages, and the
  three parts Adafruit doesn't sell. The builds now use them:
  - NeoPixel Ring 24 (the PN532 fits inside it).
  - 3 W 4 Ω enclosed speaker.
  - 470 Ω data resistor.
  - Snap-action connectors as the power hubs.
  - 22 AWG stranded power wiring.
  - HUSB238 USB-C PD breakout with the Raspberry Pi 27 W supply.
- **Diagrams for the terminal base and point-to-point builds**, with the
  interface board drawn hole for hole on an Adafruit Perma-Proto.
- Reader install steps: flash the bare ESP32 first; disconnect the ESP32's
  5 V before plugging in USB later.
- Flexible LED strip options linked from every reader build guide, and a
  new `ring_color_order` setting for strips that aren't GRB (Adafruit's
  silicone neon-like strip is RGB). The published firmware is unchanged
  (GRB).
- Shopping list: wire sets, solder, flux, heat shrink, Kapton tape, tools,
  and a wiring guide (wire type, colour, length limit and how to finish
  each connection).
- **Pictures instead of text diagrams:** a power distribution diagram for
  all builds (both USB-C PD board options, hubs, every branch with wire,
  length and current) and an interface board close-up with every wire in
  and out labelled. The wiring diagrams now name either power board.
- Shopping list: generic (non-Adafruit) alternatives and what to check for
  each, including a CH224K DIP-switch PD board set to 5 V.

## [0.8.1] - 2026-11-17

### Changed
- **The reader drives a single LED ring** (16 or 24 LEDs, set `ring_leds`).
  The Mickey head is gone, which keeps a reader within a 5 V 3 A USB-C
  supply. The ring glows white while waiting for a band.

### Hardware
- **Reviewed breadboard build** (`hardware/reader-breadboard/`), checked
  against the Espressif, Elechouse, TI, Worldsemi, Analog Devices and
  Adafruit documentation:
  - Corrected diagram: the ESP32 board's orientation and header spacing were
    wrong.
  - PN532 on 5 V with 4.7 kΩ I²C pull-ups.
  - LED and amplifier power straight from lever-connector hubs.
  - 330 Ω resistor at the ring end.
  - Rated capacitors, USB-C charger power (20 W or more), a current budget,
    and a staged build-and-test plan.
- **Terminal base and point-to-point builds** (`hardware/reader-wired/`)
  brought in line with the review, around a small perfboard interface board
  for the level shifter and I²C pull-ups.
- The custom PCB is parked until the breadboard build is proven.

## [0.8.0] - 2026-11-17

### Added
- **31 predefined scenes** on every bridge, reader and BP2-POE: a **Scene**
  select with **Play scene**, plus one-press buttons for Rainbow, Lightning,
  Colour cycle, Crossfade, Spin & buzz and Alternating. Also available as
  `magicband.send` with `effect: animation`. Sources: emcot.world and
  Haw8411/magic-band-plus-lights.
- **Fast mode** (on by default): every broadcast mixes in the park's
  `CC 03 00 01 00` "fast mode" ping, which is believed to make bands listen
  continuously, so effects start sooner and repeats land. Optional
  **Fast mode warm-up**, and a **Wake bands** button (`effect: wake`).
- **Hearing bands respond:** the integration listens through Home Assistant's
  Bluetooth adapters and proxies for anything with Disney's Bluetooth ID. It
  logs the device address, signal strength, which proxy heard it and how long
  after the last send, and adds a `magicband_heard` event, a *Last band
  heard* sensor and `magicband.list_heard`.

- **Ways to build the reader** (`hardware/README.md`): breadboard (start
  here), Lonely Binary terminal base, point-to-point wiring, and a custom
  26 × 58 mm PCB (KiCad, routed, Gerbers and JLCPCB files), with a checklist
  to prove each build works.
- **Reader firmware for the custom PCB** (`magicband-reader-pcb.yaml`), in
  the web installer, built in CI with its own update channel.

### Changed
- The integration's setup screen describes what it does.

## [0.7.1] - 2026-11-16

### Security
- **Bridge and reader connections to Home Assistant are now encrypted.**
  Home Assistant gives each board its own key the first time it connects, so
  there's nothing to set up. Boards on 0.7.0 may show a one-off "disabled
  transport encryption" notice: confirm it, then install this update, and
  encryption is switched back on.
- **Unencrypted network firmware uploads are no longer accepted** by the
  installer firmware. Updates come through Home Assistant's Firmware update
  entity. "Take control" in the ESPHome Device Builder adds its own
  password-protected uploads.

### Added
- **Published firmware for the SCREEK BP2-POE**, built from the same shared
  MagicBand code as the bridge and reader. Install it from the web installer
  or the Device Builder, with no secrets needed. Updates then arrive through
  Home Assistant like the other boards. PSRAM is enabled for update headroom.
- CI fails if the single-file BP2-POE config drifts from the shared add-on.

### Fixed
- Starting a release from the Actions page can no longer be cancelled by a
  later push.

### Integration
- No functional changes; version bumped to match.

## [0.7.0] - 2026-11-16

First release with proper version numbers. Everything before this was
development builds (bridge 0.1.0–0.5.2, reader 0.6.0, integration 0.1.0–0.2.0).

### Added
- **Two-part project:** the MagicBand Bridge (Bluetooth effects for
  MagicBand+) and the MagicBand Reader (NFC tap point for original MagicBands
  and MagicBand+), tied together by the MagicBand integration.
- **Web installer for the reader**, alongside the bridge: no secrets or YAML
  needed, Wi-Fi set up in the browser, and updates over Wi-Fi from Home
  Assistant.
- **Integration icons and logo**, shown in Home Assistant 2026.3 and later.
- **`magicband.send` action**, which finds every bridge itself, and
  `magicband.list_bridges`.
- **The integration installs the *MagicBand+ notification* blueprint** and
  keeps it updated, including a copy imported from GitHub.
- **GitHub Releases** with firmware and the integration attached; CI checks
  that all versions match.

### Changed
- The blueprint now uses `magicband.send` and needs the MagicBand integration.
- Reader: LED data moved to GPIO10 (matches the Lonely Binary terminal base),
  and the I2S LRC/BCLK pins were swapped (GPIO5/GPIO6) for straight breadboard
  wiring.
- Reader devices get a unique name (`magicband-reader-xxxxxx`), like bridges.

### Fixed
- **Firmware updates over Wi-Fi failing** on bridges: the PSRAM on N16R8
  boards is now enabled, leaving memory for the HTTPS download alongside
  Bluetooth. Bridges on 0.5.2 or earlier need one USB re-install from the web
  installer to get this fix.

## Development history (before 0.7.0)

- **Bridge 0.5.x:** alternating E1/E2 prefix (more reliable repeats),
  experimental "both" prefix mode, MagicBand light on by default.
- **Bridge 0.4.x:** Bluetooth proxy scanning paused while broadcasting,
  +20 dBm on ESP32-S3.
- **Bridge 0.3.x:** multiple bridges, Command entity, optional Bluetooth
  proxy, reusable add-on package, SCREEK BP2-POE config.
- **Bridge 0.2.0:** decoded timing, RGB colour light, LED masks, animations.
- **Bridge 0.1.0:** first web-installable firmware.
- **Reader 0.6.0:** NFC reader with LED ring, Mickey head, sounds, on-device
  known bands.
- **Integration 0.1.0–0.2.0:** people and bands, reader sync, `magicband.send`.
