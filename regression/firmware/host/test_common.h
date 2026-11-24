#pragma once
// Shared bits of the firmware host tests: result lines and a mock LED ring.
// Each test prints "RESULT|<id>|<pass|fail>|<detail>" lines; host_tests.py
// collects them (and treats a crash or a sanitizer report as a failure).
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "esphome/components/light/esp_color_view.h"
#include "gamma_table.h"

namespace hosttest {

inline std::string fmt(const char *f, ...) {
  char buf[2048];
  va_list ap;
  va_start(ap, f);
  vsnprintf(buf, sizeof buf, f, ap);
  va_end(ap);
  return buf;
}

inline void result(const char *id, bool ok, const std::string &detail) {
  std::string d = detail;
  for (auto &c : d)
    if (c == '\n' || c == '|') c = ' ';
  printf("RESULT|%s|%s|%s\n", id, ok ? "pass" : "fail", d.c_str());
  fflush(stdout);
}

// A ring of n LEDs, 3 or 4 raw bytes each, with guard bytes either side; the
// view's operator[] aborts on an index outside 0..n-1 (as a real out-of-range
// write would corrupt memory).
struct MockRing {
  int n;
  bool white;
  std::vector<uint8_t> mem;
  esphome::light::ESPColorCorrection cc;
  static constexpr int GUARD = 16;
  MockRing(int n_, bool white_, uint8_t local = 255, uint8_t maxb = 255) : n(n_), white(white_) {
    mem.assign(GUARD * 2 + (n > 0 ? n : 0) * 4, 0xA5);
    for (int i = 0; i < n * 4; i++) mem[GUARD + i] = 0;
    cc.set_gamma_table(GAMMA_2_8);
    cc.set_local_brightness(local);
    cc.set_max_brightness(esphome::Color(maxb, maxb, maxb, maxb));
  }
  int32_t size() const { return n; }
  uint8_t *px(int i) { return &mem[GUARD + i * 4]; }
  esphome::light::ESPColorView operator[](int32_t i) {
    if (i < 0 || i >= n) {
      printf("OOB|LED index %d outside 0..%d\n", (int) i, n - 1);
      fflush(stdout);
      abort();
    }
    uint8_t *p = px(i);
    return esphome::light::ESPColorView(p, p + 1, p + 2, white ? p + 3 : nullptr, nullptr, &cc);
  }
  struct All {
    MockRing *r;
    All &operator=(const esphome::Color &c) {
      for (int i = 0; i < r->n; i++) (*r)[i] = c;
      return *this;
    }
  };
  All all() { return All{this}; }
  bool guards_ok() const {
    for (int i = 0; i < GUARD; i++)
      if (mem[i] != 0xA5 || mem[mem.size() - 1 - i] != 0xA5) return false;
    if (!white)
      for (int i = 0; i < n; i++)
        if (mem[GUARD + i * 4 + 3] != 0) return false;  // the unused 4th byte stays untouched
    return true;
  }
  int lit() {
    int k = 0;
    for (int i = 0; i < n; i++) {
      uint8_t *p = px(i);
      if (p[0] || p[1] || p[2] || (white && p[3])) k++;
    }
    return k;
  }
};

}  // namespace hosttest
