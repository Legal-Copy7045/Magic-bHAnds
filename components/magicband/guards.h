#pragma once
// Small guards the device files use against misuse from Home Assistant or at
// the reader, kept here so the host tests (regression/firmware) can run them:
//  - release_newer: automatic updates install only a newer release, never an
//    older signed one (no rollback through the 3 am job);
//  - RateLimit: at most N events in a sliding window (the reader's play_show
//    action);
//  - UnknownTagLimit: a flood guard on the bands it doesn't know the reader
//    reports to Home Assistant, so a stream of made-up tag IDs can't flood its
//    tag list; ListedBands: bands that were on its list, which never count.

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
// Home Assistant. This is only a flood guard against a stream of made-up IDs
// (a tag emulator at the door), set well above anything people do at a door
// (enrolling a family's bands, a queue of guests with "Ask Home Assistant"):
// at most PER_MIN new IDs a minute and PER_HOUR an hour are reported; one of
// the last UNKNOWN_TAGS_RECENT reported IDs tapped again always is (a retap,
// or "Ask Home Assistant" asking again). Bands on the list, or on it at any
// time before (ListedBands), never go through this.
static constexpr size_t UNKNOWN_TAGS_PER_MIN = 60;
static constexpr size_t UNKNOWN_TAGS_PER_HOUR = 600;
static constexpr size_t UNKNOWN_TAGS_RECENT = 8;
template<size_t PER_MIN, size_t PER_HOUR> struct TagReportLimit {
  RateLimit<PER_MIN> minute;
  RateLimit<PER_HOUR> hour;
  std::array<std::string, UNKNOWN_TAGS_RECENT> recent{};
  size_t next = 0;
  bool allow(const std::string &uid, uint32_t now) {
    if (uid.empty()) return false;
    for (const auto &r : recent)
      if (r == uid) return true;
    // Both windows must have room before either records it.
    RateLimit<PER_MIN> m = minute;
    RateLimit<PER_HOUR> h = hour;
    if (!m.allow(now, 60000UL) || !h.allow(now, 3600000UL)) return false;
    minute = m;
    hour = h;
    recent[next] = uid;
    next = (next + 1) % UNKNOWN_TAGS_RECENT;
    return true;
  }
};
using UnknownTagLimit = TagReportLimit<UNKNOWN_TAGS_PER_MIN, UNKNOWN_TAGS_PER_HOUR>;

// Bands that have been on the reader's allowed list (kept through restarts):
// MagicbHAnds sends only the bands allowed right now, so a household band
// outside its hours or during a lockdown is off the list, but its taps should
// still reach Home Assistant (history, refusal notifications) without counting
// against the unknown-band limit. Holds the last N distinct IDs as 32-bit
// FNV-1a hashes (0 = empty slot); the oldest is replaced when full. A made-up
// ID matching a hash only skips the limit, it isn't let in.
template<size_t N> struct ListedBands {
  std::array<uint32_t, N> slot{};
  uint16_t next = 0;
  static uint32_t hash(const std::string &key) {
    uint32_t x = 2166136261u;
    for (char c : key) {
      x ^= static_cast<uint8_t>(c);
      x *= 16777619u;
    }
    return x ? x : 1;
  }
  bool contains(const std::string &key) const {
    if (key.empty()) return false;
    const uint32_t x = hash(key);
    for (uint32_t s : slot)
      if (s == x) return true;
    return false;
  }
  // `key` as on the list: hex digits, uppercase, no separators.
  void add(const std::string &key) {
    if (key.empty() || contains(key)) return;
    slot[next % N] = hash(key);
    next = static_cast<uint16_t>((next + 1) % N);
  }
  // Every entry of a list in the reader's format, ",UID,UID,".
  void add_list(const std::string &list) {
    size_t from = 0;
    while (from < list.size()) {
      size_t to = list.find(',', from);
      if (to == std::string::npos) to = list.size();
      if (to > from) add(list.substr(from, to - from));
      from = to + 1;
    }
  }
};

}  // namespace magicband
}  // namespace esphome
