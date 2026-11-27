#pragma once
// The reader's ring power budget ("Ring power budget") and the "Full-power test" that raises it.
//
// The budget is in LEDs at full RGB white (60 mA each, the datasheet worst case): 24 is the
// 1.44 A the first builds were sized for. The ring is scaled down only as far as the colour it
// shows needs: full white on more LEDs than the budget is scaled (an RGBW LED with everything on
// draws 80 mA), but red or green alone, a third of the current, usually runs at full. The test
// steps the budget up at full white and notes each step in flash first; a reset during a step (the supply sagging until the ESP32 browns out, or
// the supply cutting out) leaves the note, and the next boot keeps the step below it.

#include <algorithm>
#include <cmath>

#include "shows.h"

namespace esphome {
namespace magicband {

constexpr int POWER_BUDGET_DEFAULT = 24;
constexpr int POWER_BUDGET_MIN = 12;
constexpr int POWER_BUDGET_MAX = 35;
constexpr int POWER_TEST_STEPS[] = {24, 26, 28, 30, 32, 35};
constexpr int POWER_TEST_STEP_COUNT = sizeof(POWER_TEST_STEPS) / sizeof(POWER_TEST_STEPS[0]);

// A budget setting made safe: NaN or out of range gives the default or the nearest limit.
inline float power_budget(float leds) {
  if (!std::isfinite(leds)) return POWER_BUDGET_DEFAULT;
  return std::min<float>(std::max<float>(leds, POWER_BUDGET_MIN), POWER_BUDGET_MAX);
}

// The scale (0-1) for a ring of n LEDs showing a colour that lights `elements` LED elements
// at full (red alone 1, green with a little blue 1.3, RGB white 3, RGBW all on 4; each element
// draws up to 20 mA), so the ring stays within `leds` of budget (60 mA each).
inline float power_cap_for(int n, float leds, float elements) {
  if (n <= 0 || !(elements > 0.0f)) return 1.0f;
  const float cap = power_budget(leds) * 60.0f / (static_cast<float>(n) * 20.0f * std::min(elements, 4.0f));
  return std::min(cap, 1.0f);
}

// The scale for the worst case: every element on (full white; an RGBW LED's four elements).
inline float power_cap(int n, bool rgbw, float leds) { return power_cap_for(n, leds, rgbw ? 4.0f : 3.0f); }

// How many elements the ring's current colour lights at full (see power_cap_for). A light show
// paints its own colours with red, green and blue only (never an RGBW ring's white element), so
// it counts as all three on; anything that isn't finite counts as the worst case.
// Light is ESPHome's LightState (a template so the host tests can pass a stand-in).
template<typename Light> float shown_elements(Light &ring, bool rgbw) {
  const float worst = rgbw ? 4.0f : 3.0f;
  auto v = ring.remote_values;
  if (!v.is_on()) return 0.0f;  // off: nothing lit (a fade out keeps the cap it had)
  const auto effect = ring.get_effect_name();
  if (!effect.empty() && shows::index_of(effect.c_str()) >= 0) return 3.0f;
  v.set_state(1.0f);
  v.set_brightness(1.0f);
  float r = 0, g = 0, b = 0, w = 0;
  v.as_rgbw(&r, &g, &b, &w);
  const float e = r + g + b + (rgbw ? w : 0.0f);
  return std::isfinite(e) ? std::min(std::max(e, 0.0f), worst) : worst;
}

// The test's step number i (0, 1, ...) for a ring of n LEDs, or 0 when the test is done: it
// stops after the first step that no longer scales the ring down (more budget changes nothing).
inline int power_test_step(int n, bool rgbw, int i) {
  if (i < 0 || i >= POWER_TEST_STEP_COUNT) return 0;
  if (i > 0 && power_cap(n, rgbw, POWER_TEST_STEPS[i - 1]) >= 1.0f) return 0;
  return POWER_TEST_STEPS[i];
}

// The budget to keep after the reader restarted during the step at `level`: the step below it
// (a reset on the first step, 24, means even the old default is too much: 20).
inline int power_budget_after_reset(int level) {
  int keep = 20;
  for (int s : POWER_TEST_STEPS)
    if (s < level) keep = s;
  return std::max(keep, POWER_BUDGET_MIN);
}

}  // namespace magicband
}  // namespace esphome
