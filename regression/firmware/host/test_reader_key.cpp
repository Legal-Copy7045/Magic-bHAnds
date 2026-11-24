// The reader's pairing key (components/magicband/reader_key.h).
#include <string>
#include "test_common.h"
#include "esphome/components/magicband/reader_key.h"

using namespace esphome::magicband;
using hosttest::fmt;
using hosttest::result;

static const std::string K1 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";  // 64
static const std::string K2 = "fedcba9876543210fedcba9876543210";                                  // 32
static std::string ok(const std::string &s) { return s.empty() ? "\"\"" : "\"" + s.substr(0, 60) + "\""; }

int main() {
  // FW-130 an unpaired reader lets anyone use the protected actions
  {
    ReaderKey st{};
    bool good = !reader_paired(st) && reader_key_ok(st, "") && reader_key_ok(st, "anything") && reader_key_ok(st, K1);
    result("FW-130", good, good ? "unpaired: reader_key_ok true for any key, reader_paired false" : "unpaired reader refused a key");
  }
  // FW-131 key format: 32-64 hex characters only
  {
    std::string why;
    const std::string bad[] = {"", std::string(31, 'a'), std::string(65, 'a'), std::string(31, 'a') + "g", std::string(32, 'G'),
                               std::string(40, 'a') + " ", std::string(16, 'a') + "-" + std::string(16, 'a'), std::string(32, 'a').insert(5, 1, '\0')};
    for (const auto &k : bad) {
      ReaderKey st{};
      std::string r = reader_pair(st, k);
      if (r.empty() || reader_paired(st)) why += fmt("accepted a bad key of %zu chars; ", k.size());
      ReaderKey p{}, pend{};
      uint32_t until = 0;
      r = reader_request_pair(p, pend, until, k, 1000);
      if (r == PAIRING_PENDING || reader_paired(pend)) why += fmt("request_pair took a bad key of %zu chars; ", k.size());
    }
    for (const auto &k : {std::string(32, 'a'), std::string(64, 'F'), K1, K2}) {
      ReaderKey st{};
      if (!reader_pair(st, k).empty() || !reader_paired(st) || !reader_key_ok(st, k)) why += fmt("refused a good key of %zu chars; ", k.size());
      if (st[READER_KEY_SIZE - 1] != 0) why += "stored key not terminated; ";
    }
    result("FW-131", why.empty(), why.empty() ? "keys under 32, over 64, non-hex or with NUL are refused; 32 and 64 hex chars pair and stay terminated" : why);
  }
  // FW-132 a paired reader only takes its own key
  {
    std::string why;
    ReaderKey st{};
    reader_pair(st, K1);
    if (reader_key_ok(st, K2)) why += "other key ok; ";
    if (reader_key_ok(st, "")) why += "empty key ok; ";
    if (reader_key_ok(st, K1.substr(0, 63))) why += "prefix ok; ";
    if (reader_key_ok(st, K1 + "0")) why += "longer key ok; ";
    std::string flip = K1;
    flip[63] = 'e';
    if (reader_key_ok(st, flip)) why += "last-char change ok; ";
    flip = K1;
    flip[0] = '1';
    if (reader_key_ok(st, flip)) why += "first-char change ok; ";
    if (!reader_key_ok(st, K1)) why += "own key refused; ";
    std::string r = reader_pair(st, K2);
    if (r.empty()) why += "re-pair with another key accepted; ";
    if (!reader_key_ok(st, K1)) why += "re-pair attempt changed the key; ";
    if (!reader_pair(st, K1).empty()) why += "re-pair with the same key refused; ";
    std::string upper = K1;
    for (auto &c : upper) c = toupper(c);
    const bool case_sensitive = !reader_key_ok(st, upper);
    result("FW-132", why.empty(), why.empty() ? fmt("only the stored key (exact length, every char) is accepted; another key can't re-pair (%s); comparison is %s",
                                                     ok(r).c_str(), case_sensitive ? "case-sensitive" : "case-insensitive")
                                              : why);
  }
  // FW-133 first pairing waits for a tap: request -> pending, confirm within 2 min
  {
    std::string why;
    ReaderKey st{}, pend{};
    uint32_t until = 0;
    std::string r = reader_request_pair(st, pend, until, K1, 5000);
    if (r != PAIRING_PENDING) why += "request didn't return PAIRING_PENDING: " + ok(r) + "; ";
    if (reader_paired(st)) why += "paired before the tap; ";
    if (!reader_key_ok(st, K2)) why += "pending key already enforced; ";
    if (until != 5000 + PAIR_CONFIRM_MS) why += "wrong deadline; ";
    if (!reader_confirm_pair(st, pend, until, 5000 + PAIR_CONFIRM_MS - 1)) why += "tap 1 ms before the deadline didn't confirm; ";
    if (!reader_paired(st) || !reader_key_ok(st, K1) || reader_key_ok(st, K2)) why += "not paired with the requested key after the tap; ";
    if (reader_paired(pend)) why += "pending key not cleared; ";
    if (reader_confirm_pair(st, pend, until, 6000)) why += "a second tap confirmed again; ";
    if (reader_request_pair(st, pend, until, K1, 7000) != "") why += "paired reader: request with the same key not \"\"; ";
    if (reader_request_pair(st, pend, until, K2, 7000).empty()) why += "paired reader: request with another key accepted; ";
    result("FW-133", why.empty(), why.empty() ? "request -> PAIRING_PENDING; a tap before the deadline pairs with that key; a paired reader answers \"\" to its key and refuses others" : why);
  }
  // FW-134 rejection paths: expiry, a second requester, no pending, wrap-around
  {
    std::string why;
    ReaderKey st{}, pend{};
    uint32_t until = 0;
    reader_request_pair(st, pend, until, K1, 1000);
    if (reader_confirm_pair(st, pend, until, 1000 + PAIR_CONFIRM_MS)) why += "tap at the deadline confirmed; ";
    if (reader_paired(st)) why += "paired after expiry; ";
    // another key while one waits is refused, and doesn't replace it
    ReaderKey st2{}, pend2{};
    uint32_t until2 = 0;
    reader_request_pair(st2, pend2, until2, K1, 1000);
    std::string r = reader_request_pair(st2, pend2, until2, K2, 2000);
    if (r == PAIRING_PENDING || r.empty()) why += "a second key replaced a waiting request; ";
    if (!reader_key_ok(pend2, K1)) why += "the waiting key changed; ";
    // the same key again renews
    r = reader_request_pair(st2, pend2, until2, K1, 3000);
    if (r != PAIRING_PENDING || until2 != 3000 + PAIR_CONFIRM_MS) why += "same key didn't renew the wait; ";
    // after the wait expires another key may ask
    r = reader_request_pair(st2, pend2, until2, K2, 3000 + PAIR_CONFIRM_MS);
    if (r != PAIRING_PENDING || !reader_key_ok(pend2, K2)) why += "after expiry another key couldn't ask; ";
    // a tap with nothing pending does nothing
    ReaderKey st3{}, pend3{};
    if (reader_confirm_pair(st3, pend3, 0, 10) || reader_paired(st3)) why += "tap with nothing pending paired; ";
    // millis() wrap-around: requested just before 2^32
    ReaderKey st4{}, pend4{};
    uint32_t until4 = 0;
    const uint32_t near = 0xFFFFFFFFu - 1000;
    reader_request_pair(st4, pend4, until4, K1, near);
    if (!reader_confirm_pair(st4, pend4, until4, near + 60000)) why += "wrap-around: tap 60 s later (after millis wrapped) refused; ";
    ReaderKey st5{}, pend5{};
    uint32_t until5 = 0;
    reader_request_pair(st5, pend5, until5, K1, near);
    if (reader_confirm_pair(st5, pend5, until5, near + PAIR_CONFIRM_MS + 5)) why += "wrap-around: tap after the deadline accepted; ";
    result("FW-134", why.empty(), why.empty() ? "expired waits, a second requester, taps with nothing pending and millis() wrap-around are all handled" : why);
  }
  // FW-135 unpair needs the key
  {
    std::string why;
    ReaderKey st{};
    reader_pair(st, K1);
    if (reader_unpair(st, K2).empty() || !reader_paired(st)) why += "unpaired with the wrong key; ";
    if (reader_unpair(st, "").empty() || !reader_paired(st)) why += "unpaired with no key; ";
    if (!reader_unpair(st, K1).empty() || reader_paired(st)) why += "own key didn't unpair; ";
    for (char c : st)
      if (c) { why += "key bytes left behind; "; break; }
    if (!reader_unpair(st, "whatever").empty()) why += "unpair of an unpaired reader not \"\"; ";
    if (!reader_pair(st, K2).empty() || !reader_key_ok(st, K2)) why += "couldn't pair again after unpair; ";
    result("FW-135", why.empty(), why.empty() ? "unpair refuses a wrong or empty key, clears every key byte with the right one, and is a no-op when unpaired" : why);
  }
  return 0;
}
