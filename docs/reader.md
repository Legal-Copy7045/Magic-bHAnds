# MagicBand Reader

A park-style touch point for Home Assistant. Tap an **original MagicBand** or a
**MagicBand+** on it: the ring spins, Home Assistant gets the band's ID, the
ring and Mickey turn green with a chime, and a MagicBand+ also lights up green
and buzzes.

Config: [`esphome/magicband-reader.yaml`](../esphome/magicband-reader.yaml).

Inspired by
[foolishmortalbuilders/magicbandreader](https://github.com/foolishmortalbuilders/magicbandreader),
[dcivitano/Magic-Band-Reader](https://github.com/dcivitano/Magic-Band-Reader) and
[ncory/MagicReader](https://github.com/ncory/MagicReader). Like them, it
identifies bands by their NFC ID. Unlike them, it runs on one ESP32 with
ESPHome and connects to Home Assistant natively (Tags, entities, actions). No
code from those projects is used.

## How bands are read

Both band types contain a standard 13.56 MHz NFC chip (ISO 14443-A) with a
fixed ID, which is the same ID a phone app such as *NFC Tools* shows. The
reader only reads that ID, so no encrypted Disney data is involved. Original
MagicBands give a 7-byte ID like `04-53-65-2A-C0-5F-80`.

## Parts

| Part | Example | Notes |
|---|---|---|
| ESP32-S3 dev board | Lonely Binary / DevKitC-1 **N16R8** | Same board as the bridge |
| NFC reader | **PN532** module (Elechouse V3 or clone) | Set its DIP switches to **I2C** |
| LED ring | WS2812B ring, 24 LEDs | 12 or 16 also work: change `ring_leds` |
| Mickey head | WS2812B strip or rings, ~12 LEDs | Set `mickey_leds` |
| Amplifier | **MAX98357A** I2S board | Plus a 3 W 4–8 Ω speaker |
| Level shifter | 74AHCT125 (or a single SN74AHCT1G125) | 3.3 V → 5 V for the LED data line |
| Power | 5 V **3 A** supply | 36 LEDs at full white draw ~2 A |
| Odds and ends | 330 Ω resistor, 1000 µF capacitor | Resistor in series with LED data; capacitor across the LED 5 V/GND |

## Wiring

| ESP32-S3 pin | Goes to |
|---|---|
| **5V** | 5 V supply (+). Also the PN532 VCC, the MAX98357A VIN, the level shifter VCC and the LED 5 V |
| **GND** | Ground for everything (common ground is essential) |
| **GPIO8** | PN532 **SDA** |
| **GPIO9** | PN532 **SCL** |
| **GPIO4** | Level shifter input → 330 Ω → first LED of the **ring** **DIN** |
| **GPIO5** | MAX98357A **BCLK** |
| **GPIO6** | MAX98357A **LRC** |
| **GPIO7** | MAX98357A **DIN** |

- **LED chain order:** the ring comes first, then the ring's DOUT goes to the
  Mickey head's DIN. The firmware splits the chain into a **Ring** light and a
  **Mickey** light.
- **Power the LEDs from the 5 V supply directly**, not through the ESP32's
  USB.
- **Level shifter (74AHCT125):** tie its OE pin for the channel you use (1OE)
  to GND, and power it from 5 V.
- **Placement:** put the PN532 antenna in the centre of the ring, under the
  lid, with **no metal** between it and the band. Read range is a few
  centimetres through plastic.

## Install

1. In the **ESPHome Device Builder**: **+ New device**, then **Continue**,
   name it `magicband-reader`, choose **ESP32-S3**, then **Skip**.
2. **Edit** it and replace everything with the contents of
   `esphome/magicband-reader.yaml`. Change `ring_leds` and `mickey_leds` if
   your LED counts differ.
3. **Secrets:** make sure `wifi_ssid` and `wifi_password` exist, and add
   `reader_api_key` (generate one with
   `py -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"`).
4. **Install → Plug into this computer** for the first install over USB.
   After that, updates go over Wi-Fi.
5. Add it in Home Assistant when it's discovered.

## Using it with Home Assistant

**Name your bands.** Tap each band once, then go to **Settings → Tags**. Each
band appears with its ID: give it a name ("Steve's MagicBand+").

**React to a band.** Create an automation with the trigger **Tag → Steve's
MagicBand+**, for example to turn on the lounge lights.

**Entities on the reader:**

| Entity | What it does |
|---|---|
| **Ring**, **Mickey** | The LEDs as normal HA lights, so you can use them as a night light too |
| **Last band** | ID of the last band read |
| **Response mode** | *Welcome every band* (default, instant green), or *Ask Home Assistant* (see below) |
| **Light up MagicBand+** | Send green + buzz to a MagicBand+ on a successful read (default on) |
| **Sound** | Chimes on/off |
| **Test welcome** | Plays the welcome sequence without a band |
| plus the MagicBand bridge entities | MagicBand light, Buzz, Command, Prefix mode and so on |

### "Ask Home Assistant" mode: green for known bands, red for others

Set **Response mode** to *Ask Home Assistant*. The ring then spins until HA
answers. With no answer within 3 seconds, it shows red. Add an automation that
answers:

```yaml
alias: "MagicBand reader: allow known bands"
triggers:
  - trigger: event
    event_type: tag_scanned
    event_data:
      device_id: YOUR_READER_DEVICE_ID   # optional: only this reader
actions:
  - if:
      - condition: template
        value_template: >
          {{ trigger.event.data.tag_id in ['04-53-65-2A-C0-5F-80', '04-11-22-33-44-55-66'] }}
    then:
      - action: esphome.magicband_reader_accept
    else:
      - action: esphome.magicband_reader_deny
```

## Sounds

The reader plays simple built-in tones (RTTTL). You can change the tunes in
the `reader_welcome` and `reader_deny` scripts. Disney's own sounds aren't
included; play your own files from HA on another speaker if you want those.

## Notes

- The MagicBand+ feedback uses Bluetooth, so it reaches **any** MagicBand+
  nearby, not only the one on the reader. The reader transmits at 0 dBm (set
  `tx_power` under `magicband:`) to keep that local.
- Taps during a sequence are ignored; tap again once the reader is idle.
