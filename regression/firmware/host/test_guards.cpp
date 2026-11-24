// components/magicband/guards.h: release_newer (automatic updates never go
// back), RateLimit and UnknownTagLimit.
#include <string>
#include "test_common.h"
#include "esphome/components/magicband/guards.h"

using namespace esphome::magicband;
using hosttest::fmt;
using hosttest::result;

int main() {
  // FW-180 release_newer: only a strictly newer dotted version installs automatically
  {
    std::string why;
    struct C { const char *latest, *current; bool want; } cs[] = {
        {"0.10.32", "0.10.31", true},  {"0.11.0", "0.10.31", true},   {"1.0.0", "0.10.31", true},   {"0.10.100", "0.10.99", true},
        {"0.10.31", "0.10.31", false}, {"0.10.30", "0.10.31", false}, {"0.9.99", "0.10.31", false}, {"0.10.4", "0.10.31", false},
        {"0.10", "0.10.0", false},     {"0.10.0.1", "0.10.0", true},  {"0.10.1", "0.10", true},     {"0.10.32-beta", "0.10.31", true},
        {"", "0.10.31", false},        {"0.10.32", "", false},        {"v0.10.32", "0.10.31", false}, {"0..32", "0.10.31", false},
        {"0.10.", "0.10.31", false},   {"abc", "0.10.31", false},     {"99999999999.0", "0.10.31", false}, {"0.10.32", "2026.10.2", false},
    };
    for (auto &c : cs)
      if (release_newer(c.latest, c.current) != c.want)
        why += fmt("release_newer(%s, %s) = %d; ", c.latest, c.current, !c.want);
    result("FW-180", why.empty(), why.empty() ? fmt("%zu version pairs: only a strictly newer release counts; equal, older, empty or malformed versions never install", sizeof(cs) / sizeof(*cs)) : why);
  }
  // FW-181 UnknownTagLimit: 6 new a minute, 30 an hour, recent ones pass, nothing recorded when refused
  {
    std::string why;
    UnknownTagLimit L;
    int ok = 0;
    for (int i = 0; i < 10; i++)
      if (L.allow(fmt("04%012X", i), 1000 + i * 100)) ok++;
    if (ok != 6) why += fmt("%d of 10 new IDs in a second (want 6); ", ok);
    if (!L.allow(fmt("04%012X", 2), 2000)) why += "a reported ID tapped again was refused; ";
    if (L.allow(fmt("04%012X", 8), 2100)) why += "a refused ID got in on its second try within the minute; ";
    if (!L.allow(fmt("04%012X", 8), 1000 + 60000)) why += "a new ID a minute later was refused; ";
    if (L.allow("", 200000)) why += "an empty ID was allowed; ";
    UnknownTagLimit H;
    ok = 0;
    for (int i = 0; i < 600; i++)  // one new ID every 6 s for an hour
      if (H.allow(fmt("0A0B%04X", i), 10 + i * 6000)) ok++;
    if (ok != 30) why += fmt("%d new IDs in an hour at one per 6 s (want 30); ", ok);
    if (!H.allow(fmt("0A0B%04X", 99999), 10 + 3600000 + 5000)) why += "a new ID after the hour was refused; ";
    // millis() wrap
    UnknownTagLimit W;
    ok = 0;
    for (int i = 0; i < 10; i++)
      if (W.allow(fmt("0E0F%04X", i), 0xFFFFFFFFu - 3000 + i * 1000)) ok++;
    if (ok != 6) why += fmt("across the millis() wrap: %d of 10 (want 6); ", ok);
    result("FW-181", why.empty(), why.empty() ? "UnknownTagLimit: 6 new IDs a minute and 30 an hour; a reported ID tapped again passes; a refused one isn't recorded; wrap-safe" : why);
  }
  // FW-182 RateLimit: N in any window, sliding, wrap-safe
  {
    std::string why;
    RateLimit<3> r;
    const bool a = r.allow(0, 1000), b = r.allow(10, 1000), c = r.allow(20, 1000), d = r.allow(30, 1000);
    if (!(a && b && c) || d) why += "not exactly 3 in a burst; ";
    if (!r.allow(1000, 1000)) why += "not allowed once the first left the window; ";
    if (r.allow(1005, 1000)) why += "allowed while 3 are in the window; ";
    if (!r.allow(1010, 1000)) why += "the second's slot didn't free up; ";
    RateLimit<12> s;
    int ok = 0;
    for (uint32_t t = 0; t < 600000; t += 1000)
      if (s.allow(t, 60000)) ok++;
    if (ok != 120) why += fmt("one a second for 10 min: %d allowed (want 120); ", ok);
    result("FW-182", why.empty(), why.empty() ? "RateLimit: at most N in any window, sliding; slots free as they age out" : why);
  }
  return 0;
}
