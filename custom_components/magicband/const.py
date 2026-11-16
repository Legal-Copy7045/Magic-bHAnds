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

SIGNAL_UPDATED = f"{DOMAIN}_updated"
SIGNAL_PEOPLE_CHANGED = f"{DOMAIN}_people_changed"

SYNC_INTERVAL_MINUTES = 10

ATTR_BAND = "band"
ATTR_PERSON = "person"
ATTR_LABEL = "label"
ATTR_HA_PERSON = "ha_person"
ATTR_ALLOWED = "allowed"
ATTR_NAME = "name"
