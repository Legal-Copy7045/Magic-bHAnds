// put_dimmed() (components/magicband/shows.h): dimming that keeps a colour's hue.
#include "test_common.h"
#include "esphome/components/magicband/shows.h"

using namespace esphome;
using hosttest::fmt;
using hosttest::MockRing;
using hosttest::result;

struct Out {
  int r, g, b, w;
};
static Out run(Color c, uint8_t level, bool white_led, uint8_t local = 255, uint8_t maxb = 255) {
  MockRing ring(1, white_led, local, maxb);
  magicband::put_dimmed(ring[0], c, level);
  uint8_t *p = ring.px(0);
  return {p[0], p[1], p[2], white_led ? p[3] : 0};
}
// The naive path ESPHome would take: scale the colour, then the curve.
static Out naive(Color c, uint8_t level, uint8_t local = 255, uint8_t maxb = 255) {
  MockRing ring(1, false, local, maxb);
  ring[0] = c * level;
  uint8_t *p = ring.px(0);
  return {p[0], p[1], p[2], 0};
}

int main() {
  struct Named {
    const char *name;
    Color c;
  };
  // The reader's colour table (set_ring_colour) at full brightness.
  const Named tails[] = {{"Warm white", Color(255, 178, 89)}, {"Orange", Color(255, 89, 0)}, {"Pink", Color(255, 51, 127)}};
  const uint8_t locals[] = {255, 200, 128, 77, 26};   // the light's brightness (Idle glow 100/80/50/30/10 %)
  const uint8_t maxbs[] = {255, 160, 61, 26, 13};  // LED brightness x power cap (100, 63, 24, 10, 5 %)
  // FW-100: hue kept (RGB ring)
  {
    std::string why, deg;
    int checked = 0, degenerate = 0;
    for (auto &t : tails) {
      int first_minor[3] = {-1, -1, -1};
      for (uint8_t L : locals)
        for (uint8_t M : maxbs)
          for (int level = 1; level <= 255; level++) {
            Out o = run(t.c, level, false, L, M);
            const int src[3] = {t.c.r, t.c.g, t.c.b}, out[3] = {o.r, o.g, o.b};
            checked++;
            if (out[0] == 0) continue;  // dark (allowed only if the level rounds to nothing)
            // The ring's top step count for this colour at full level: below 2 there is no room for a mix (FW-107).
            const Out full = naive(t.c, 255, L, M);
            if (full.r < 2) {
              degenerate++;
              if (out[1] == 0 && powf(src[1] / 255.0f, 2.8f) >= 0.2f && deg.find(fmt("%s at light brightness %d/255, LED brightness x cap %d/255", t.name, L, M)) == std::string::npos)
                deg += fmt("%s at light brightness %d/255, LED brightness x cap %d/255: the whole colour is %d step(s) of red, shown as %d,%d,%d; ",
                           t.name, L, M, full.r, o.r, o.g, o.b);
              continue;
            }
            for (int k = 1; k < 3; k++) {
              const float share = powf(src[k] / 255.0f, 2.8f);
              if (out[k] > out[0]) why += fmt("%s: channel %d brighter than red at level %d; ", t.name, k, level);
              if (src[k] == 0 && out[k] != 0) why += fmt("%s: channel %d lit though the colour has none (level %d); ", t.name, k, level);
              if (share >= 0.2f && out[k] == 0)
                why += fmt("%s: channel %d (share %.2f) dropped out at level %d (local %d, max %d) -> %d,%d,%d; ", t.name, k, share,
                           level, L, M, o.r, o.g, o.b);
              const float want = share * out[0];
              if (fabsf(out[k] - want) > 1.0f + 0.04f * out[0])
                why += fmt("%s: channel %d is %d steps, the mix wants %.1f (red %d, level %d, local %d, max %d); ", t.name, k, out[k],
                           want, out[0], level, L, M);
              if (out[k] > 0 && (first_minor[k] < 0 || level < first_minor[k]) && L == 255 && M == 255) first_minor[k] = level;
            }
          }
      if (why.size() > 1500) break;
    }
    // Sensitivity: the naive path does turn a dim warm white cool (equal steps), which put_dimmed must not.
    Out nv = naive(Color(255, 178, 89), 12, 77);
    Out pd = run(Color(255, 178, 89), 12, false, 77);
    std::string sens = fmt("sensitivity: the plain path gives warm white at level 12, glow 30 %% = %d,%d,%d; put_dimmed = %d,%d,%d", nv.r, nv.g, nv.b, pd.r, pd.g, pd.b);
    result("FW-100", why.empty(), why.empty() ? fmt("%d colour/level/brightness combinations keep their mix; %s", checked, sens.c_str())
                                              : why.substr(0, 1500));
    // FW-107: the documented "a fifth or more never drops out" where the ring has under 2 steps for the whole colour.
    result("FW-107", deg.empty(), deg.empty() ? fmt("%d near-off combinations, none drop a major channel", degenerate)
                                              : "Documented guarantee not met at extreme dimming (design limit: the colour has 1 step, "
                                                "so put_dimmed keeps it red rather than exceed its brightness): " + deg);
  }
  // FW-101: RGB ring, colour carrying w=255 (an RGB light still hands effects a white value) takes the mix path.
  {
    std::string why;
    for (auto &t : tails)
      for (int level = 0; level <= 255; level += 5) {
        Color cw = t.c;
        cw.w = 255;
        Out a = run(cw, level, false, 77), b = run(t.c, level, false, 77);
        if (a.r != b.r || a.g != b.g || a.b != b.b)
          why += fmt("%s level %d: w=255 gives %d,%d,%d, w=0 gives %d,%d,%d; ", t.name, level, a.r, a.g, a.b, b.r, b.g, b.b);
      }
    Out a = run(Color(255, 178, 89, 255), 8, false, 77);
    result("FW-101", why.empty(), why.empty() ? fmt("w=255 and w=0 give the same mix on an RGB ring for all three colours; e.g. warm white w=255, level 8, glow 30 %%: %d,%d,%d", a.r, a.g, a.b) : why.substr(0, 1500));
  }
  // FW-102: RGBW ring with the white LED in use takes the plain path (c * level through the curve, white included).
  {
    std::string why;
    const Color cs[] = {Color(0, 0, 0, 255), Color(255, 89, 0, 153), Color(153, 51, 0, 204), Color(0, 38, 89, 255)};
    for (const Color &c : cs)
      for (int level = 0; level <= 255; level += 3) {
        Out o = run(c, level, true, 128);
        MockRing ref(1, true, 128);
        ref[0] = c * static_cast<uint8_t>(level);
        uint8_t *p = ref.px(0);
        if (o.r != p[0] || o.g != p[1] || o.b != p[2] || o.w != p[3])
          why += fmt("colour %d,%d,%d,%d level %d: %d,%d,%d,%d vs plain %d,%d,%d,%d; ", c.r, c.g, c.b, c.w, level, o.r, o.g, o.b, o.w,
                     p[0], p[1], p[2], p[3]);
      }
    result("FW-102", why.empty(), why.empty() ? "white-LED colours on an RGBW ring are scaled the plain way at every level" : why.substr(0, 1500));
  }
  // FW-103: RGBW ring, a colour without white: mix path, and the white LED (probed at 255) ends dark.
  {
    std::string why;
    for (auto &t : tails)
      for (int level = 0; level <= 255; level += 1) {
        Out o = run(t.c, level, true, 77), r = run(t.c, level, false, 77);
        if (o.w != 0) why += fmt("%s level %d: white LED left at %d; ", t.name, level, o.w);
        if (o.r != r.r || o.g != r.g || o.b != r.b) why += fmt("%s level %d: RGBW %d,%d,%d vs RGB %d,%d,%d; ", t.name, level, o.r, o.g, o.b, r.r, r.g, r.b);
      }
    result("FW-103", why.empty(), why.empty() ? "no-white colours on an RGBW ring: same mix as RGB, white LED off" : why.substr(0, 1500));
  }
  // FW-104: level 0, or a black colour, is black (white LED too).
  {
    std::string why;
    const Color cs[] = {Color(255, 178, 89), Color(255, 0, 0), Color(0, 0, 255, 255), Color(255, 255, 255, 255)};
    for (const Color &c : cs)
      for (bool w : {false, true}) {
        Out o = run(c, 0, w);
        if (o.r || o.g || o.b || o.w) why += fmt("colour %d,%d,%d,%d (%s) level 0 -> %d,%d,%d,%d; ", c.r, c.g, c.b, c.w, w ? "RGBW" : "RGB", o.r, o.g, o.b, o.w);
      }
    for (bool w : {false, true})
      for (int level : {1, 128, 255}) {
        Out o = run(Color(0, 0, 0), level, w);
        if (o.r || o.g || o.b || o.w) why += fmt("black at level %d (%s) -> %d,%d,%d,%d; ", level, w ? "RGBW" : "RGB", o.r, o.g, o.b, o.w);
      }
    result("FW-104", why.empty(), why.empty() ? "level 0 and black give an unlit LED on RGB and RGBW rings" : why);
  }
  // FW-105: the top channel never gets brighter as the level falls (a smooth tail).
  {
    std::string why;
    for (auto &t : tails)
      for (uint8_t L : locals) {
        int prev = 0;
        for (int level = 1; level <= 255; level++) {
          Out o = run(t.c, level, false, L);
          if (o.r < prev) why += fmt("%s local %d: red %d at level %d after %d; ", t.name, L, o.r, level, prev);
          prev = o.r;
        }
      }
    result("FW-105", why.empty(), why.empty() ? "brightness is monotonic in level for every tail colour and glow" : why.substr(0, 1500));
  }
  // FW-106: full level is the colour at full brightness (top channel exactly as the curve gives it).
  {
    std::string why;
    for (auto &t : tails)
      for (uint8_t L : locals) {
        Out o = run(t.c, 255, false, L), n = naive(t.c, 255, L);
        if (o.r != n.r) why += fmt("%s local %d: red %d at full level vs %d plain; ", t.name, L, o.r, n.r);
      }
    result("FW-106", why.empty(), why.empty() ? "level 255 keeps the colour's full brightness" : why);
  }
  return 0;
}
