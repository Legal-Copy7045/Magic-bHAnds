"""Firmware checks that need a person with the hardware (status "manual").

Each says exactly what to do and what to see. Nothing here is run
automatically: it would tap, light, sound, update or restart a device.
"""

MANUAL = [
    ("FW-300", "Signed official builds",
     "An official device refuses an unsigned update and installs a signed one",
     "1. On a bridge, reader or BP2 running an official release, 'Take control' in the ESPHome Device Builder (or build "
     "esphome/<device>.yaml yourself) and install the build over the air. 2. Expect the upload to fail and the device log "
     "to show the image signature check failing; the device keeps running the old version. 3. Install the next official "
     "release from Home Assistant's Firmware update entity: it installs and the device restarts on the new version. "
     "4. Flash your own build over USB with the web installer: it boots (no eFuses burned)."),
    ("FW-301", "Automatic updates",
     "Automatic updates installs a waiting release between 03:00 and 04:00 local time, by itself",
     "1. On a device one release behind, set 'Time zone' to your zone and turn 'Automatic updates' on. 2. Leave Home "
     "Assistant connected or not. 3. Next morning: the device is on the new release; its log (INFO) shows the update "
     "after 03:00 local. 4. With the switch off, nothing installs."),
    ("FW-302", "Refused-tap lockout",
     "Refused taps lock the reader out, show it, and end on time",
     "1. Reader with 'Refused-tap lockout' on, Lockout after 3, Lockout window 60 s, Lockout time 1 min. 2. Tap a band "
     "that isn't allowed 3 times within a minute. 3. Expect: the ring pulses slowly in red, 'Tap lockout' turns on, the "
     "log warns '3 refused taps', and a tap of an allowed band is ignored (log: 'Tap ignored: refused-tap lockout', no "
     "magicband_tap event). 4. After 1 minute (or turning the switch off) taps work again and the idle glow returns. "
     "5. 'Test welcome' presses never count towards the lockout."),
    ("FW-303", "Reader pairing",
     "First pairing needs a tap on the reader",
     "1. Erase a reader over USB (web installer, Erase device), flash, add it. 2. MagicbHAnds asks (Repairs) to tap a band "
     "within 2 minutes and the ring breathes blue. 3. Tap any band: 'Paired with MagicbHAnds' turns on, the ring shows a "
     "green welcome, no tag event is fired for that tap. 4. Repeat without tapping: after 2 minutes the request expires "
     "and the ring stops breathing blue, even if the integration asked again meanwhile."),
    ("FW-304", "Ring colours when dim (put_dimmed)",
     "Warm white, orange and pink stay their colour when dim on a real ring",
     "1. RGB WS2812 ring: Idle colour Warm white, Idle style Circle, Idle glow 30 %, LED brightness 100 %. The circle's tail "
     "fades warm (no red or bluish-white LEDs near its end). 2. Repeat with Orange and Pink, and with Idle glow 10 %. "
     "3. LED brightness 10 %: warm white is about one output step; it shows as a dim yellowish (red and green on), never "
     "plain red (FW-107). "
     "4. RGBW ring with Ring type RGBW warm white: the white LED carries Warm white; other colours leave it off."),
    ("FW-305", "Idle circle",
     "Idle circle settings on a real ring",
     "With Idle style Circle: Idle circle heads 1-4 shows that many evenly spaced heads; Idle circle tail 1 shows single "
     "LEDs; tail 0 shows a fifth of the ring; Idle tail fade 0 fades out, 100 is a solid bar; direction Reverse runs the "
     "other way; LED count 1-8 still runs without freezing."),
    ("FW-306", "Light shows",
     "Every light show plays on the ring as on the page's live twin, and ends dark",
     "1. For each show in 'Show', press 'Play show' with the MagicbHAnds page's reader card open. 2. The ring and the "
     "page's twin match. 3. Each show fades to dark before the idle glow returns (Heartbeat: three beats, then dark)."),
    ("FW-307", "Sound at night",
     "Sound at night Quieter lowers and restores the volume",
     "1. 'Sound at night' Quieter, Night volume 20 %, Night from/until around the current time. 2. When night starts the "
     "speaker volume drops to 20 %; tap: the tap-in sound is quieter. 3. Change the volume by hand during the night: it "
     "stays. 4. In the morning the day volume returns. 5. Restart during the night: the morning still restores the day volume."),
    ("FW-308", "Band IDs not logged",
     "The reader's USB log and Home Assistant device log never show a band ID",
     "1. Connect the reader's UART port, open the log (web installer Logs, or ESPHome logs). 2. Tap allowed and unknown "
     "bands, press Allow/Forget last band, sync from MagicbHAnds. 3. No NFC ID (hex like 04A1B2...) appears in the log."),
    ("FW-309", "Time zone setting",
     "Changing 'Time zone' applies at once to night mode and the update window",
     "1. Reader with Night from 22 / until 6. 2. Set 'Time zone' to a zone where it's currently 23:00. 3. Within a minute "
     "'Night' turns on and the idle glow switches to the night setting; set it back and it turns off."),
    ("FW-310", "Bridge airtime budget",
     "A bridge flooded with commands waits for airtime and keeps proxying Bluetooth",
     "1. Send a 60 s always-on command, then 30 more commands quickly (magicband.send from a script). 2. The bridge log "
     "warns 'Broadcasting too much: waiting for airtime'. 3. Its Bluetooth proxy keeps reporting advertisements (other "
     "BLE sensors keep updating) and the queued commands play out over the next minutes."),
    ("FW-311", "No setup hotspot",
     "No fallback hotspot when Wi-Fi is lost",
     "1. Turn the Wi-Fi access point off (or move the bridge/reader out of range) for 3 minutes. 2. Scan for Wi-Fi "
     "networks: no network named after the device appears. 3. Restore Wi-Fi: it reconnects by itself."),
    ("FW-313", "Sound at night",
     "After a power cut at night the start-up sound respects 'Sound at night'",
     "1. Reader with 'Sound at night' Off and Night from/until around the current time. 2. Unplug it for 10 s and plug "
     "it back in (a power cut, not Restart). 3. The start-up show plays; no start-up sound. 4. Same with Sound at night "
     "Normal: the start-up sound plays (within 20 s of the show). 5. With Wi-Fi off at start-up and Sound at night "
     "Quieter: no sound after 20 s."),
    ("FW-314", "Welcome sounds",
     "A person's own welcome sound with Home Assistant down: the reader's chime plays",
     "1. Give a person a welcome sound in MagicbHAnds and sync. 2. Stop Home Assistant (or block it from the reader). "
     "3. Tap their band: the reader plays its own tap-in chime. 4. With Home Assistant back, the person's sound plays "
     "and the chime doesn't."),
    ("FW-315", "Refused-tap lockout",
     "'Tap lockout' is off, not unknown, after a restart",
     "1. Reader with 'Refused-tap lockout' on. 2. Restart it. 3. In Home Assistant 'Tap lockout' shows Off (OK), not "
     "Unknown."),
    ("FW-316", "Ring effects",
     "Changing ring settings during a tap doesn't cut off the welcome",
     "1. Tap an allowed band and, during the welcome, change 'LED brightness', 'LED count', 'LED colour order' or "
     "'Idle glow' from Home Assistant. 2. The welcome pulses finish; the idle glow returns afterwards in the new setting."),
    ("FW-317", "Night mode",
     "Sunset to sunrise follows a Time zone change straight away",
     "1. Night mode 'Sunset to sunrise', Time zone your own. 2. Set Time zone to one where it's currently between sunset "
     "and sunrise at Home Assistant's location (e.g. 8 hours away). 3. 'Night now' changes within a minute, without "
     "waiting for sun.sun to update; set it back and it returns."),
    ("FW-318", "Unknown-band tag scan limit",
     "A burst of unknown tags reaches Home Assistant only at the documented rate",
     "1. Reader in 'Known bands only'. 2. Tap 10 different tags that aren't on its list within a minute (cards, fobs). "
     "3. Home Assistant gets 6 tag scans (Settings, Tags; or the tag_scanned events); the reader log warns 'Unknown band "
     "not sent to Home Assistant' for the rest; every tap still gets the denied sequence. 4. An allowed band tapped in "
     "between is always sent and welcomed."),
    ("FW-312", "No factory-reset button",
     "BP2-POE in Home Assistant has no Factory Reset entity",
     "1. Open the BP2-POE device in Home Assistant. 2. There's no 'Factory reset' or 'Safe Mode Boot' button ('Reboot "
     "Device' is expected; after updating from an older release delete the leftover unavailable 'Safe Mode Boot' "
     "entity). 3. Bands light up from the BP2 over Ethernet with magicband.send."),
]


def results() -> list[dict]:
    return [dict(id=i, feature=f, check=c, status="manual", detail=steps) for i, f, c, steps in MANUAL]
