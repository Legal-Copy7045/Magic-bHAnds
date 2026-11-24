// render_show() (components/magicband/shows.h): bounds, determinism, end of show.
// With "dump" as argument it reads "show t n" lines and prints each frame as
// hex, for the comparison with the page's JavaScript copy.
#include <set>
#include <string>
#include "test_common.h"
#include "esphome/components/magicband/shows.h"

using namespace esphome::magicband;
using hosttest::fmt;
using hosttest::result;

static const int NS[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 16, 17, 24, 31, 35, 48, 60, 64, 99, 100};

int main(int argc, char **argv) {
  if (argc > 1 && std::string(argv[1]) == "dump") {
    int s, n;
    unsigned t;
    std::vector<uint8_t> buf;
    while (scanf("%d %u %d", &s, &t, &n) == 3) {
      buf.assign(3 * n, 0);
      bool on = shows::render_show(s, t, n, buf.data());
      printf("%d %u %d %d ", s, t, n, on ? 1 : 0);
      for (uint8_t b : buf) printf("%02x", b);
      printf("\n");
    }
    return 0;
  }
  const int G = 64;
  // FW-110 bounds (guard bytes; ASan would also stop an overrun)
  {
    std::string why;
    long frames = 0;
    for (int s = 0; s < shows::COUNT; s++)
      for (int n : NS) {
        std::vector<uint8_t> mem(3 * n + 2 * G, 0x5A);
        for (uint32_t t = 0; t <= shows::DURATION_MS[s] + 200; t += (n > 30 ? 13 : 7)) {
          shows::render_show(s, t, n, mem.data() + G);
          frames++;
          bool ok = true;
          for (int i = 0; i < G; i++)
            if (mem[i] != 0x5A || mem[mem.size() - 1 - i] != 0x5A) ok = false;
          if (!ok) {
            why += fmt("%s n=%d t=%u wrote outside the buffer; ", shows::NAMES[s], n, t);
            break;
          }
        }
      }
    // n = 0 and negative n write nothing
    uint8_t guard[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    for (int s = 0; s < shows::COUNT; s++)
      if (shows::render_show(s, 100, 0, guard) || shows::render_show(s, 100, -3, guard)) why += fmt("%s returned true for n<=0; ", shows::NAMES[s]);
    for (int i = 0; i < 8; i++)
      if (guard[i] != i + 1) why += "n<=0 wrote to the buffer; ";
    result("FW-110", why.empty(), why.empty() ? fmt("%ld frames, 28 shows x %zu ring sizes (1-100 LEDs): no write outside 3n bytes", frames, sizeof(NS) / sizeof(*NS)) : why.substr(0, 1500));
  }
  // FW-111 determinism: same (show, t, n) gives the same frame, in any order
  {
    std::string why;
    for (int s = 0; s < shows::COUNT && why.size() < 1000; s++)
      for (int n : {5, 24, 60}) {
        const uint32_t D = shows::DURATION_MS[s];
        std::vector<std::vector<uint8_t>> fwd;
        for (uint32_t t = 0; t < D; t += 37) {
          std::vector<uint8_t> b(3 * n);
          shows::render_show(s, t, n, b.data());
          fwd.push_back(b);
        }
        size_t k = fwd.size();
        for (int64_t t = (int64_t) (k - 1) * 37; t >= 0; t -= 37) {
          std::vector<uint8_t> b(3 * n, 0xEE);  // dirty buffer: render must clear it
          shows::render_show(s, (uint32_t) t, n, b.data());
          if (b != fwd[--k]) {
            why += fmt("%s n=%d t=%lld differs between runs; ", shows::NAMES[s], n, (long long) t);
            break;
          }
        }
      }
    result("FW-111", why.empty(), why.empty() ? "every show is a pure function of (t, n): same frames backwards, from a dirty buffer" : why);
  }
  // FW-112 lifetime: true while running, false and dark from DURATION_MS; bad index false and dark
  {
    std::string why;
    for (int s = 0; s < shows::COUNT; s++) {
      std::vector<uint8_t> b(72, 0xEE);
      if (!shows::render_show(s, 0, 24, b.data())) why += fmt("%s: false at t=0; ", shows::NAMES[s]);
      if (!shows::render_show(s, shows::DURATION_MS[s] - 1, 24, b.data())) why += fmt("%s: false at the last ms; ", shows::NAMES[s]);
      std::fill(b.begin(), b.end(), 0xEE);
      if (shows::render_show(s, shows::DURATION_MS[s], 24, b.data())) why += fmt("%s: still true at DURATION_MS; ", shows::NAMES[s]);
      for (uint8_t v : b)
        if (v) { why += fmt("%s: not dark after the end; ", shows::NAMES[s]); break; }
    }
    for (int s : {-1, shows::COUNT, 1000}) {
      std::vector<uint8_t> b(72, 0xEE);
      if (shows::render_show(s, 10, 24, b.data())) why += fmt("index %d: true; ", s);
      for (uint8_t v : b)
        if (v) { why += fmt("index %d: not dark; ", s); break; }
    }
    result("FW-112", why.empty(), why.empty() ? "each show runs until DURATION_MS, then reports false with a dark frame; bad indices are dark" : why);
  }
  // FW-113 each show "ends dark": the last 60 ms are faded (max channel <= 48 of 255)
  {
    std::string why, info;
    for (int s = 0; s < shows::COUNT; s++) {
      int peak = 0;
      uint32_t at = 0;
      const uint32_t D = shows::DURATION_MS[s];
      for (int n : {12, 24, 60})
        for (uint32_t t = D - 60; t < D; t++) {
          std::vector<uint8_t> b(3 * n);
          shows::render_show(s, t, n, b.data());
          for (uint8_t v : b)
            if (v > peak) peak = v, at = t;
        }
      if (peak > 48) why += fmt("%s: channel %d of 255 at t=%u (ends at %u); ", shows::NAMES[s], peak, at, D);
    }
    result("FW-113", why.empty(), why.empty() ? "every show is faded out over its last 60 ms" : "Shows cut off while still bright (the comment says each ends dark): " + why);
  }
  // FW-114 names and tables
  {
    std::string why;
    std::set<std::string> seen;
    for (int i = 0; i < shows::COUNT; i++) {
      if (!seen.insert(shows::NAMES[i]).second) why += fmt("duplicate name %s; ", shows::NAMES[i]);
      if (shows::index_of(shows::NAMES[i]) != i) why += fmt("index_of(%s) != %d; ", shows::NAMES[i], i);
      if (shows::DURATION_MS[i] < 1000 || shows::DURATION_MS[i] > 10000) why += fmt("%s lasts %u ms; ", shows::NAMES[i], shows::DURATION_MS[i]);
    }
    if (shows::index_of("Random") != -1 || shows::index_of("") != -1 || shows::index_of("rainbow rush") != -1) why += "unknown names not -1; ";
    if (!(shows::RANDOM_COUNT > 0 && shows::RANDOM_COUNT <= shows::COUNT)) why += "RANDOM_COUNT out of range; ";
    if (std::string(shows::NAMES[shows::RANDOM_COUNT]) != "Birthday") why += "the first show after RANDOM_COUNT is not the first celebration (Birthday); ";
    if (sizeof(shows::NAMES) / sizeof(*shows::NAMES) != (size_t) shows::COUNT || sizeof(shows::DURATION_MS) / sizeof(*shows::DURATION_MS) != (size_t) shows::COUNT)
      why += "array sizes differ from COUNT; ";
    result("FW-114", why.empty(), why.empty() ? fmt("%d unique shows, %d in Random, index_of round-trips, unknown names give -1", shows::COUNT, shows::RANDOM_COUNT) : why);
  }
  return 0;
}
