#pragma once
// Host mock of ESPHome 2026.10.2's light::ESPColorView and ESPColorCorrection
// (esp_color_view.h, esp_color_correction.h/.cpp): a view onto one LED's raw
// output bytes, written through the light's correction (power cap / LED
// brightness as max_brightness, the light's brightness as local_brightness,
// then the gamma table, rounding with "at least one step" for non-zero
// values). The white pointer is null on a ring without a white LED, exactly
// like the real view. The gamma table is generated from ESPHome's own
// light.generate_gamma_table() (gamma_table.h, written by host_tests.py).
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include "esphome/core/color.h"

namespace esphome {
namespace light {

class ESPColorCorrection {
 public:
  void set_max_brightness(const Color &m) { max_brightness_ = m; }
  void set_local_brightness(uint8_t b) { local_brightness_ = b; }
  void set_gamma_table(const uint16_t *t) { gamma_table_ = t; }
  uint8_t color_correct_red(uint8_t v) const { return gamma_correct_(esp_scale8_twice(v, max_brightness_.red, local_brightness_)); }
  uint8_t color_correct_green(uint8_t v) const { return gamma_correct_(esp_scale8_twice(v, max_brightness_.green, local_brightness_)); }
  uint8_t color_correct_blue(uint8_t v) const { return gamma_correct_(esp_scale8_twice(v, max_brightness_.blue, local_brightness_)); }
  uint8_t color_correct_white(uint8_t v) const { return gamma_correct_(esp_scale8_twice(v, max_brightness_.white, local_brightness_)); }

 protected:
  uint8_t gamma_correct_(uint8_t value) const {
    if (gamma_table_ == nullptr) return value;
    uint16_t table_value = gamma_table_[value];
    uint8_t result = (table_value + 128) / 257;
    if (result == 0 && table_value != 0) return 1;
    return result;
  }
  const uint16_t *gamma_table_{nullptr};
  Color max_brightness_{255, 255, 255, 255};
  uint8_t local_brightness_{255};
};

class ESPColorView {
 public:
  ESPColorView(uint8_t *red, uint8_t *green, uint8_t *blue, uint8_t *white, uint8_t *effect_data,
               const ESPColorCorrection *cc)
      : red_(red), green_(green), blue_(blue), white_(white), effect_data_(effect_data), color_correction_(cc) {}
  ESPColorView &operator=(const Color &rhs) {
    set(rhs);
    return *this;
  }
  void set(const Color &c) {
    *red_ = color_correction_->color_correct_red(c.r);
    *green_ = color_correction_->color_correct_green(c.g);
    *blue_ = color_correction_->color_correct_blue(c.b);
    if (white_ != nullptr) *white_ = color_correction_->color_correct_white(c.w);
  }
  uint8_t get_red_raw() const { return *red_; }
  uint8_t get_green_raw() const { return *green_; }
  uint8_t get_blue_raw() const { return *blue_; }
  uint8_t get_white_raw() const { return white_ == nullptr ? 0 : *white_; }

 protected:
  uint8_t *const red_;
  uint8_t *const green_;
  uint8_t *const blue_;
  uint8_t *const white_;
  uint8_t *const effect_data_;
  const ESPColorCorrection *color_correction_;
};

}  // namespace light
}  // namespace esphome
