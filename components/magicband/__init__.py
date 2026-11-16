"""ESPHome external component: broadcast MagicBand+ BLE effect commands.

The ESP32 acts as a non-connectable BLE advertiser. MagicBand+ bands within
range listen for advertisements carrying Disney's manufacturer ID (0x0183)
and play the encoded light / haptic effect. No pairing is involved.
"""

import esphome.codegen as cg
from esphome.components import esp32_ble
from esphome.components.esp32 import request_bluetooth
from esphome.components.esp32_ble import CONF_BLE_ID
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_TX_POWER
from esphome.components.esp32 import get_esp32_variant
from esphome.components.esp32.const import VARIANT_ESP32C3, VARIANT_ESP32S3
from esphome.core import TimePeriod
import esphome.final_validate as fv

CODEOWNERS = []
AUTO_LOAD = ["esp32_ble", "json"]
DEPENDENCIES = ["esp32"]

CONF_DURATION = "duration"
CONF_MIN_INTERVAL = "min_interval"
CONF_MAX_INTERVAL = "max_interval"
CONF_QUEUE_SIZE = "queue_size"
CONF_PAUSE_SCANNING = "pause_scanning"
CONF_ALTERNATE_PREFIX = "alternate_prefix"
CONF_PREFIX_MODE = "prefix_mode"
PREFIX_MODES = {"off": 0, "alternate": 1, "both": 2}

# ESP32-S3/C3 controllers number power levels from -24 dBm (index 0) up to
# +20 dBm (index 15) in 3 dB steps; the original ESP32 goes -12..+9 dBm.
EXTENDED_POWER_VARIANTS = (VARIANT_ESP32S3, VARIANT_ESP32C3)


def _max_power():
    return 20 if get_esp32_variant() in EXTENDED_POWER_VARIANTS else 9


def _validate_tx_power(value):
    if isinstance(value, str) and value.strip().lower() == "max":
        return "max"
    return cv.decibel(value)


def _power_index(dbm):
    """dBm -> esp_power_level_t index for this variant."""
    if get_esp32_variant() in EXTENDED_POWER_VARIANTS:
        allowed = list(range(-24, 19, 3)) + [20]
        if dbm not in allowed:
            raise cv.Invalid(f"tx_power on this chip must be one of {allowed} dBm or 'max'")
        return 15 if dbm == 20 else (dbm + 24) // 3
    allowed = list(range(-12, 10, 3))
    if dbm not in allowed:
        raise cv.Invalid(f"tx_power on this chip must be one of {allowed} dBm or 'max'")
    return (dbm + 12) // 3

# Components that drive BLE advertising through ESPHome's own advertising
# manager. This component drives the GAP layer directly, so the two would fight.
CONFLICTING_COMPONENTS = ("esp32_ble_beacon", "esp32_improv", "esp32_ble_server")

magicband_ns = cg.esphome_ns.namespace("magicband")
MagicBand = magicband_ns.class_("MagicBand", cg.Component)

_interval = cv.All(
    cv.positive_time_period_milliseconds,
    cv.Range(min=TimePeriod(milliseconds=20), max=TimePeriod(milliseconds=10240)),
)


def _validate(config):
    if config[CONF_MIN_INTERVAL] > config[CONF_MAX_INTERVAL]:
        raise cv.Invalid("min_interval must be <= max_interval")
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MagicBand),
            cv.GenerateID(CONF_BLE_ID): cv.use_id(esp32_ble.ESP32BLE),
            # How long each command is broadcast for. Bands only scan
            # periodically, so a burst of a couple of seconds is reliable.
            cv.Optional(CONF_DURATION, default="2s"): cv.All(
                cv.positive_time_period_milliseconds,
                cv.Range(
                    min=TimePeriod(milliseconds=100), max=TimePeriod(seconds=30)
                ),
            ),
            cv.Optional(CONF_MIN_INTERVAL, default="20ms"): _interval,
            cv.Optional(CONF_MAX_INTERVAL, default="40ms"): _interval,
            cv.Optional(CONF_QUEUE_SIZE, default=8): cv.int_range(min=1, max=32),
            # "max" = +20 dBm on ESP32-S3/C3, +9 dBm on the original ESP32.
            cv.Optional(CONF_TX_POWER, default="max"): _validate_tx_power,
            # Pause Bluetooth-proxy scanning while broadcasting, so the radio
            # spends the broadcast on the bands (resumes afterwards).
            cv.Optional(CONF_PAUSE_SCANNING, default=True): cv.boolean,
            # Alternate an E1 00 / E2 00 prefix on each command. Seen in park
            # captures; in testing it makes repeated commands more reliable.
            # Older on/off form of prefix_mode (true = alternate, false = off).
            cv.Optional(CONF_ALTERNATE_PREFIX): cv.boolean,
            # off / alternate (flip E1/E2 per command, default) / both
            # (experimental: also flip within each burst).
            cv.Optional(CONF_PREFIX_MODE): cv.one_of(*PREFIX_MODES, lower=True),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _validate,
)


def _final_validate(config):
    esp32_ble.validate_variant(config)
    dbm = config[CONF_TX_POWER]
    _power_index(_max_power() if dbm == "max" else int(dbm))
    full = fv.full_config.get()
    for comp in CONFLICTING_COMPONENTS:
        if comp in full:
            raise cv.Invalid(
                f"magicband drives BLE advertising directly and cannot be used "
                f"together with '{comp}'"
            )
    return config


FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    parent = await cg.get_variable(config[CONF_BLE_ID])
    esp32_ble.register_gap_event_handler(parent, var)

    cg.add(var.set_duration(config[CONF_DURATION]))
    cg.add(var.set_min_interval(config[CONF_MIN_INTERVAL]))
    cg.add(var.set_max_interval(config[CONF_MAX_INTERVAL]))
    cg.add(var.set_queue_size(config[CONF_QUEUE_SIZE]))
    dbm = config[CONF_TX_POWER]
    dbm = _max_power() if dbm == "max" else int(dbm)
    cg.add(var.set_tx_power(cg.RawExpression(f"static_cast<esp_power_level_t>({_power_index(dbm)})"), dbm))
    cg.add(var.set_pause_scanning(config[CONF_PAUSE_SCANNING]))
    mode = config.get(CONF_PREFIX_MODE)
    if mode is None:
        mode = "alternate" if config.get(CONF_ALTERNATE_PREFIX, True) else "off"
    cg.add(var.set_prefix_mode(PREFIX_MODES[mode]))

    request_bluetooth()
