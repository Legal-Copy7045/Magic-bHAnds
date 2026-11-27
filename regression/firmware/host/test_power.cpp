// The ring power budget and the full-power test's steps (components/magicband/power.h).
#include "test_common.h"
#include "esphome/components/magicband/power.h"

using namespace esphome;
using hosttest::fmt;
using hosttest::result;

static bool near(float a, float b) { return std::fabs(a - b) < 1e-5f; }

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
  return 0;
}
