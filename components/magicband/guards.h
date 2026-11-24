#pragma once
// Small guards the device files use against misuse from Home Assistant or at
// the reader, kept here so the host tests (regression/firmware) can run them:
//  - release_newer: automatic updates install only a newer release, never an
//    older signed one (no rollback through the 3 am job);
//  - RateLimit: at most N events in a sliding window (the reader's play_show
//    action);
//  - UnknownTagLimit: how many bands it doesn't know the reader reports to
//    Home Assistant, so a stream of made-up tag IDs can't flood its tag list.

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace esphome {
namespace magicband {

// "0.10.31" -> {0, 10, 31}. Empty if it isn't dotted numbers (a suffix such as
// "-beta" after the numbers is ignored).
inline std::vector<uint32_t> release_parts(const std::string &v) {
  std::vector<uint32_t> out;
  size_t i = 0;
  while (i < v.size()) {
    if (v[i] < '0' || v[i] > '9') return {};  // at the start, or right after a dot
    uint64_t n = 0;
    while (i < v.size() && v[i] >= '0' && v[i] <= '9') {
      n = n * 10 + (v[i] - '0');
      if (n > 0xFFFFFFFFull) return {};
      i++;
    }
    out.push_back(static_cast<uint32_t>(n));
    if (i < v.size() && v[i] == '.') {
      i++;
      if (i == v.size()) return {};
    } else if (i < v.size()) {
      break;  // a suffix: ignored
    }
  }
  return out;
}

// Whether `latest` is a newer release than `current` (1.2 = 1.2.0). False when
// either isn't a version, so nothing installs on a malformed manifest.
inline bool release_newer(const std::string &latest, const std::string &current) {
  const auto a = release_parts(latest), b = release_parts(current);
  if (a.empty() || b.empty()) return false;
  for (size_t i = 0; i < a.size() || i < b.size(); i++) {
    const uint32_t x = i < a.size() ? a[i] : 0, y = i < b.size() ? b[i] : 0;
    if (x != y) return x > y;
  }
  return false;
}

// At most N events in any window_ms (millis(), wrap-safe). allow() records the
// event when it's allowed.
template<size_t N> struct RateLimit {
  std::array<uint32_t, N> at{};
  size_t used = 0, next = 0;
  bool allow(uint32_t now, uint32_t window_ms) {
    size_t recent = 0;
    for (size_t i = 0; i < used; i++)
      if (now - at[i] < window_ms) recent++;
    if (recent >= N) return false;
    at[next] = now;  // the oldest slot (millis only goes forward)
    next = (next + 1) % N;
    if (used < N) used++;
    return true;
  }
};

// Bands the reader doesn't know (not on its allowed list) reported to Home
// Assistant as tag scans: each new ID makes a stored tag and a tag entity in
// Home Assistant, so a stream of made-up IDs (a tag emulator at the door) could
// grow its tag list without bound. At most UNKNOWN_TAGS_PER_MIN new IDs a
// minute and UNKNOWN_TAGS_PER_HOUR an hour are reported; one of the last
// UNKNOWN_TAGS_RECENT reported IDs tapped again always is (a retap, or "Ask
// Home Assistant" asking again). Bands on the list never go through this.
static constexpr size_t UNKNOWN_TAGS_PER_MIN = 6;
static constexpr size_t UNKNOWN_TAGS_PER_HOUR = 30;
static constexpr size_t UNKNOWN_TAGS_RECENT = 8;
struct UnknownTagLimit {
  RateLimit<UNKNOWN_TAGS_PER_MIN> minute;
  RateLimit<UNKNOWN_TAGS_PER_HOUR> hour;
  std::array<std::string, UNKNOWN_TAGS_RECENT> recent{};
  size_t next = 0;
  bool allow(const std::string &uid, uint32_t now) {
    if (uid.empty()) return false;
    for (const auto &r : recent)
      if (r == uid) return true;
    // Both windows must have room before either records it.
    RateLimit<UNKNOWN_TAGS_PER_MIN> m = minute;
    RateLimit<UNKNOWN_TAGS_PER_HOUR> h = hour;
    if (!m.allow(now, 60000UL) || !h.allow(now, 3600000UL)) return false;
    minute = m;
    hour = h;
    recent[next] = uid;
    next = (next + 1) % UNKNOWN_TAGS_RECENT;
    return true;
  }
};

}  // namespace magicband
}  // namespace esphome
