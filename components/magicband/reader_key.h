#pragma once
// The reader's pairing key: once the MagicbHAnds integration has paired with a
// reader, the actions that change who the reader lets in (set_known_bands,
// set_band_colours, accept, deny) need the key. The integration keeps it in its
// own storage, so other Home Assistant users, who can call any ESPHome action,
// can't use them. A reader with no key (never paired, or not used with the
// integration) works as before.
//
// A paired reader takes a new key only in the first PAIR_WINDOW_MS after a real
// power-on (unplugging it), not after a software restart, which any Home
// Assistant user can trigger.

#include <array>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <string>

namespace esphome {
namespace magicband {

static constexpr size_t READER_KEY_SIZE = 65;  // 64 hex characters + terminator
static constexpr uint32_t PAIR_WINDOW_MS = 10 * 60 * 1000;
using ReaderKey = std::array<char, READER_KEY_SIZE>;

inline bool reader_paired(const ReaderKey &stored) { return stored[0] != 0; }

// Whether `given` may use the protected actions: always if the reader isn't
// paired, otherwise only with the stored key (compared in constant time).
inline bool reader_key_ok(const ReaderKey &stored, const std::string &given) {
  if (!reader_paired(stored))
    return true;
  const size_t n = strnlen(stored.data(), READER_KEY_SIZE - 1);
  if (given.size() != n)
    return false;
  uint8_t diff = 0;
  for (size_t i = 0; i < n; i++)
    diff |= static_cast<uint8_t>(stored[i] ^ given[i]);
  return diff == 0;
}

// Pairs with `key` (32-64 hex characters). Returns "" when paired (or already
// paired with this key), else why not.
inline std::string reader_pair(ReaderKey &stored, const std::string &key, bool in_window) {
  if (key.size() < 32 || key.size() > READER_KEY_SIZE - 1)
    return "The key must be 32 to 64 hex characters";
  for (char c : key)
    if (!std::isxdigit(static_cast<unsigned char>(c)))
      return "The key must be 32 to 64 hex characters";
  if (reader_paired(stored) && !reader_key_ok(stored, key) && !in_window)
    return "This reader is paired with another key. Unplug it for a few seconds, then it accepts a new key "
           "for 10 minutes";
  stored.fill(0);
  memcpy(stored.data(), key.data(), key.size());
  return "";
}

}  // namespace magicband
}  // namespace esphome
