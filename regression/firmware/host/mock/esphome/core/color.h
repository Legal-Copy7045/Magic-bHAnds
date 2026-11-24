#pragma once
// Host mock of esphome/core/color.h (ESPHome 2026.10.2): the parts the
// magicband component uses. esp_scale8 / esp_scale8_twice and the Color layout
// are copied from the real header; host_tests.py checks they still match it.
#include <cstdint>

namespace esphome {

inline static constexpr uint8_t esp_scale8(uint8_t i, uint8_t scale) {
  return (uint16_t(i) * (1 + uint16_t(scale))) / 256;
}
inline static constexpr uint8_t esp_scale8_twice(uint8_t i, uint8_t scale1, uint8_t scale2) {
  return (uint32_t(i) * (1 + uint32_t(scale1)) * (1 + uint32_t(scale2))) >> 16;
}

struct Color {
  union {
    struct {
      union { uint8_t r; uint8_t red; };
      union { uint8_t g; uint8_t green; };
      union { uint8_t b; uint8_t blue; };
      union { uint8_t w; uint8_t white; };
    };
    uint8_t raw[4];
    uint32_t raw_32;
  };
  constexpr Color() : raw_32(0) {}
  constexpr Color(uint8_t red, uint8_t green, uint8_t blue) : r(red), g(green), b(blue), w(0) {}
  constexpr Color(uint8_t red, uint8_t green, uint8_t blue, uint8_t white) : r(red), g(green), b(blue), w(white) {}
  bool operator==(const Color &rhs) const { return raw_32 == rhs.raw_32; }
  bool operator!=(const Color &rhs) const { return raw_32 != rhs.raw_32; }
  Color operator*(uint8_t scale) const {
    return Color(esp_scale8(red, scale), esp_scale8(green, scale), esp_scale8(blue, scale), esp_scale8(white, scale));
  }
  static const Color BLACK;
  static const Color WHITE;
};
inline constexpr Color Color::BLACK(0, 0, 0, 0);
inline constexpr Color Color::WHITE(255, 255, 255, 255);

}  // namespace esphome
