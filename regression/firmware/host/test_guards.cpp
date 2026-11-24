// components/magicband/guards.h: release_newer (automatic updates never go
// back), RateLimit, UnknownTagLimit / AskTagLimit, ListedBands and
// image_version_ok (an update image's own version).
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
  // FW-183 BUG-020: ListedBands remembers bands that were on the list; AskTagLimit is 20 a minute / 200 an hour
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
    // the relaxed limit for Ask Home Assistant without MagicbHAnds
    AskTagLimit A;
    int ok = 0;
    for (int i = 0; i < 40; i++)
      if (A.allow(fmt("04%012X", 1000 + i), 1000 + i * 1000)) ok++;
    if (ok != 20) why += fmt("Ask HA: %d of 40 new IDs in 40 s (want 20); ", ok);
    AskTagLimit H;
    ok = 0;
    for (int i = 0; i < 1200; i++)  // one new ID every 3 s for an hour
      if (H.allow(fmt("0A0B%06X", i), 10 + i * 3000)) ok++;
    if (ok != 200) why += fmt("Ask HA: %d new IDs in an hour at one per 3 s (want 200); ", ok);
    if (ASK_TAGS_PER_MIN <= UNKNOWN_TAGS_PER_MIN || ASK_TAGS_PER_HOUR <= UNKNOWN_TAGS_PER_HOUR) why += "the Ask HA limit isn't higher; ";
    result("FW-183", why.empty(), why.empty() ? "ListedBands: IDs from every list are remembered (last 128, oldest replaced), re-adding changes nothing, trivially copyable for restore; AskTagLimit: 20 new a minute, 200 an hour" : why);
  }
  // FW-184 SEC-016: image_version_ok compares the image's own (signed) version with the running one
  {
    std::string why;
    struct C { const char *image, *running; bool want; } cs[] = {
        {"mb-0.10.33", "0.10.32", true},  {"mb-0.10.32", "0.10.32", true},  {"mb-0.11.0", "0.10.32", true},  {"mb-1.0.0", "0.10.99", true},
        {"mb-0.10.31", "0.10.32", false}, {"mb-0.9.99", "0.10.32", false},  {"mb-0.10.4", "0.10.32", false}, {"1", "0.10.32", false},
        {"", "0.10.32", false},           {"mb-", "0.10.32", false},        {"mb-abc", "0.10.32", false},    {"0.10.33", "0.10.32", false},
        {"MB-0.10.33", "0.10.32", false}, {"xmb-0.10.33", "0.10.32", false}, {"mb-0.10.33-beta", "0.10.32", true}, {"mb-0.10.32", "0.10.32.1", false},
        {"mb-0.10.31", "my-build", true}, {"1", "", true},
    };
    for (auto &c : cs)
      if (image_version_ok(c.image, c.running) != c.want)
        why += fmt("image_version_ok(%s, %s) = %d; ", c.image, c.running, !c.want);
    result("FW-184", why.empty(), why.empty() ? fmt("%zu cases: an image boots only if its own version is mb-<release> not older than the running release (a reinstall is fine); images from before versions were embedded ('1'), malformed or unprefixed ones are refused; a running build without a release compares nothing", sizeof(cs) / sizeof(*cs)) : why);
  }
  return 0;
}
