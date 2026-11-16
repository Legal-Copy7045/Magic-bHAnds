"""`light: - platform: magicband` - an RGB light entity that colours nearby bands."""

import esphome.codegen as cg
from esphome.components import light
import esphome.config_validation as cv
from esphome.const import CONF_OUTPUT_ID

from . import MagicBand, magicband_ns

DEPENDENCIES = ["magicband"]

CONF_MAGICBAND_ID = "magicband_id"

MagicBandLight = magicband_ns.class_("MagicBandLight", light.LightOutput)

CONFIG_SCHEMA = light.RGB_LIGHT_SCHEMA.extend(
    {
        cv.GenerateID(CONF_OUTPUT_ID): cv.declare_id(MagicBandLight),
        cv.GenerateID(CONF_MAGICBAND_ID): cv.use_id(MagicBand),
    }
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_OUTPUT_ID])
    await light.register_light(var, config)
    parent = await cg.get_variable(config[CONF_MAGICBAND_ID])
    cg.add(var.set_parent(parent))
