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
  and ring outside), and decide in Home Assistant, not on the reader.

## Who can change who's allowed in

Everything that changes access (people, assigning bands, linking Bluetooth)
or lists band IDs (`list`, `list_bluetooth_bands`, `list_heard`) needs an
**administrator** in Home Assistant, and so does the MagicbHAnds sidebar
page. Other users can still use the bands (`magicband.send`) and see the
entities.

Home Assistant users who aren't administrators can still use the readers'
and bridges' own controls (response mode, "Allow last band", the Command
entity). The reader's own decision only drives its lights and sound; the
`magicband_tap` event's `allowed` comes from Home Assistant.

**Automatic Bluetooth pairing never changes access.** If linking a band would
give an NFC tag a new owner (and so let it in), it's left for an
administrator to confirm.

## Readers' allowed list

The integration sends the allowed list to every reader and each reader
replies whether it applied it. If a reader can't store the whole list (about
106 bands of 7 bytes) or the list is malformed, the reader **empties** its
list (denies everyone) rather than keep an old one, and Home Assistant shows
a "reader not updated" notification. A reader that's offline keeps its last
list until it reconnects.

## Devices and updates

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
  checked against the MD5 in the same manifest. That catches corruption, not a
  compromised site or repository: ESPHome has no firmware signing. Releases
  carry signed build-provenance attestations; check a download with
  `gh attestation verify <file> --repo Legal-Copy7045/Magic-bHAnds`.
- **The web installer** serves its own copy of ESP Web Tools, checked against
  a fixed hash when the site is built.
- **Building your own firmware** ("Take control") pulls the add-on and
  component from this repository's `main` branch at build time.

## Limits on what nearby radios can do

- At most 25 unclaimed Bluetooth bands are kept; beyond that, long-unheard
  ones are dropped and new ones ignored, so made-up beacons can't flood
  Home Assistant. Bands linked or given to someone are never dropped.
- At most 60 `magicband_heard` events a minute are fired.
- At most 50 unassigned NFC bands are kept.
- Only real NFC IDs (4, 7 or 10 bytes of hex) are recorded or allowed.
- A bridge broadcasts one command for at most 60 seconds.

## Privacy

Band IDs, who owns them, and Bluetooth beacon data (including from other
people's MagicBand+ passing by) are stored in Home Assistant, appear in
entity attributes and history, and are in backups. Anyone with a band's NFC ID
can copy the band, so treat Home Assistant backups and exports accordingly.

## Reporting a problem

Open a GitHub issue without exploit details and ask for a private contact,
or use GitHub's private vulnerability reporting if it's enabled.
