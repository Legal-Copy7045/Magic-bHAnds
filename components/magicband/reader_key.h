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
// Returned (at the start of the message) when another key's first pairing is
// waiting: the requester lost the race and shouldn't ask anyone to tap.
static constexpr const char *PAIRING_BUSY = "PAIRING_BUSY";
// Returned (at the start of the message) when this key's own wait has just
// expired without a tap: it may ask again PAIR_CONFIRM_MS after the expiry.
static constexpr const char *PAIRING_COOLDOWN = "PAIRING_COOLDOWN";
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
// Home Assistant user elsewhere can't tap, so can't claim a new reader.
// The first request wins: while it waits no other key can replace it (the
// other requester gets PAIRING_BUSY, so the integration notices it lost
// instead of someone else's key being confirmed unnoticed). Asking again with
// the waiting key answers PAIRING_PENDING but doesn't extend the wait, and once
// a wait has expired the same key must leave a PAIR_CONFIRM_MS gap
// (PAIRING_COOLDOWN) in which any other key may ask, so no one key can hold a
// new reader's pairing open indefinitely.
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
  if (reader_paired(pending)) {
    // Time since the waiting (or last) request, valid for 49 days of millis().
    const uint32_t age = now - (pending_until - PAIR_CONFIRM_MS);
    const bool same = reader_key_ok(pending, key);
    if (age < PAIR_CONFIRM_MS) {
      if (same)
        return PAIRING_PENDING;  // still waiting: the deadline stays where it is
      return std::string(PAIRING_BUSY) +
             ": another pairing request is already waiting on this reader (not from this key). Don't tap a band: "
             "wait 2 minutes and try again";
    }
    if (same && age < 2 * PAIR_CONFIRM_MS)
      return std::string(PAIRING_COOLDOWN) +
             ": this key's pairing request expired without a tap; it can ask again 2 minutes after that";
  }
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
