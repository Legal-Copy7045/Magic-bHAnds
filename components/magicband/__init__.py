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
from esphome.core import TimePeriod
import esphome.final_validate as fv

CODEOWNERS = []
AUTO_LOAD = ["esp32_ble", "json"]
DEPENDENCIES = ["esp32"]

CONF_DURATION = "duration"
CONF_MIN_INTERVAL = "min_interval"
CONF_MAX_INTERVAL = "max_interval"
CONF_QUEUE_SIZE = "queue_size"

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
            cv.Optional(CONF_TX_POWER, default="9dBm"): cv.All(
                cv.decibel, cv.enum(esp32_ble.TX_POWER_LEVELS, int=True)
            ),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _validate,
)


def _final_validate(config):
    esp32_ble.validate_variant(config)
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
    cg.add(var.set_tx_power(config[CONF_TX_POWER]))

    request_bluetooth()
