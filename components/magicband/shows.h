#pragma once
// The reader's light shows: short, colourful sequences for the LED ring
// (the start-up show, the "Play show" button and the play_show action).
//
// Each show is a pure function of time: render_show(show, t_ms, n, rgb) fills
// rgb[0 .. 3n) with the colour of every LED at t_ms after the show started.
// Nothing is remembered between frames, so a show can be drawn at any moment,
// and the MagicbHAnds page draws the same shows with a JavaScript copy of this
// file (custom_components/magicband/frontend/page.html, SHOWS): keep the two in
// step.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>

#include "esphome/components/light/esp_color_view.h"
#include "esphome/core/color.h"

namespace esphome {
namespace magicband {

// Writes colour c at level (0-255) to one LED of the ring so that it keeps its
// colour when dim. The light's brightness curve rounds each channel on its own,
// so a fading warm white (lots of red, some green, a little blue) first became
// one step of each (a faint cool white) and, with the minor channels cut, plain
// red: a warm-white circle's tail showed red. Here the channels are set in the
// ring's own output steps, after its brightness curve, in the colour's
// full-brightness proportions (gamma 2.8, the light's default). A channel with
// at least a fifth of the brightest one's share never drops out: the LED stays
// at the dimmest level that still shows it, so a tail keeps its colour to the
// end (where the whole colour is fewer steps than its mix needs, at the very
// dimmest settings, each such channel gets one step, like the top one).
// Smaller shares (warm white's blue) may round away. On RGBW rings with
// the white LED in use, colours are scaled the plain way. (An RGB light still
// hands effects a white value, so test the LED itself, not c.w: going by c.w
// sent RGB rings down the plain path, and a warm tail faded to one step of
// each colour, a bluish white.)
inline void put_dimmed(light::ESPColorView led, Color c, uint8_t level) {
  led = Color(0, 0, 0, 255);
  if (c.w != 0 && led.get_white_raw() != 0) {
    led = c * level;
    return;
  }
  c.w = 0;
  const uint8_t src[3] = {c.r, c.g, c.b};
  int top = 0;
  for (int k = 1; k < 3; k++)
    if (src[k] > src[top]) top = k;
  if (src[top] == 0 || level == 0) {
    led = Color::BLACK;
    return;
  }
  // The output steps channel ch gives for value v (brightness curve, power cap, LED brightness).
  auto out = [&](uint8_t v, int ch) -> int {
    led = Color(ch == 0 ? v : 0, ch == 1 ? v : 0, ch == 2 ? v : 0);
    return ch == 0 ? led.get_red_raw() : ch == 1 ? led.get_green_raw() : led.get_blue_raw();
  };
  // The smallest value giving at least `target` steps on channel ch (0 = off).
  auto value_for = [&](int target, int ch) -> uint8_t {
    if (target <= 0) return 0;
    int lo = 1, hi = 255;
    while (lo < hi) {
      const int mid = (lo + hi) / 2;
      if (out(mid, ch) >= target) hi = mid; else lo = mid + 1;
    }
    return static_cast<uint8_t>(lo);
  };
  float share[3];
  for (int k = 0; k < 3; k++) share[k] = powf(static_cast<float>(src[k]) / src[top], 2.8f);
  const int most = out(src[top], top);
  int steps = out(static_cast<uint8_t>((src[top] * level + 127) / 255), top);
  // Keep every channel with a fifth or more of the share at one step or more.
  int least = 1;
  for (int k = 0; k < 3; k++)
    if (k != top && share[k] >= 0.2f) least = std::max(least, static_cast<int>(ceilf(0.5f / share[k])));
  uint8_t v[3];
  if (most < least) {
    // At the very dimmest settings (LED brightness x power cap or light
    // brightness of about a tenth or less) the whole colour is fewer steps than
    // the mix needs. The proportions can't be shown, so light the top channel
    // and every channel with a fifth or more of its share at one step each (warm
    // white: 1,1,0) rather than the top one alone (plain red). Scaling the plain
    // way doesn't do it either: it rounds the minor channels away first.
    for (int k = 0; k < 3; k++) v[k] = k == top || share[k] >= 0.2f ? value_for(1, k) : 0;
    led = Color(v[0], v[1], v[2]);
    return;
  }
  steps = std::min(std::max(steps, least), std::max(most, 1));
  for (int k = 0; k < 3; k++)
    v[k] = k == top ? value_for(steps, k) : value_for(static_cast<int>(lroundf(steps * share[k])), k);
  led = Color(v[0], v[1], v[2]);
}

namespace shows {

static const int COUNT = 28;
static const char *const NAMES[COUNT] = {
    "Rainbow rush", "Fireworks", "Comet chase", "Colour parade", "Twinkle", "Heartbeat", "Ocean",
    "Fire", "Pinwheel", "Confetti", "Penguins", "Goal", "Aurora", "Candy cane", "Thunderstorm",
    "Sunrise", "Disco",
    // Celebrations (the integration plays these after a welcome on the day; see holidays.py)
    "Birthday", "New Year", "Valentine", "St Patrick", "Easter", "Stars and Stripes", "Halloween",
    "Thanksgiving", "Hanukkah", "Christmas",
    // A new passport badge (passport.py)
    "Stamp",
};
// "Random" picks from the everyday shows (the first RANDOM_COUNT), not the celebrations.
static const int RANDOM_COUNT = 17;
// How long each show runs (ms); it ends dark.
static const uint32_t DURATION_MS[COUNT] = {3100, 5000, 4000, 4300, 5000, 4300, 5000, 4500, 4500, 4500,
                                            4800, 2900, 5500, 4500, 5000, 5000, 4500, 5000, 5200, 4600,
                                            4500, 4800, 4800, 5000, 5000, 5200, 5000, 2800};

inline int index_of(const char *name) {
  for (int i = 0; i < COUNT; i++)
    if (strcmp(name, NAMES[i]) == 0) return i;
  return -1;
}

// A repeatable pseudo-random number from two integers (the page uses the same).
inline uint32_t hash(uint32_t a, uint32_t b) {
  uint32_t h = (a + 1) * 2654435761u ^ b * 40503u;
  h ^= h >> 13;
  h *= 0x5bd1e995u;
  h ^= h >> 15;
  return h;
}
inline float frac(float x) { return x - floorf(x); }
inline float clamp01(float x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

struct RGB {
  float r, g, b;  // 0-1
};
// A fully saturated colour round the colour wheel (h 0-1: red, yellow, green, cyan, blue, magenta).
inline RGB hue(float h) {
  h = frac(h) * 6.0f;
  auto k = [h](float n) {  // the standard HSV to RGB formula with S = V = 1
    const float v = fmodf(n + h, 6.0f), m = v < 4.0f - v ? v : 4.0f - v;
    return 1.0f - clamp01(m);
  };
  return {k(5), k(3), k(1)};
}

// Fills rgb (3 bytes per LED) with show `show` at t ms. Returns false once it has ended.
inline bool render_show(int show, uint32_t t, int n, uint8_t *rgb) {
  if (n <= 0) return false;
  memset(rgb, 0, n * 3);
  if (show < 0 || show >= COUNT || t >= DURATION_MS[show]) return false;
  const float T = t;
  auto put = [&](int i, RGB c, float v) {  // brightest wins where shows overlap
    i = ((i % n) + n) % n;
    v = clamp01(v);
    uint8_t *p = rgb + i * 3;
    const uint8_t r = c.r * v * 255, g = c.g * v * 255, b = c.b * v * 255;
    if (r + g + b > p[0] + p[1] + p[2]) p[0] = r, p[1] = g, p[2] = b;
  };
  // Fade in over the first `in` ms and out over the last `out` ms.
  auto env = [&](float in, float out) {
    const float d = DURATION_MS[show];
    return clamp01(in > 0 ? T / in : 1) * clamp01(out > 0 ? (d - T) / out : 1);
  };
  switch (show) {
    case 0: {  // Rainbow rush: racing comets, a swelling spinning rainbow, a sparkle burst, a fade
      if (T < 900) {
        const float q = T / 900, pos = q * q * 2 * n;
        const int tail = n / 3 > 4 ? n / 3 : 4;
        for (int c = 0; c < 2; c++) {
          const float head = pos + c * n / 2.0f;
          for (int k = 0; k < tail; k++) {
            const float f = 1.0f - (float) k / tail;
            put((int) floorf(head) - k, hue((head - k) / n + c * 0.5f), f * f);
          }
        }
      } else if (T < 1800) {
        const float q = (T - 900) / 900, v = 0.35f + 0.65f * sinf(q * 1.5708f);
        for (int i = 0; i < n; i++) put(i, hue((float) i / n + q * 1.5f), v);
      } else if (T < 2350) {
        const float q = (T - 1800) / 550;
        const uint32_t fr = t / 50;
        for (int i = 0; i < n; i++) {
          const uint32_t h = hash(i, fr);
          if ((h & 7) == 0) put(i, {1, 1, 1}, 1 - 0.5f * q);
          else if ((h & 7) < 5) put(i, hue(((h >> 8) & 255) / 255.0f), 0.86f * (1 - 0.4f * q));
        }
      } else {
        const float q = (T - 2350) / 750;
        for (int i = 0; i < n; i++) put(i, hue((float) i / n + 1.35f + q * 0.3f), 0.78f * (1 - q) * (1 - q));
      }
      break;
    }
    case 1: {  // Fireworks: bursts of colour opening out from random points, with white sparks
      for (int k = 0; k < 6; k++) {
        const float start = k * 750.0f, age = T - start;
        if (age < 0 || age > 1200) continue;
        const int centre = hash(k, 1) % n;
        const RGB c = hue((hash(k, 2) & 1023) / 1024.0f);
        const float radius = (age / 700.0f) * (n / 4.0f), fade = 1 - age / 1200.0f;
        for (int d = 0; d <= (int) radius && d <= n / 2; d++) {
          const float edge = 1 - (radius - d) / (radius + 1);
          const float v = fade * (0.35f + 0.65f * edge);
          put(centre + d, c, v);
          put(centre - d, c, v);
        }
        if (age < 500) {  // sparks at the edge
          const int r = (int) radius;
          if (hash(k, t / 40) & 1) put(centre + r + 1, {1, 1, 1}, 1 - age / 500);
          if (hash(k + 7, t / 40) & 1) put(centre - r - 1, {1, 1, 1}, 1 - age / 500);
        }
      }
      break;
    }
    case 2: {  // Comet chase: three coloured comets at different speeds and directions
      const float e = env(300, 400);
      const float speed[3] = {1.0f, 1.6f, -1.25f}, hues[3] = {0.0f, 0.33f, 0.62f};
      const int tail = n / 4 > 3 ? n / 4 : 3;
      for (int c = 0; c < 3; c++) {
        const float head = T / 1000.0f * speed[c] * n + c * n / 3.0f;
        const int dir = speed[c] > 0 ? 1 : -1;
        for (int k = 0; k < tail; k++) {
          const float f = 1.0f - (float) k / tail;
          put((int) floorf(head) - dir * k, hue(hues[c] + k * 0.01f), e * f * f);
        }
      }
      break;
    }
    case 3: {  // Colour parade: red, orange, yellow, green, blue and purple wipe round in turn
      static const RGB C[6] = {{1, 0, 0}, {1, 0.4f, 0}, {1, 0.85f, 0}, {0, 1, 0.1f}, {0, 0.3f, 1}, {0.6f, 0, 1}};
      const float wipe = 600;
      const int k = (int) (T / wipe);
      const float e = T > 3700 ? clamp01((4300 - T) / 600) : 1;
      const RGB under = k > 0 ? C[(k - 1) % 6] : RGB{0, 0, 0};
      const int lit = k < 6 ? (int) ((T - k * wipe) / wipe * n) : n;
      for (int i = 0; i < n; i++) {
        if (k >= 6) put(i, C[5], e);
        else if (i <= lit) put(i, C[k], e);
        else if (k > 0) put(i, under, e);
      }
      break;
    }
    case 4: {  // Twinkle: soft white, blue and gold stars twinkling in and out
      const float e = env(500, 700);
      for (int i = 0; i < n; i++) {
        const uint32_t h = hash(i, 99);
        const float period = 900 + (h % 800), phase = (h >> 10) % 1000 / 1000.0f;
        const float s = sinf(6.2832f * (T / period + phase));
        const float v = s > 0 ? s * s * s : 0;
        const int kind = (h >> 20) % 3;
        const RGB c = kind == 0 ? RGB{1, 1, 1} : kind == 1 ? RGB{0.55f, 0.7f, 1} : RGB{1, 0.75f, 0.35f};
        put(i, c, e * (0.05f + 0.95f * v));
      }
      break;
    }
    case 5: {  // Heartbeat: three "lub-dub" beats in warm red, spreading from the top
      // Only three: a fourth would start at 4200 ms and be cut off bright at 4300.
      const float beat = 1400, p = fmodf(T, beat);
      float v = 0;
      if (T >= 3 * beat) v = 0;
      else if (p < 220) v = sinf(3.1416f * p / 220);
      else if (p >= 300 && p < 560) v = 0.7f * sinf(3.1416f * (p - 300) / 260);
      for (int i = 0; i < n; i++) {
        const float d = fabsf((float) i / n - 0.5f) * 2;  // 0 at the bottom, 1 at the top
        put(i, {1, 0.08f, 0.25f}, v * (0.45f + 0.55f * d));
      }
      break;
    }
    case 6: {  // Ocean: blue and teal waves rolling round the ring
      const float e = env(500, 600);
      for (int i = 0; i < n; i++) {
        const float w = 0.5f + 0.5f * sinf(6.2832f * ((float) i / n * 2 - T / 1500));
        const float w2 = 0.5f + 0.5f * sinf(6.2832f * ((float) i / n * 3 + T / 2300));
        const float m = clamp01(0.6f * w + 0.4f * w2);
        put(i, {0, 0.15f + 0.65f * m, 0.6f + 0.1f * m}, e * (0.3f + 0.7f * m));
      }
      break;
    }
    case 7: {  // Fire: flickering flames, hottest at the bottom
      const float e = env(400, 700);
      const uint32_t fr = t / 70;
      const float f = (T - fr * 70.0f) / 70;
      for (int i = 0; i < n; i++) {
        const float a = (hash(i, fr) & 255) / 255.0f, b = (hash(i, fr + 1) & 255) / 255.0f;
        const float d = 1 - fabsf((float) i / n - 0.5f) * 2;  // 1 at the bottom
        const float heat = clamp01((a + (b - a) * f) * 0.55f + d * 0.5f);
        put(i, {1, heat * heat * 0.75f, heat * heat * heat * heat * 0.15f}, e * (0.25f + 0.75f * heat));
      }
      break;
    }
    case 8: {  // Pinwheel: four coloured arms that spin up, then slow down
      const float q = T / DURATION_MS[show];
      const float turn = 3.0f * (q - sinf(6.2832f * q) / 6.2832f);
      const float e = env(250, 500);
      for (int i = 0; i < n; i++) {
        const float a = frac((float) i / n + turn) * 4;
        const int arm = (int) a;
        const float inside = a - arm;
        if (inside < 0.12f) continue;  // dark gap between arms
        put(i, hue(arm / 4.0f + T / 4000), e * (0.4f + 0.6f * inside));
      }
      break;
    }
    case 9: {  // Confetti: random flashes of colour that fade
      const float e = T > 3800 ? clamp01((4500 - T) / 700) : 1;
      const uint32_t fr = t / 60;
      const uint32_t chance = 2600 / (n > 0 ? n : 1);  // about two new flashes a frame (per 1000)
      for (int i = 0; i < n; i++)
        for (int back = 0; back < 14 && back <= (int) fr; back++) {
          const uint32_t h = hash(i, fr - back);
          if (h % 1000 < chance) {
            put(i, hue(((h >> 12) & 1023) / 1024.0f), e * (1 - back / 14.0f));
            break;
          }
        }
      break;
    }
    case 10: {  // Penguins: black and gold. Gold arcs spin round a black ring, then two gold flashes and a sparkle
      const RGB gold = {1, 0.68f, 0.06f};
      if (T < 2800) {
        const float q = T / 2800, turn = 1.6f * q * q;
        const float e = clamp01(T / 300);
        for (int i = 0; i < n; i++) {
          const float a = frac((float) i / n + turn) * 3;  // three arcs
          const float inside = a - floorf(a);
          if (inside < 0.45f) put(i, gold, e * (0.35f + 0.65f * sinf(3.1416f * inside / 0.45f)));
        }
      } else if (T < 4000) {
        const float p = fmodf(T - 2800, 600) / 600;
        const float v = sinf(3.1416f * p);
        const uint32_t fr = t / 45;
        for (int i = 0; i < n; i++) {
          put(i, gold, v);
          if ((hash(i, fr) & 15) == 0) put(i, {1, 1, 1}, v);  // white sparkles in the flash
        }
      } else {
        const float q = (T - 4000) / 800;
        for (int i = 0; i < n; i++)
          if ((hash(i, 7) & 3) == 0) put(i, gold, (1 - q) * 0.8f);
      }
      break;
    }
    case 11: {  // Goal: three hard red pulses, like the bands' red flash for a goal
      const float beat = 900, p = fmodf(T, beat);
      float v = 0;
      if (T < 3 * beat) {
        if (p < 80) v = p / 80;
        else if (p < 380) v = 1;
        else if (p < 750) v = 1 - (p - 380) / 370;
      }
      for (int i = 0; i < n; i++) put(i, {1, 0, 0}, v);
      break;
    }
    case 12: {  // Aurora: green, teal and violet curtains drifting and shimmering
      const float e = env(700, 900);
      for (int i = 0; i < n; i++) {
        const float x = (float) i / n;
        const float a = 0.5f + 0.5f * sinf(6.2832f * (x * 1.5f + T / 3100));
        const float b = 0.5f + 0.5f * sinf(6.2832f * (x * 2.5f - T / 2200) + 1.3f);
        const float shimmer = 0.85f + 0.15f * sinf(T / 90 + i * 1.7f);
        const RGB c = {0.45f * b, 0.35f + 0.65f * a, 0.35f + 0.45f * (1 - a) + 0.2f * b};
        put(i, c, e * shimmer * (0.25f + 0.75f * clamp01(0.6f * a + 0.5f * b)));
      }
      break;
    }
    case 13: {  // Candy cane: red and white stripes spinning faster, then slowing
      const float q = T / DURATION_MS[show];
      const float turn = 2.5f * (q - sinf(6.2832f * q) / 6.2832f);
      const float e = env(250, 500);
      for (int i = 0; i < n; i++) {
        const float a = frac((float) i / n + turn) * 8;  // eight stripes
        const bool red = ((int) a) % 2 == 0;
        put(i, red ? RGB{1, 0, 0.05f} : RGB{1, 1, 1}, e * (red ? 1.0f : 0.75f));
      }
      break;
    }
    case 14: {  // Thunderstorm: a dark, rolling blue sky split by lightning
      const float e = env(400, 600);
      float flash = 0;
      const float strikes[3] = {1100, 2600, 3900};
      for (float s0 : strikes) {
        const float d = T - s0;
        if (d >= 0 && d < 90) flash = 1;
        else if (d >= 160 && d < 230) flash = 0.7f;  // the second flicker of a strike
        else if (d >= 230 && d < 600) flash = flash > 0.3f * (1 - (d - 230) / 370) ? flash : 0.3f * (1 - (d - 230) / 370);
      }
      for (int i = 0; i < n; i++) {
        const float cloud = 0.5f + 0.5f * sinf(6.2832f * ((float) i / n * 2 + T / 2600));
        put(i, {0.05f, 0.1f, 0.45f}, e * (0.12f + 0.25f * cloud));
        if (flash > 0) put(i, {0.85f, 0.9f, 1}, flash);
      }
      break;
    }
    case 15: {  // Sunrise: the ring warms from the bottom up, deep red to orange to golden white
      const float q = T / DURATION_MS[show];
      const float e = T > 4300 ? clamp01((5000 - T) / 700) : 1;
      for (int i = 0; i < n; i++) {
        const float h = fabsf((float) i / n - 0.5f) * 2;  // 1 at the top, 0 at the bottom
        const float lift = clamp01(q * 1.6f - (1 - h) * 0.6f);
        const RGB c = {1, clamp01(lift * 0.85f), clamp01(lift * lift * 0.55f)};
        put(i, c, e * clamp01(0.15f + lift));
      }
      break;
    }
    case 16: {  // Disco: six segments jumping to new colours on the beat, pulsing
      const uint32_t beat = t / 250;
      const float p = (T - beat * 250.0f) / 250;
      const float e = T > 4000 ? clamp01((4500 - T) / 500) : 1;
      for (int i = 0; i < n; i++) {
        const int seg = i * 6 / n;
        const uint32_t h = hash(seg, beat);
        put(i, hue((h & 1023) / 1024.0f), e * (0.45f + 0.55f * (1 - p)));
      }
      break;
    }
    case 17: {  // Birthday: party-coloured candles light round the ring, flicker, are blown out, then confetti
      static const RGB C[4] = {{1, 0.35f, 0.6f}, {1, 0.8f, 0.1f}, {0.2f, 0.8f, 1}, {0.5f, 1, 0.2f}};
      if (T < 4300) {
        const int lit = T < 1500 ? (int) (T / 1500 * n) : n;
        const float blow = T < 3300 ? 0 : (T - 3300) / 1000;  // the dark spreads from the top down both sides
        const uint32_t fr = t / 80;
        for (int i = 0; i <= lit && i < n; i++) {
          const float top = fabsf((float) i / n - 0.5f) * 2;  // 1 at the top
          if (top > 1 - blow) continue;
          put(i, C[i % 4], 0.75f + 0.25f * ((hash(i, fr) & 255) / 255.0f));
        }
      } else {
        const float q = (T - 4300) / 700;
        const uint32_t fr = t / 50;
        for (int i = 0; i < n; i++) {
          const uint32_t h = hash(i, fr);
          if ((h & 3) == 0) put(i, C[(h >> 4) % 4], 1 - q);
        }
      }
      break;
    }
    case 18: {  // New Year: a 3-2-1 countdown in white, then gold and silver bursts and sparkles
      if (T < 1800) {
        const int k = (int) (T / 600);
        const float p = (T - k * 600.0f) / 600;
        const float v = p < 0.6f ? 1 : 1 - (p - 0.6f) / 0.4f;
        const int lit = n * (3 - k) / 3;
        for (int i = 0; i < lit; i++) put(i, {1, 1, 1}, v);
      } else {
        const float e = T > 4600 ? clamp01((5200 - T) / 600) : 1;
        for (int k = 0; k < 5; k++) {
          const float age = T - 1800 - k * 650.0f;
          if (age < 0 || age > 1100) continue;
          const int centre = hash(k, 31) % n;
          const RGB c = (k & 1) ? RGB{0.85f, 0.88f, 1} : RGB{1, 0.72f, 0.12f};
          const float radius = age / 600.0f * (n / 5.0f), fade = 1 - age / 1100.0f;
          for (int d = 0; d <= (int) radius && d <= n / 2; d++) {
            const float v = e * fade * (0.4f + 0.6f * (1 - (radius - d) / (radius + 1)));
            put(centre + d, c, v);
            put(centre - d, c, v);
          }
        }
        const uint32_t fr = t / 60;
        for (int i = 0; i < n; i++)
          if ((hash(i, fr) & 31) == 0) put(i, {1, 0.85f, 0.4f}, e * 0.8f);
      }
      break;
    }
    case 19: {  // Valentine: pink and red arcs draw a heart from the top down, then it beats
      const RGB red = {1, 0, 0.12f}, pink = {1, 0.3f, 0.55f};
      if (T < 1400) {
        const float q = T / 1400;
        for (int i = 0; i < n; i++) {
          const float pos = (float) i / n;  // 0 at the top, 0.5 at the bottom
          const bool right = pos <= 0.5f;
          const float along = right ? pos * 2 : (1 - pos) * 2;  // 0 at the top, 1 at the bottom
          if (along <= q) put(i, right ? pink : red, 0.5f + 0.5f * (1 - (q - along)));
        }
      } else {
        const float p = fmodf(T - 1400, 1100);
        float v = 0.25f;
        if (p < 200) v = 0.25f + 0.75f * sinf(3.1416f * p / 200);
        else if (p >= 280 && p < 520) v = 0.25f + 0.5f * sinf(3.1416f * (p - 280) / 240);
        const float e = T > 4000 ? clamp01((4600 - T) / 600) : 1;
        for (int i = 0; i < n; i++) put(i, ((float) i / n <= 0.5f) ? pink : red, e * v);
      }
      break;
    }
    case 20: {  // St Patrick: rolling shades of green with gold coins glinting
      const float e = env(400, 600);
      for (int i = 0; i < n; i++) {
        const float w = 0.5f + 0.5f * sinf(6.2832f * ((float) i / n * 3 + T / 1800));
        put(i, {0.05f + 0.25f * w, 0.55f + 0.45f * w, 0.1f * (1 - w)}, e * (0.4f + 0.6f * w));
      }
      const uint32_t fr = t / 70;
      for (int i = 0; i < n; i++)
        for (int back = 0; back < 6 && back <= (int) fr; back++)
          if (hash(i, fr - back) % 100 < 3) {
            put(i, {1, 0.75f, 0.1f}, e * (1 - back / 6.0f));
            break;
          }
      break;
    }
    case 21: {  // Easter: six pastel eggs turning slowly round the ring, each hatching with a white flash
      static const RGB P[6] = {{1, 0.55f, 0.7f}, {1, 0.9f, 0.45f}, {0.5f, 1, 0.7f},
                               {0.75f, 0.6f, 1}, {0.5f, 0.8f, 1},  {1, 0.7f, 0.5f}};
      const float e = env(400, 600), turn = T / 6000;
      for (int i = 0; i < n; i++) {
        const float a = frac((float) i / n + turn) * 6;
        const int egg = (int) a;
        const float inside = a - egg;
        if (egg > 5 || inside < 0.15f || inside > 0.85f) continue;
        const float hatch = T - 600 - egg * 600.0f;  // each egg hatches in turn
        put(i, P[egg], e * (0.55f + 0.45f * sinf(3.1416f * (inside - 0.15f) / 0.7f)));
        if (hatch >= 0 && hatch < 250) put(i, {1, 1, 1}, e * (1 - hatch / 250));
      }
      break;
    }
    case 22: {  // Stars and Stripes: red, white and blue fill the ring and spin, then white stars twinkle on blue
      static const RGB C[3] = {{1, 0, 0.05f}, {1, 1, 1}, {0, 0.2f, 1}};
      if (T < 1200) {
        const float q = T / 1200;
        for (int i = 0; i < n; i++) {
          const float pos = (float) i / n * 3;
          const int stripe = (int) pos;
          if (pos - stripe <= q) put(i, C[stripe], stripe == 1 ? 0.75f : 1);
        }
      } else if (T < 3400) {
        const float q = (T - 1200) / 2200, turn = 1.5f * q * q;
        for (int i = 0; i < n; i++) {
          int stripe = (int) (frac((float) i / n + turn) * 3);
          if (stripe > 2) stripe = 2;
          put(i, C[stripe], stripe == 1 ? 0.75f : 1);
        }
      } else {
        const float e = T > 4200 ? clamp01((4800 - T) / 600) : 1;
        for (int i = 0; i < n; i++) {
          put(i, C[2], e * 0.5f);
          const uint32_t h = hash(i, 5);
          const float s = sinf(6.2832f * (T / (500 + h % 400) + (h >> 12) % 100 / 100.0f));
          if ((h & 3) == 0 && s > 0) put(i, {1, 1, 1}, e * s);
        }
      }
      break;
    }
    case 23: {  // Halloween: purple with four flickering orange pumpkins, and sudden ghostly green flashes
      const float e = env(400, 600), turn = T / 8000;
      const uint32_t fr = t / 90;
      const float ghosts[2] = {2000, 3600};
      float ghost = 0;
      for (float s0 : ghosts) {
        const float d = T - s0;
        if (d >= 0 && d < 300) ghost = 1 - d / 300;
      }
      for (int i = 0; i < n; i++) {
        put(i, {0.45f, 0, 0.8f}, e * 0.35f);
        const float a = frac((float) i / n + turn) * 4, inside = a - floorf(a);
        if (inside > 0.3f && inside < 0.7f) put(i, {1, 0.35f, 0}, e * (0.55f + 0.45f * ((hash(i, fr) & 255) / 255.0f)));
        if (ghost > 0) put(i, {0.55f, 1, 0.55f}, ghost);
      }
      break;
    }
    case 24: {  // Thanksgiving: autumn leaves drifting down both sides of a warm amber ring
      static const RGB L[4] = {{1, 0.35f, 0}, {0.85f, 0.1f, 0}, {1, 0.7f, 0.1f}, {0.6f, 0.25f, 0.05f}};
      const float e = env(500, 700), half = n / 2.0f;
      for (int i = 0; i < n; i++) put(i, {1, 0.45f, 0.05f}, e * 0.15f);
      for (int k = 0; k < 12; k++) {
        const float age = T - (float) (hash(k, 11) % 3600);
        if (age < 0 || age > 1400) continue;
        const float along = age / 1400;  // 0 at the top, 1 at the bottom
        const bool right = hash(k, 12) & 1;
        const int i = right ? (int) (along * half) : n - 1 - (int) (along * half);
        const RGB c = L[hash(k, 13) % 4];
        put(i, c, e * (1 - 0.3f * along));
        put(right ? i - 1 : i + 1, c, e * 0.4f * (1 - along));  // a short trail above it
      }
      break;
    }
    case 25: {  // Hanukkah: the shamash at the top lights first, then eight candles one by one, on a blue glow
      const float e = T > 4600 ? clamp01((5200 - T) / 600) : 1;
      const uint32_t fr = t / 90;
      for (int i = 0; i < n; i++) put(i, {0, 0.2f, 1}, e * clamp01((T - 400) / 1500) * 0.3f);
      for (int c = 0; c < 9; c++) {
        const float lit = T - 300 - c * 350.0f;
        if (lit < 0) continue;
        const float flick = 0.75f + 0.25f * ((hash(c, fr) & 255) / 255.0f);
        put(c * n / 9, c == 0 ? RGB{1, 0.85f, 0.5f} : RGB{0.85f, 0.9f, 1}, e * clamp01(lit / 200) * flick);
      }
      break;
    }
    case 26: {  // Christmas: red and green lights chasing round with snow twinkling, then a gold star at the top
      const float e = env(300, 600);
      if (T < 3800) {
        const int step = (int) (T / 220);
        const uint32_t fr = t / 120;
        for (int i = 0; i < n; i++) {
          const int k = (i + step) % 4;
          if (k == 0) put(i, {1, 0, 0.05f}, e);
          else if (k == 2) put(i, {0, 1, 0.15f}, e);
          if ((hash(i, fr) & 31) == 0) put(i, {1, 1, 1}, e * 0.9f);
        }
      } else {
        const float q = (T - 3800) / 1200;
        for (int i = 0; i < n; i++) {
          const float top = fabsf((float) i / n - 0.5f) * 2;  // 1 at the top
          put(i, {1, 0.7f, 0.15f}, e * clamp01((top - 0.8f) * 5) * (0.6f + 0.4f * sinf(q * 12)));
          put(i, {0, 0.6f, 0.1f}, e * 0.25f * (1 - q));
        }
      }
      break;
    }
    case 27: {  // Stamp: a passport stamp for a new badge. Gold sweeps round, a white flash, a sparkling gold glow
      const RGB gold = {1, 0.72f, 0.1f};
      if (T < 700) {
        const int lit = (int) (T / 700 * n);
        for (int i = 0; i <= lit && i < n; i++) put(i, gold, 0.6f + 0.4f * (float) i / n);
      } else if (T < 900) {
        for (int i = 0; i < n; i++) put(i, {1, 1, 1}, 1 - (T - 700) / 400);
      } else {
        const float e = T > 2200 ? clamp01((2800 - T) / 600) : 1;
        const uint32_t fr = t / 50;
        for (int i = 0; i < n; i++) {
          put(i, gold, e * 0.7f);
          if ((hash(i, fr) & 7) == 0) put(i, {1, 1, 0.85f}, e);
        }
      }
      break;
    }
  }
  return true;
}

}  // namespace shows
}  // namespace magicband
}  // namespace esphome
