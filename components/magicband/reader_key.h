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

// SHA-256 of a short string (FIPS 180-4), for the key fingerprint below.
inline std::array<uint8_t, 32> sha256(const std::string &msg) {
  static constexpr uint32_t K[64] = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
      0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
      0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
      0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
      0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  auto rotr = [](uint32_t x, int n) { return (x >> n) | (x << (32 - n)); };
  std::string m = msg;
  const uint64_t bits = static_cast<uint64_t>(msg.size()) * 8;
  m += static_cast<char>(0x80);
  while (m.size() % 64 != 56)
    m += static_cast<char>(0);
  for (int i = 7; i >= 0; i--)
    m += static_cast<char>((bits >> (8 * i)) & 0xFF);
  for (size_t off = 0; off < m.size(); off += 64) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++)
      w[i] = (static_cast<uint32_t>(static_cast<uint8_t>(m[off + 4 * i])) << 24) |
             (static_cast<uint32_t>(static_cast<uint8_t>(m[off + 4 * i + 1])) << 16) |
             (static_cast<uint32_t>(static_cast<uint8_t>(m[off + 4 * i + 2])) << 8) |
             static_cast<uint32_t>(static_cast<uint8_t>(m[off + 4 * i + 3]));
    for (int i = 16; i < 64; i++) {
      const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; i++) {
      const uint32_t t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
      const uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      hh = g;
      g = f;
      f = e;
      e = d + t1;
      d = c;
      c = b;
      b = a;
      a = t1 + t2;
    }
    h[0] += a;
    h[1] += b;
    h[2] += c;
    h[3] += d;
    h[4] += e;
    h[5] += f;
    h[6] += g;
    h[7] += hh;
  }
  std::array<uint8_t, 32> out{};
  for (int i = 0; i < 32; i++)
    out[i] = static_cast<uint8_t>(h[i / 4] >> (24 - 8 * (i % 4)));
  return out;
}

// Shown as the reader's "Pairing key fingerprint" (diagnostic): the first 8
// hex characters (lowercase) of the SHA-256 of the paired key, or while a first
// pairing waits for its tap, of the waiting key; "none" otherwise. The
// MagicbHAnds integration compares it with its own key's fingerprint
// (hashlib.sha256(key.encode()).hexdigest()[:8]) to know whether the pairing
// that's waiting (or done) is its own, without the key being shown: 32 bits of
// a hash of a 128-256-bit random key give nothing away.
static constexpr const char *NO_FINGERPRINT = "none";
inline std::string reader_key_fingerprint(const ReaderKey &key) {
  if (!reader_paired(key))
    return NO_FINGERPRINT;
  const auto d = sha256(std::string(key.data(), strnlen(key.data(), READER_KEY_SIZE - 1)));
  static const char *HEX = "0123456789abcdef";
  std::string out;
  for (int i = 0; i < 4; i++) {
    out += HEX[d[i] >> 4];
    out += HEX[d[i] & 0xF];
  }
  return out;
}
inline std::string reader_pairing_fingerprint(const ReaderKey &stored, const ReaderKey &pending, uint32_t pending_until,
                                              uint32_t now) {
  if (reader_paired(stored))
    return reader_key_fingerprint(stored);
  if (reader_paired(pending) && static_cast<int32_t>(pending_until - now) > 0)
    return reader_key_fingerprint(pending);
  return NO_FINGERPRINT;
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
