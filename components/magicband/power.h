#pragma once
// The reader's ring power budget ("Ring power budget") and the "Full-power test" that raises it.
//
// The budget is in LEDs at full RGB white (60 mA each, the datasheet worst case): 24 is the
// 1.44 A the first builds were sized for. A ring with more LEDs than the budget is scaled down
// so full white stays within it (an RGBW LED with everything on draws 80 mA, so an RGBW ring
// gets three quarters of the LEDs). The test steps the budget up at full white and notes each
// step in flash first; a reset during a step (the supply sagging until the ESP32 browns out, or
// the supply cutting out) leaves the note, and the next boot keeps the step below it.

#include <algorithm>
#include <cmath>

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

// The scale (0-1) for a ring of n LEDs so full white stays within `leds` of budget.
inline float power_cap(int n, bool rgbw, float leds) {
  const float budget = power_budget(leds) * (rgbw ? 0.75f : 1.0f);
  return n > budget ? budget / static_cast<float>(n) : 1.0f;
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
