// components/magicband/guards.h: release_newer (automatic updates never go
// back), RateLimit, UnknownTagLimit (the unknown-band flood guard) and
// ListedBands.
#include <string>
#include <cstring>
#include <type_traits>
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
  // FW-181 UnknownTagLimit: a flood guard only: 60 new a minute, 600 an hour, recent ones pass, nothing recorded when refused
  {
    std::string why;
    static_assert(UNKNOWN_TAGS_PER_MIN == 60 && UNKNOWN_TAGS_PER_HOUR == 600, "the flood guard is 60 a minute / 600 an hour");
    UnknownTagLimit L;
    int ok = 0;
    for (int i = 0; i < 100; i++)
      if (L.allow(fmt("04%012X", i), 1000 + i * 100)) ok++;
    if (ok != 60) why += fmt("%d of 100 new IDs in 10 s (want 60); ", ok);
    if (!L.allow(fmt("04%012X", 59), 11000)) why += "a reported ID tapped again was refused; ";
    if (L.allow(fmt("04%012X", 80), 11100)) why += "a refused ID got in on its second try within the minute; ";
    if (!L.allow(fmt("04%012X", 80), 1000 + 60000)) why += "a new ID a minute later was refused; ";
    if (L.allow("", 200000)) why += "an empty ID was allowed; ";
    // a family of 20 enrolling at the door in a minute: every band is reported
    UnknownTagLimit F;
    ok = 0;
    for (int i = 0; i < 20; i++)
      if (F.allow(fmt("04%012X", 0xF00 + i), 5000 + i * 3000)) ok++;
    if (ok != 20) why += fmt("a family of 20 enrolling in a minute: %d reported (want 20); ", ok);
    UnknownTagLimit H;
    ok = 0;
    for (int i = 0; i < 3600; i++)  // one new ID every second for an hour
      if (H.allow(fmt("0A0B%04X", i), 10 + i * 1000)) ok++;
    if (ok != 600) why += fmt("%d new IDs in an hour at one per second (want 600); ", ok);
    if (!H.allow(fmt("0A0B%04X", 99999), 10 + 3600000 + 5000)) why += "a new ID after the hour was refused; ";
    // millis() wrap
    UnknownTagLimit W;
    ok = 0;
    for (int i = 0; i < 100; i++)
      if (W.allow(fmt("0E0F%04X", i), 0xFFFFFFFFu - 3000 + i * 100)) ok++;
    if (ok != 60) why += fmt("across the millis() wrap: %d of 100 (want 60); ", ok);
    result("FW-181", why.empty(), why.empty() ? "UnknownTagLimit (flood guard): 60 new IDs a minute and 600 an hour; a family of 20 enrolling in a minute all reported; a reported ID tapped again passes; a refused one isn't recorded; wrap-safe" : why);
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
  // FW-183 BUG-020: ListedBands remembers bands that were on the list
  {
    std::string why;
    static_assert(std::is_trivially_copyable<ListedBands<128>>::value, "ListedBands must be trivially copyable (restore_value)");
    ListedBands<128> L{};
    if (L.contains("") || L.contains("04A1B2C3D4E5F6")) why += "an empty set contains something; ";
    L.add_list(",04A1B2C3D4E5F6,0A0B0C0D,11223344556677889900,");
    for (const char *k : {"04A1B2C3D4E5F6", "0A0B0C0D", "11223344556677889900"})
      if (!L.contains(k)) why += fmt("%s from the list not remembered; ", k);
    if (L.contains("0A0B0C0E") || L.contains("")) why += "an ID never listed is contained; ";
    const ListedBands<128> before = L;
    L.add_list(",0A0B0C0D,04A1B2C3D4E5F6,");  // the same list again (every sync): nothing changes, so nothing is written
    if (memcmp(&before, &L, sizeof L) != 0) why += "re-adding listed IDs changed the store (flash writes on every sync); ";
    L.add_list("");
    L.add_list(",,");
    if (memcmp(&before, &L, sizeof L) != 0) why += "an empty list changed the store; ";
    // a household of 200 bands: the last 128 distinct ones are kept, the oldest go
    ListedBands<128> B{};
    for (int i = 0; i < 200; i++) B.add(fmt("04%012X", i));
    int kept = 0;
    for (int i = 0; i < 200; i++) kept += B.contains(fmt("04%012X", i));
    if (kept != 128 || !B.contains(fmt("04%012X", 199)) || B.contains(fmt("04%012X", 0))) why += fmt("200 IDs: %d kept, newest %d, oldest %d; ", kept, B.contains(fmt("04%012X", 199)), B.contains(fmt("04%012X", 0)));
    // a restored copy (the bytes as stored) still works
    ListedBands<128> R;
    memcpy(&R, &B, sizeof R);
    if (!R.contains(fmt("04%012X", 150))) why += "a byte copy lost an ID; ";
    result("FW-183", why.empty(), why.empty() ? "ListedBands: IDs from every list are remembered (last 128, oldest replaced), re-adding changes nothing, trivially copyable for restore" : why);
  }
  return 0;
}
