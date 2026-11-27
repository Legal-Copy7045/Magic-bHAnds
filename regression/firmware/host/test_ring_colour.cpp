// ring_colour() (components/magicband/shows.h) through ESPHome's own LightColorValues: what the
// reader's ring_on hands the light call is what reaches the LEDs (RGBW rings' white LED included).
#include "test_common.h"
#include "esphome/components/light/light_color_values.h"
#include "esphome/components/magicband/shows.h"

using namespace esphome;
using hosttest::fmt;
using hosttest::result;

struct Rgbw {
  float r, g, b, w;
};
// What the LEDs get after ESPHome's normalize_color() and as_rgbw(), at full brightness.
static Rgbw esphome_out(light::ColorMode mode, float r, float g, float b, float cb, float w) {
  light::LightColorValues v;
  v.set_color_mode(mode);
  v.set_state(1.0f);
  v.set_brightness(1.0f);
  v.set_red(r), v.set_green(g), v.set_blue(b), v.set_color_brightness(cb), v.set_white(w);
  v.normalize_color();
  Rgbw o{};
  v.as_rgbw(&o.r, &o.g, &o.b, &o.w);
  return o;
}
static Rgbw via_reader(light::ColorMode mode, float r, float g, float b, float w) {
  const auto rc = magicband::ring_colour(r, g, b);
  return esphome_out(mode, rc.r, rc.g, rc.b, rc.strength, w);
}
static bool near(float a, float b) { return std::fabs(a - b) < 1e-4f; }

int main() {
  struct Entry {
    const char *ring, *name;
    float r, g, b, w;
  };
  // set_ring_colour's RGBW entries (White and Warm white on each ring type) and a few plain colours.
  const Entry rgbw[] = {
      {"warm", "Warm white", 0, 0, 0, 1},       {"warm", "White", 0, 0.15f, 0.35f, 1},
      {"neutral", "Warm white", 0.6f, 0.2f, 0, 0.8f}, {"neutral", "White", 0, 0, 0, 1},
      {"cool", "Warm white", 1, 0.35f, 0, 0.6f},  {"cool", "White", 0, 0, 0, 1},
      {"any", "Red", 1, 0, 0, 0},                 {"any", "Purple", 0.5f, 0, 1, 0},
      {"any", "Locked out", 1, 0, 0, 0},          {"any", "Offline amber", 1, 0.45f, 0, 0},
  };
  // FW-228: on an RGBW ring the LEDs get exactly the chosen mix: a white-LED colour lights only the white LED
  {
    std::string why;
    for (auto &e : rgbw) {
      const Rgbw o = via_reader(light::ColorMode::RGB_WHITE, e.r, e.g, e.b, e.w);
      if (!near(o.r, e.r) || !near(o.g, e.g) || !near(o.b, e.b) || !near(o.w, e.w))
        why += fmt("%s ring %s: got %.3f/%.3f/%.3f/%.3f, want %.3f/%.3f/%.3f/%.3f; ", e.ring, e.name, o.r, o.g, o.b, o.w, e.r,
                   e.g, e.b, e.w);
    }
    // The bug this replaces: the old call (colour as is, no colour brightness) lit warm white as full RGB white too.
    const Rgbw old = esphome_out(light::ColorMode::RGB_WHITE, 0, 0, 0, 1.0f, 1.0f);
    const bool old_bug = near(old.r, 1) && near(old.g, 1) && near(old.b, 1);
    result("FW-228", why.empty() && old_bug,
           why.empty() ? fmt("%zu colours exact; warm-white ring's Warm white = white LED only (the old call gave RGB %.0f/%.0f/%.0f "
                             "as well)", sizeof rgbw / sizeof rgbw[0], old.r, old.g, old.b)
                       : why);
  }
  // FW-229: RGB rings get the same colours as before; bad input (NaN, out of range, black) is safe
  {
    std::string why;
    const float table[][3] = {{1, 1, 1}, {1, 0.7f, 0.35f}, {1, 0.35f, 0}, {0, 1, 1}, {0.5f, 0, 1}, {1, 0.2f, 0.5f}};
    for (auto &t : table) {
      const Rgbw o = via_reader(light::ColorMode::RGB, t[0], t[1], t[2], 0);
      const Rgbw before = esphome_out(light::ColorMode::RGB, t[0], t[1], t[2], 1.0f, 0);
      if (!near(o.r, before.r) || !near(o.g, before.g) || !near(o.b, before.b) || !near(o.w, 0))
        why += fmt("RGB %.2f/%.2f/%.2f changed; ", t[0], t[1], t[2]);
    }
    const auto n = magicband::ring_colour(NAN, -1.0f, 2.0f);
    if (!(near(n.r, 0) && near(n.g, 0) && near(n.b, 1) && near(n.strength, 1))) why += "NaN/out-of-range not clamped; ";
    const auto k = magicband::ring_colour(0, 0, 0);
    if (!near(k.strength, 0)) why += "black has strength; ";
    result("FW-229", why.empty(), why.empty() ? "RGB ring unchanged for the colour table; NaN, negative, >1 and black handled" : why);
  }
  return 0;
}
