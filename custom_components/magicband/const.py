"""Constants for the MagicBand integration."""

DOMAIN = "magicband"

STORAGE_KEY = "magicband.registry"
STORAGE_VERSION = 1

# ESPHome readers are recognised by their project name
# (project: legal-copy7045.magicband-reader), which Home Assistant's ESPHome
# integration exposes as the device model.
READER_MODEL = "magicband-reader"
# ESPHome action on each reader that replaces its allowed list.
READER_SET_SERVICE_SUFFIX = "_set_known_bands"

EVENT_TAP = "magicband_tap"
# A Bluetooth advertisement with Disney's company ID was heard (see listener.py).
EVENT_HEARD = "magicband_heard"
DISNEY_COMPANY_ID = 0x0183

SIGNAL_UPDATED = f"{DOMAIN}_updated"
SIGNAL_PEOPLE_CHANGED = f"{DOMAIN}_people_changed"
SIGNAL_HEARD = f"{DOMAIN}_heard"
# A band was tapped on a reader: (reader device ID, band UID, allowed).
SIGNAL_READER_TAP = f"{DOMAIN}_reader_tap"
# A MagicBand+ status beacon was recognised (see beacons.py).
EVENT_BEACON = "magicband_band_seen"
SIGNAL_BEACON = f"{DOMAIN}_beacon"
SIGNAL_BEACON_NEW = f"{DOMAIN}_beacon_new"

SYNC_INTERVAL_MINUTES = 10

# The reader's ring colours (esphome/magicband-reader.yaml, set_ring_colour):
# a person's welcome colour is one of these.
READER_COLOURS = [
    "White", "Warm white", "Red", "Orange", "Yellow", "Green", "Cyan", "Blue", "Purple", "Pink", "Magenta",
]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CONF_BATTERY_LEVEL = "battery_reminder_level"
CONF_SNAPSHOT_DAYS = "snapshot_days"  # how long tap snapshots are kept (snapshots.py)
DEFAULT_BATTERY_LEVEL = 20
ATTR_WELCOME_COLOUR = "welcome_colour"

ATTR_BAND = "band"
ATTR_PERSON = "person"
ATTR_LABEL = "label"
ATTR_HA_PERSON = "ha_person"
ATTR_ALLOWED = "allowed"
ATTR_NAME = "name"
