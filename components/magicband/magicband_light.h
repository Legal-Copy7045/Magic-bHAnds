#pragma once

#include "esphome/components/light/light_output.h"
#include "esphome/components/light/light_state.h"
#include "magicband.h"

#ifdef USE_ESP32

namespace esphome::magicband {

/// RGB light entity that shows the chosen colour on nearby bands (always-on until turned off).
/// While a light effect is running, the effect sends its own packet and the colour isn't re-sent.
class MagicBandLight : public light::LightOutput {
 public:
  void set_parent(MagicBand *parent) { this->parent_ = parent; }

  light::LightTraits get_traits() override {
    auto traits = light::LightTraits();
    traits.set_supported_color_modes({light::ColorMode::RGB});
    return traits;
  }

  void write_state(light::LightState *state) override {
    bool on = state->current_values.is_on();
    if (on && state->get_current_effect_index() != 0)
      return;  // an effect is active; it drives the band itself
    float r, g, b;
    state->current_values_as_rgb(&r, &g, &b);
    this->parent_->request_light_state(on, static_cast<uint8_t>(r * 255.0f + 0.5f),
                                       static_cast<uint8_t>(g * 255.0f + 0.5f),
                                       static_cast<uint8_t>(b * 255.0f + 0.5f));
  }

 protected:
  MagicBand *parent_{nullptr};
};

}  // namespace esphome::magicband

#endif  // USE_ESP32
