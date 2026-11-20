#pragma once
// The reader's pairing key: once the MagicbHAnds integration has paired with a
// reader, the actions that change who the reader lets in (set_known_bands,
// set_band_colours, accept, deny) need the key. The integration keeps it in its
// own storage, so other Home Assistant users, who can call any ESPHome action,
// can't use them. A reader with no key (never paired, or not used with the
// integration) works as before.
//
// A paired reader never takes a different key over the network: only the key
// holder can release it (unpair), or someone with the reader in hand can erase
// it over USB (the web installer's "Erase device"), which anyone with USB access
// could do anyway. So no Home Assistant user can take a reader over, even right
// after it restarts or loses power.

#include <array>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <string>

namespace esphome {
namespace magicband {

static constexpr size_t READER_KEY_SIZE = 65;  // 64 hex characters + terminator
// First pairing waits this long for a band tap on the reader to confirm it.
static constexpr uint32_t PAIR_CONFIRM_MS = 2 * 60 * 1000;
// Returned by reader_request_pair while a first pairing waits for its tap.
static constexpr const char *PAIRING_PENDING = "PAIRING_PENDING: tap any band on the reader within 2 minutes to finish pairing";
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
inline std::string reader_pair(ReaderKey &stored, const std::string &key) {
  if (key.size() < 32 || key.size() > READER_KEY_SIZE - 1)
    return "The key must be 32 to 64 hex characters";
  for (char c : key)
    if (!std::isxdigit(static_cast<unsigned char>(c)))
      return "The key must be 32 to 64 hex characters";
  if (reader_paired(stored)) {
    if (reader_key_ok(stored, key))
      return "";
    return "This reader is paired with another key. Release it from the Home Assistant that paired it "
           "(magicband.unpair_reader), or erase it over USB with the web installer (Erase device) and add it again";
  }
  stored.fill(0);
  memcpy(stored.data(), key.data(), key.size());
  return "";
}

// First pairing needs someone at the reader: the key waits as `pending` until a
// band is tapped on the reader (reader_confirm_pair) within PAIR_CONFIRM_MS. A
// Home Assistant user elsewhere can't tap, so can't claim a new reader; and a
// pending key can't be replaced by another until it expires, so the
// integration notices (its own request is refused) instead of someone else's
// key being confirmed unnoticed.
// Returns "" when paired (already, with this key), PAIRING_PENDING when waiting
// for the tap, else why not.
inline std::string reader_request_pair(ReaderKey &stored, ReaderKey &pending, uint32_t &pending_until,
                                       const std::string &key, uint32_t now) {
  if (reader_paired(stored))
    return reader_pair(stored, key);  // the same key: fine; another: refused
  ReaderKey check{};
  const std::string err = reader_pair(check, key);  // validates the key's format
  if (!err.empty())
    return err;
  const bool waiting = reader_paired(pending) && static_cast<int32_t>(pending_until - now) > 0;
  if (waiting && !reader_key_ok(pending, key))
    return "Another pairing request is already waiting on this reader (not from this key). Don't tap a band: "
           "wait 2 minutes and try again";
  pending = check;
  pending_until = now + PAIR_CONFIRM_MS;
  return PAIRING_PENDING;
}

// A band was tapped: if a first pairing is waiting, this confirms it. Returns true when it did.
inline bool reader_confirm_pair(ReaderKey &stored, ReaderKey &pending, uint32_t pending_until, uint32_t now) {
  if (reader_paired(stored) || !reader_paired(pending) || static_cast<int32_t>(pending_until - now) <= 0)
    return false;
  stored = pending;
  pending.fill(0);
  return true;
}

// Releases the pairing; needs the current key. Returns "" when done.
inline std::string reader_unpair(ReaderKey &stored, const std::string &key) {
  if (!reader_paired(stored))
    return "";
  if (!reader_key_ok(stored, key))
    return "Wrong key";
  stored.fill(0);
  return "";
}

}  // namespace magicband
}  // namespace esphome
