// The ring power budget and the full-power test's steps (components/magicband/power.h).
#include "test_common.h"
#include "esphome/components/magicband/power.h"

using namespace esphome;
using hosttest::fmt;
using hosttest::result;

static bool near(float a, float b) { return std::fabs(a - b) < 1e-5f; }

// A stand-in for ESPHome's LightState/LightColorValues, enough for shown_elements.
struct FakeValues {
  bool on = true;
  float r = 1, g = 1, b = 1, w = 0, state = 1, bright = 1;
  bool is_on() const { return on; }
  void set_state(float s) { state = s; }
  void set_brightness(float v) { bright = v; }
  void as_rgbw(float *o_r, float *o_g, float *o_b, float *o_w) const {
    *o_r = state * bright * r, *o_g = state * bright * g, *o_b = state * bright * b, *o_w = state * bright * w;
  }
};
struct FakeLight {
  FakeValues remote_values;
  std::string effect = "None";
  std::string get_effect_name() const { return effect; }
};

int main() {
  // FW-230: power_cap keeps full white within the budget: the old fixed cap at the default
  {
    std::string why;
    for (int n = 1; n <= 100; n++) {
      const float old_rgb = n > 24 ? 24.0f / n : 1.0f, old_rgbw = n > 18 ? 18.0f / n : 1.0f;
      if (!near(magicband::power_cap(n, false, 24), old_rgb)) why += fmt("RGB n=%d differs from 24/n; ", n);
      if (!near(magicband::power_cap(n, true, 24), old_rgbw)) why += fmt("RGBW n=%d differs from 18/n; ", n);
      for (int b = 12; b <= 35; b++) {
        const float rgb = magicband::power_cap(n, false, b) * n, rgbw = magicband::power_cap(n, true, b) * n * 80.0f / 60.0f;
        if (rgb > b + 1e-3f || rgbw > b + 1e-3f) why += fmt("n=%d budget %d over (%.2f/%.2f); ", n, b, rgb, rgbw);
      }
    }
    if (!near(magicband::power_cap(35, false, 35), 1.0f)) why += "35 LEDs at budget 35 still capped; ";
    result("FW-230", why.empty(), why.empty() ? "default 24 = the old cap (24/n, RGBW 18/n) for 1-100 LEDs; every budget 12-35 keeps full white within it" : why);
  }
  // FW-231: settings out of range are safe (NaN, 0, 1000, negative) and stay within 12-35
  {
    std::string why;
    const float bad[] = {NAN, INFINITY, -INFINITY, 0, -5, 11, 36, 1000};
    for (float b : bad) {
      const float v = magicband::power_budget(b);
      if (!(v >= 12 && v <= 35)) why += fmt("%f -> %f; ", b, v);
      const float c = magicband::power_cap(50, false, b);
      if (!(c > 0 && c <= 35.0f / 50 + 1e-6f)) why += fmt("cap for %f is %f; ", b, c);
    }
    if (!near(magicband::power_budget(NAN), 24)) why += "NaN isn't the default; ";
    result("FW-231", why.empty(), why.empty() ? "NaN/inf give 24, out-of-range values clamp to 12-35, the cap stays within 35/n" : why);
  }
  // FW-232: test steps: 24 up to 35, stopping once a step no longer scales the ring; nothing for a small ring
  {
    std::string why;
    auto steps = [](int n, bool rgbw) {
      std::string s;
      for (int i = 0; i < 20; i++) {
        const int v = magicband::power_test_step(n, rgbw, i);
        if (!v) break;
        s += std::to_string(v) + " ";
      }
      return s;
    };
    const struct {
      int n;
      bool rgbw;
      const char *want;
    } cases[] = {{35, false, "24 26 28 30 32 35 "}, {28, false, "24 26 28 "}, {24, false, "24 "}, {12, false, "24 "},
                 {35, true, "24 26 28 30 32 35 "}, {24, true, "24 26 28 30 32 "}, {18, true, "24 "}, {100, false, "24 26 28 30 32 35 "}};
    for (auto &c : cases)
      if (steps(c.n, c.rgbw) != c.want) why += fmt("n=%d%s: [%s] want [%s]; ", c.n, c.rgbw ? " RGBW" : "", steps(c.n, c.rgbw).c_str(), c.want);
    if (magicband::power_test_step(35, false, -1) || magicband::power_test_step(35, false, 99)) why += "out-of-range index gives a step; ";
    result("FW-232", why.empty(), why.empty() ? "steps 24..35 for big rings, stop at the first uncapped step, one step for small rings, bad index ends" : why);
  }
  // FW-233: after a reset during a step, the budget is the step below it (20 if the first step failed)
  {
    std::string why;
    const int want[][2] = {{24, 20}, {26, 24}, {28, 26}, {30, 28}, {32, 30}, {35, 32}, {1000, 35}, {-3, 20}};
    for (auto &w : want)
      if (magicband::power_budget_after_reset(w[0]) != w[1])
        why += fmt("reset at %d -> %d, want %d; ", w[0], magicband::power_budget_after_reset(w[0]), w[1]);
    result("FW-233", why.empty(), why.empty() ? "reset at 24 keeps 20, at 26..35 the step below; odd values stay within 12-35" : why);
  }
  // FW-235: the cap follows the colour shown: red and green run at full on a 35-LED ring at the default budget,
  // white is scaled as before, RGBW warm white (white element alone) runs at full
  {
    std::string why;
    struct C {
      const char *name;
      bool rgbw;
      float r, g, b, w, want;
    } cs[] = {
        {"Red (deny)", false, 1, 0, 0, 0, 1.0f},           {"Green (accept)", false, 0, 1, 0.3f, 0, 1.0f},
        {"White RGB", false, 1, 1, 1, 0, 24.0f / 35},      {"Red RGBW", true, 1, 0, 0, 0, 1.0f},
        {"Warm white, warm RGBW", true, 0, 0, 0, 1, 1.0f}, {"White, warm RGBW", true, 0, 0.15f, 0.35f, 1, 1.0f},
        {"All on RGBW", true, 1, 1, 1, 1, 18.0f / 35},
    };
    for (auto &c : cs) {
      FakeLight l;
      l.remote_values.r = c.r, l.remote_values.g = c.g, l.remote_values.b = c.b, l.remote_values.w = c.w;
      l.remote_values.bright = 0.3f;  // the light's brightness doesn't change the colour's draw
      const float cap = magicband::power_cap_for(35, 24, magicband::shown_elements(l, c.rgbw));
      if (!near(cap, c.want)) why += fmt("%s: cap %.3f want %.3f; ", c.name, cap, c.want);
      // never over budget: elements x 20 mA x n x cap <= budget x 60 mA
      const float ma = magicband::shown_elements(l, c.rgbw) * 20.0f * 35 * cap;
      if (ma > 24 * 60.0f + 0.01f) why += fmt("%s: %.0f mA over the budget; ", c.name, ma);
    }
    result("FW-235", why.empty(), why.empty() ? "35 LEDs, budget 24: red, green, RGBW warm white and RGBW white at 100 %; RGB white 69 %, RGBW all on 51 %; all within budget" : why);
  }
  // FW-236: a light show counts as the worst case; off is nothing lit; NaN colour counts as the worst case
  {
    std::string why;
    FakeLight l;
    l.remote_values.r = 1, l.remote_values.g = 0, l.remote_values.b = 0;
    l.effect = magicband::shows::NAMES[0];
    if (!near(magicband::shown_elements(l, false), 3) || !near(magicband::shown_elements(l, true), 3)) why += "a show isn't red+green+blue on; ";
    l.effect = "Chase";
    if (!near(magicband::shown_elements(l, false), 1)) why += "a one-colour effect isn't sized by its colour; ";
    l.remote_values.on = false;
    if (!near(magicband::shown_elements(l, true), 0)) why += "off isn't 0; ";
    l.remote_values.on = true, l.remote_values.g = NAN;
    if (!near(magicband::shown_elements(l, true), 4)) why += "NaN isn't the worst case; ";
    if (!near(magicband::power_cap_for(35, 24, 0), 1) || !near(magicband::power_cap_for(0, 24, 3), 1)) why += "0 elements/LEDs not 1; ";
    if (!near(magicband::power_cap_for(35, 24, 99), 18.0f / 35)) why += "elements over 4 not clamped; ";
    result("FW-236", why.empty(), why.empty() ? "shows = red+green+blue on (3, also on RGBW: they never light white), one-colour effects by their colour, off = 0, NaN = worst, out-of-range clamped" : why);
  }
  return 0;
}
