#include "magicband.h"

#ifdef USE_ESP32

#include "esphome/components/json/json_util.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

#ifdef USE_ESP32_BLE_TRACKER
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"
#endif

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstring>

namespace esphome::magicband {

static const char *const TAG = "magicband";

// If the BLE stack never confirms a config/start/stop, give up after this long.
static constexpr uint32_t GAP_TIMEOUT_MS = 1000;
// Light entity changes are sent once the value has been stable this long.
static constexpr uint32_t LIGHT_DEBOUNCE_MS = 250;
// A burst is split into slots; each slot can carry a different version of the
// advertisement (E1/E2 prefix for prefix mode BOTH, the fast-mode ping).
static constexpr uint32_t SLOT_MS = 100;
// Fast mode: every FAST_EVERY-th slot carries the fast ping (20% of airtime).
static constexpr uint32_t FAST_EVERY = 5;
// Fast mode warm-up runs when the bridge has been quiet for this long.
static constexpr uint32_t WARMUP_AFTER_IDLE_MS = 30000;
static const uint8_t FAST_PING[] = {0xCC, 0x03, 0x00, 0x01, 0x00};

static bool is_cc(const std::vector<uint8_t> &p) {
  if (!p.empty() && p[0] == 0xCC)
    return true;
  return p.size() > 2 && (p[0] == 0xE1 || p[0] == 0xE2) && p[2] == 0xCC;
}

static inline uint8_t vib_byte(uint8_t v) { return 0xB0 | (v & 0x0F); }
static inline uint8_t col(uint8_t mode, uint8_t c) { return mode | (c & 0x1F); }
static inline uint8_t rgb6(uint8_t v, bool flash) {
  uint8_t six = static_cast<uint8_t>((v * 63 + 127) / 255);
  return (flash ? 0x80 : 0x00) | static_cast<uint8_t>(six << 1);
}

void MagicBand::setup() {
  this->adv_params_ = {
      .adv_int_min = static_cast<uint16_t>(this->min_interval_ms_ / 0.625f),
      .adv_int_max = static_cast<uint16_t>(this->max_interval_ms_ / 0.625f),
      .adv_type = ADV_TYPE_NONCONN_IND,
      .own_addr_type = BLE_ADDR_TYPE_PUBLIC,
      .peer_addr = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00},
      .peer_addr_type = BLE_ADDR_TYPE_PUBLIC,
      .channel_map = ADV_CHNL_ALL,
      .adv_filter_policy = ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY,
  };
}

void MagicBand::dump_config() {
  ESP_LOGCONFIG(TAG,
                "MagicBand+ broadcaster:\n"
                "  Duration: %ums\n"
                "  Interval: %u-%ums\n"
                "  Queue size: %u",
                (unsigned) this->duration_ms_, (unsigned) this->min_interval_ms_, (unsigned) this->max_interval_ms_,
                this->queue_size_);
#ifndef CONFIG_BT_CONTROLLER_DISABLED
  ESP_LOGCONFIG(TAG, "  TX power: %ddBm", this->tx_power_dbm_);
#endif
  ESP_LOGCONFIG(TAG,
                "  Pause scanning while broadcasting: %s\n"
                "  Prefix mode: %s\n"
                "  Fast mode: %s (warm-up %ums)",
                YESNO(this->pause_scanning_), prefix_mode_name(this->prefix_mode_), YESNO(this->fast_mode_),
                (unsigned) this->fast_warmup_ms_);
}

void MagicBand::loop() {
  const uint32_t now = millis();

  if (this->light_pending_ && now - this->light_changed_at_ >= LIGHT_DEBOUNCE_MS) {
    this->light_pending_ = false;
    if (this->light_on_) {
      this->send_rgb(this->light_rgb_[0], this->light_rgb_[1], this->light_rgb_[2], 0, TIMING_ALWAYS_ON);
      this->light_was_on_ = true;
    } else if (this->light_was_on_) {
      this->send_off();
      this->light_was_on_ = false;
    }
  }

  switch (this->state_) {
    case State::IDLE:
      if (!this->queue_.empty() && esp32_ble::global_ble != nullptr && esp32_ble::global_ble->is_active()) {
        this->start_next_();
      } else if (this->queue_.empty() && this->scan_paused_) {
        this->resume_scan_();
      }
      break;
    case State::CONFIGURING:
      if (now - this->state_since_ > GAP_TIMEOUT_MS) {
        ESP_LOGW(TAG, "Timed out configuring advertisement data");
        this->state_ = State::IDLE;
      }
      break;
    case State::ADVERTISING:
      if (this->stop_requested_ || now - this->state_since_ >= this->current_.duration_ms) {
        this->request_stop_();
      } else if ((this->swap_in_burst_ || this->ping_in_burst_) && now - this->last_swap_ >= SLOT_MS) {
        // Swap the advertisement data in place while advertising.
        this->last_swap_ = now;
        this->slot_++;
        if (this->ping_in_burst_ && this->slot_ % FAST_EVERY == FAST_EVERY - 1) {
          esp_ble_gap_config_adv_data_raw(this->adv_ping_, this->adv_ping_len_);
        } else {
          if (this->swap_in_burst_)
            this->showing_alt_ = !this->showing_alt_;
          esp_ble_gap_config_adv_data_raw(this->showing_alt_ ? this->adv_alt_ : this->adv_,
                                          this->showing_alt_ ? this->adv_alt_len_ : this->adv_len_);
        }
      }
      break;
    case State::STOPPING:
      if (now - this->state_since_ > GAP_TIMEOUT_MS) {
        ESP_LOGW(TAG, "Timed out stopping advertising");
        this->state_ = State::IDLE;
      }
      break;
  }
}

// Build a raw advertisement: Flags AD + manufacturer-specific AD (0xFF) with
// Disney's company ID, then the payload. Returns its length.
static size_t build_adv(uint8_t *adv, const std::vector<uint8_t> &payload) {
  size_t n = 0;
  adv[n++] = 0x02;
  adv[n++] = 0x01;
  adv[n++] = 0x06;
  adv[n++] = static_cast<uint8_t>(1 + 2 + payload.size());
  adv[n++] = 0xFF;
  adv[n++] = DISNEY_COMPANY_ID & 0xFF;
  adv[n++] = DISNEY_COMPANY_ID >> 8;
  memcpy(adv + n, payload.data(), payload.size());
  return n + payload.size();
}

void MagicBand::start_next_() {
  this->current_ = std::move(this->queue_.front());
  this->queue_.pop_front();
  this->stop_requested_ = false;
  this->pause_scan_();

  // Fast mode warm-up: after a quiet spell, send the fast ping on its own first
  // so bands are listening when the effect arrives.
  const uint32_t now = millis();
  if (this->fast_mode_ && this->fast_warmup_ms_ > 0 && !is_cc(this->current_.payload) &&
      (!this->ever_broadcast_ || now - this->last_broadcast_end_ > WARMUP_AFTER_IDLE_MS)) {
    ESP_LOGD(TAG, "Fast mode: waking bands for %ums first", (unsigned) this->fast_warmup_ms_);
    this->queue_.push_front(std::move(this->current_));
    this->current_ = Command{std::vector<uint8_t>(FAST_PING, FAST_PING + sizeof(FAST_PING)), this->fast_warmup_ms_};
  }
  this->ever_broadcast_ = true;

  // E1 00 / E2 00 prefix (seen in park captures). ALTERNATE flips it on each new
  // command, which in testing makes repeats more reliable. BOTH (experimental)
  // also flips between the two versions within one burst.
  this->swap_in_burst_ = false;
  std::vector<uint8_t> ping(FAST_PING, FAST_PING + sizeof(FAST_PING));
  bool can_prefix = this->current_.payload.size() + 2 <= MAX_PAYLOAD_LEN && this->current_.payload[0] != 0xE1 &&
                    this->current_.payload[0] != 0xE2;
  if (this->prefix_mode_ != PREFIX_OFF && can_prefix) {
    uint8_t prefix = this->next_prefix_e2_ ? 0xE2 : 0xE1;
    this->next_prefix_e2_ = !this->next_prefix_e2_;
    std::vector<uint8_t> other = this->current_.payload;
    this->current_.payload.insert(this->current_.payload.begin(), {prefix, 0x00});
    ping.insert(ping.begin(), {prefix, 0x00});
    if (this->prefix_mode_ == PREFIX_BOTH) {
      other.insert(other.begin(), {static_cast<uint8_t>(prefix == 0xE1 ? 0xE2 : 0xE1), 0x00});
      this->adv_alt_len_ = build_adv(this->adv_alt_, other);
      this->swap_in_burst_ = true;
    }
  }
  this->adv_len_ = build_adv(this->adv_, this->current_.payload);
  this->showing_alt_ = false;
  this->slot_ = 0;
  // Fast mode: mix the fast ping into the burst (not into pings themselves).
  this->ping_in_burst_ = this->fast_mode_ && !is_cc(this->current_.payload);
  if (this->ping_in_burst_)
    this->adv_ping_len_ = build_adv(this->adv_ping_, ping);

  char hex[MAX_PAYLOAD_LEN * 3 + 1];
  format_hex_pretty_to(hex, this->current_.payload.data(), this->current_.payload.size(), ' ');
  ESP_LOGD(TAG, "Broadcasting 83 01 %s for %ums%s%s", hex, (unsigned) this->current_.duration_ms,
           this->swap_in_burst_ ? " (switching E1/E2 within the burst)" : "",
           this->ping_in_burst_ ? " (with fast-mode ping)" : "");

#ifndef CONFIG_BT_CONTROLLER_DISABLED
  esp_err_t err = esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV, this->tx_power_);
  if (err != ESP_OK)
    ESP_LOGW(TAG, "esp_ble_tx_power_set failed: %s", esp_err_to_name(err));
#endif

  esp_err_t cfg = esp_ble_gap_config_adv_data_raw(this->adv_, this->adv_len_);
  if (cfg != ESP_OK) {
    ESP_LOGE(TAG, "esp_ble_gap_config_adv_data_raw failed: %s", esp_err_to_name(cfg));
    return;
  }
  this->state_ = State::CONFIGURING;
  this->state_since_ = millis();
}

const char *MagicBand::prefix_mode_name(uint8_t mode) {
  switch (mode) {
    case PREFIX_OFF:
      return "off";
    case PREFIX_BOTH:
      return "both";
    default:
      return "alternate";
  }
}

void MagicBand::set_prefix_mode_by_name(const std::string &input) {
  std::string s;
  for (char c : input)
    s.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
  if (s.rfind("off", 0) == 0)
    this->prefix_mode_ = PREFIX_OFF;
  else if (s.rfind("both", 0) == 0)
    this->prefix_mode_ = PREFIX_BOTH;
  else
    this->prefix_mode_ = PREFIX_ALTERNATE;
  ESP_LOGI(TAG, "Prefix mode: %s", prefix_mode_name(this->prefix_mode_));
}

void MagicBand::pause_scan_() {
#ifdef USE_ESP32_BLE_TRACKER
  auto *tracker = esp32_ble_tracker::global_esp32_ble_tracker;
  if (!this->pause_scanning_ || this->scan_paused_ || tracker == nullptr)
    return;
  if (tracker->get_scanner_state() == esp32_ble_tracker::ScannerState::RUNNING ||
      tracker->get_scanner_state() == esp32_ble_tracker::ScannerState::STARTING) {
    ESP_LOGD(TAG, "Pausing BLE scanning while broadcasting");
    tracker->stop_scan();
    this->scan_paused_ = true;
  }
#endif
}

void MagicBand::resume_scan_() {
#ifdef USE_ESP32_BLE_TRACKER
  auto *tracker = esp32_ble_tracker::global_esp32_ble_tracker;
  if (tracker == nullptr) {
    this->scan_paused_ = false;
    return;
  }
  auto state = tracker->get_scanner_state();
  if (state == esp32_ble_tracker::ScannerState::RUNNING || state == esp32_ble_tracker::ScannerState::STARTING) {
    // Back up (we kicked it, or a proxy connection restarted it).
    this->scan_paused_ = false;
    ESP_LOGD(TAG, "BLE scanning resumed");
    return;
  }
  // Re-enable continuous scanning. The tracker only re-evaluates restarting on
  // its own state changes, so also start it explicitly once it's idle (the
  // same call ESPHome's esp32_ble_tracker.start_scan action uses). Called every
  // loop until the scanner reports it is running again.
  tracker->set_scan_continuous(true);
  if (state == esp32_ble_tracker::ScannerState::IDLE)
    tracker->start_scan_if_idle();
#else
  this->scan_paused_ = false;
#endif
}

void MagicBand::request_stop_() {
  esp_err_t err = esp_ble_gap_stop_advertising();
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "esp_ble_gap_stop_advertising failed: %s", esp_err_to_name(err));
    this->state_ = State::IDLE;
    return;
  }
  this->state_ = State::STOPPING;
  this->state_since_ = millis();
}

void MagicBand::gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
  switch (event) {
    case ESP_GAP_BLE_ADV_DATA_RAW_SET_COMPLETE_EVT:
      if (this->state_ != State::CONFIGURING)
        return;
      if (param->adv_data_raw_cmpl.status != ESP_BT_STATUS_SUCCESS) {
        ESP_LOGE(TAG, "Setting advertisement data failed: %d", param->adv_data_raw_cmpl.status);
        this->state_ = State::IDLE;
        return;
      }
      if (esp_ble_gap_start_advertising(&this->adv_params_) != ESP_OK) {
        ESP_LOGE(TAG, "esp_ble_gap_start_advertising failed");
        this->state_ = State::IDLE;
      }
      break;
    case ESP_GAP_BLE_ADV_START_COMPLETE_EVT:
      if (this->state_ != State::CONFIGURING)
        return;
      if (param->adv_start_cmpl.status != ESP_BT_STATUS_SUCCESS) {
        ESP_LOGE(TAG, "Advertising start failed: %d", param->adv_start_cmpl.status);
        this->state_ = State::IDLE;
        return;
      }
      this->state_ = State::ADVERTISING;
      this->state_since_ = millis();
      this->last_swap_ = this->state_since_;
      break;
    case ESP_GAP_BLE_ADV_STOP_COMPLETE_EVT:
      if (this->state_ == State::STOPPING) {
        this->state_ = State::IDLE;
        this->last_broadcast_end_ = millis();
      }
      break;
    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// Queueing
// ---------------------------------------------------------------------------

bool MagicBand::send_raw(const std::vector<uint8_t> &payload, uint32_t duration_ms) {
  if (payload.empty() || payload.size() > MAX_PAYLOAD_LEN) {
    ESP_LOGE(TAG, "Payload must be 1-%u bytes (got %u)", (unsigned) MAX_PAYLOAD_LEN, (unsigned) payload.size());
    return false;
  }
  if (this->queue_.size() >= this->queue_size_) {
    ESP_LOGW(TAG, "Queue full, dropping oldest command");
    this->queue_.pop_front();
  }
  if (duration_ms > MAX_DURATION_MS) {
    ESP_LOGW(TAG, "Duration %ums capped at %ums", (unsigned) duration_ms, (unsigned) MAX_DURATION_MS);
    duration_ms = MAX_DURATION_MS;
  }
  this->queue_.push_back(Command{payload, duration_ms == 0 ? this->duration_ms_ : duration_ms});
  return true;
}

bool MagicBand::send_hex(const std::string &hex, uint32_t duration_ms) {
  std::vector<uint8_t> bytes;
  int hi = -1;
  for (size_t i = 0; i < hex.size(); i++) {
    char c = hex[i];
    if (c == '0' && i + 1 < hex.size() && (hex[i + 1] == 'x' || hex[i + 1] == 'X')) {
      i++;
      continue;
    }
    int v;
    if (c >= '0' && c <= '9')
      v = c - '0';
    else if (c >= 'a' && c <= 'f')
      v = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F')
      v = c - 'A' + 10;
    else
      continue;  // separators: spaces, colons, commas, dashes
    if (hi < 0) {
      hi = v;
    } else {
      bytes.push_back(static_cast<uint8_t>((hi << 4) | v));
      hi = -1;
    }
  }
  if (hi >= 0) {
    ESP_LOGE(TAG, "Odd number of hex digits in '%s'", hex.c_str());
    return false;
  }
  if (bytes.size() >= 2 && bytes[0] == 0x83 && bytes[1] == 0x01)
    bytes.erase(bytes.begin(), bytes.begin() + 2);
  return this->send_raw(bytes, duration_ms);
}

void MagicBand::stop() {
  this->queue_.clear();
  if (this->state_ == State::ADVERTISING)
    this->stop_requested_ = true;
}

void MagicBand::request_light_state(bool on, uint8_t red, uint8_t green, uint8_t blue) {
  this->light_on_ = on;
  this->light_rgb_[0] = red;
  this->light_rgb_[1] = green;
  this->light_rgb_[2] = blue;
  this->light_pending_ = true;
  this->light_changed_at_ = millis();
}

// ---------------------------------------------------------------------------
// Command builders. Byte layouts come from community reverse engineering
// (see docs/protocol.md). The byte after the 0xE9 opcode is the remaining length.
// ---------------------------------------------------------------------------

void MagicBand::send_single_color(uint8_t color, uint8_t vibration, uint8_t timing, uint8_t leds,
                                  uint32_t duration_ms) {
  this->send_raw({0xE9, 0x05, 0x00, timing, 0x0E, static_cast<uint8_t>(((leds & 0x07) << 5) | (color & 0x1F)),
                  vib_byte(vibration)},
                 duration_ms);
}

void MagicBand::send_dual_color(uint8_t inner, uint8_t outer, uint8_t vibration, uint8_t timing,
                                uint32_t duration_ms) {
  this->send_raw({0xE9, 0x06, 0x00, timing, 0x0F, col(0x80, inner), col(0x80, outer), vib_byte(vibration)},
                 duration_ms);
}

void MagicBand::send_five_color(const std::string &colors, uint8_t vibration, uint8_t timing, uint32_t duration_ms) {
  std::vector<uint8_t> codes;
  size_t start = 0;
  while (start <= colors.size() && codes.size() < 5) {
    size_t end = colors.find(',', start);
    if (end == std::string::npos)
      end = colors.size();
    std::string item = colors.substr(start, end - start);
    item.erase(0, item.find_first_not_of(' '));
    item.erase(item.find_last_not_of(' ') + 1);
    if (!item.empty())
      codes.push_back(color_from_string(item));
    start = end + 1;
  }
  if (codes.empty())
    codes.push_back(WHITE);

  std::vector<uint8_t> p{0xE9, 0x09, 0x00, timing, 0x0F};
  for (size_t i = 0; i < 5; i++)
    p.push_back(col(0xA0, codes[i % codes.size()]));
  p.push_back(vib_byte(vibration));
  this->send_raw(p, duration_ms);
}

void MagicBand::send_rgb(uint8_t red, uint8_t green, uint8_t blue, uint8_t vibration, uint8_t timing, bool flash,
                         uint32_t duration_ms) {
  this->send_raw({0xE9, 0x08, 0x00, timing, 0xD2, 0x55, rgb6(red, flash), rgb6(green, flash), rgb6(blue, flash),
                  vib_byte(vibration)},
                 duration_ms);
}

void MagicBand::send_crossfade(uint8_t c1, uint8_t c2, uint8_t vibration, uint32_t duration_ms) {
  this->send_raw({0xE1, 0x00, 0xE9, 0x11, 0x00, 0x6F, 0x0F, col(0x40, c1), col(0x40, c2), 0x58, 0xF4, 0x48, 0x82,
                  0xD1, 0x46, 0x02, 0x08, 0xD0, 0x65, 0x00, vib_byte(vibration)},
                 duration_ms);
}

void MagicBand::send_circle(uint8_t vibration, uint32_t duration_ms) {
  this->send_raw(
      {0xE9, 0x0B, 0x0B, 0x0F, 0x0F, 0x5C, 0x5D, 0x48, 0xA5, 0xD1, 0x45, 0x32, vib_byte(vibration)}, duration_ms);
}

void MagicBand::send_ping(bool fast, uint32_t duration_ms) {
  this->send_raw({0xCC, 0x03, 0x00, static_cast<uint8_t>(fast ? 0x01 : 0x00), 0x00}, duration_ms);
}

void MagicBand::wake_bands(float seconds) {
  uint32_t ms = static_cast<uint32_t>(std::max(1.0f, std::min(seconds, 60.0f)) * 1000.0f);
  this->send_raw(std::vector<uint8_t>(FAST_PING, FAST_PING + sizeof(FAST_PING)), ms);
}

void MagicBand::send_off(uint32_t duration_ms) {
  this->send_single_color(OFF, 0, TIMING_ALWAYS_ON, LEDS_ALL, duration_ms);
}

// Predefined scenes: captured park packets (payload after 83 01, without the
// E1/E2 prefix, which the prefix mode adds). Sources: emcot.world's MagicBand+
// code list and Haw8411/magic-band-plus-lights. Names are descriptive guesses.
struct Scene {
  const char *name;
  const char *label;
  uint8_t len;
  uint8_t bytes[MAX_PAYLOAD_LEN];
};

// clang-format off
static const Scene SCENES[] = {
    {"lightning", "Lightning", 14, {0xE9, 0x0C, 0x00, 0x0F, 0x0F, 0x5D, 0x46, 0x5B, 0xF0, 0x05, 0x32, 0x37, 0x48, 0x95}},
    {"orange_blink", "Orange blink", 14, {0xE9, 0x0C, 0x00, 0xEF, 0x0F, 0x4F, 0x4F, 0x5B, 0xF0, 0xFB, 0x14, 0x37, 0x48, 0x95}},
    {"color_cycle", "Color cycle", 14, {0xE9, 0x0C, 0x00, 0x0F, 0x0F, 0xB1, 0xB9, 0xB5, 0xB1, 0xA2, 0x30, 0x7B, 0x7D, 0xB0}},
    {"rainbow", "Rainbow", 14, {0xE9, 0x0C, 0x00, 0x0F, 0x0F, 0x5D, 0x46, 0x5B, 0xF0, 0x05, 0x32, 0x37, 0x48, 0xB0}},
    {"circle", "Circle", 13, {0xE9, 0x0B, 0x0B, 0x0F, 0x0F, 0x5C, 0x5D, 0x48, 0xA5, 0xD1, 0x45, 0x32, 0xB0}},
    {"alternating", "Alternating", 18, {0xE9, 0x10, 0x00, 0x13, 0x48, 0x97, 0xD0, 0x0E, 0xA0, 0xD1, 0x46, 0x06, 0x0F, 0x30, 0xD0, 0x4E, 0x07, 0xB0}},
    {"crossfade", "Crossfade", 19, {0xE9, 0x11, 0x00, 0x6F, 0x0F, 0x56, 0x48, 0x58, 0xF4, 0x48, 0x82, 0xD1, 0x46, 0x02, 0x08, 0xD0, 0x65, 0x00, 0xB0}},
    {"crossfade_2", "Crossfade 2", 19, {0xE9, 0x11, 0x00, 0x4F, 0x0F, 0x44, 0x4F, 0x58, 0xF4, 0x48, 0x82, 0xD1, 0x46, 0x06, 0x07, 0xD0, 0x65, 0x43, 0xB0}},
    {"crossfade_3", "Crossfade 3", 19, {0xE9, 0x11, 0x00, 0x0F, 0x0F, 0x48, 0x59, 0x58, 0xF4, 0x48, 0x82, 0xD1, 0x46, 0x02, 0x0D, 0xD0, 0x65, 0x05, 0xB0}},
    {"crossfade_4", "Crossfade 4", 19, {0xE9, 0x11, 0x00, 0x4F, 0x0F, 0x4F, 0x55, 0x58, 0xF4, 0x48, 0x82, 0xD1, 0x46, 0x02, 0x2A, 0xD0, 0x65, 0x01, 0xB0}},
    {"crossfade_5", "Crossfade 5", 19, {0xE9, 0x11, 0x00, 0x01, 0x0F, 0x5A, 0x47, 0x5B, 0xF0, 0x31, 0x34, 0x37, 0x48, 0x94, 0xD1, 0x3D, 0x05, 0x07, 0xB0}},
    {"crossfade_6", "Crossfade 6", 19, {0xE9, 0x11, 0x00, 0x07, 0x0F, 0x55, 0x5D, 0x58, 0xF4, 0x48, 0x82, 0xD1, 0x46, 0x05, 0x08, 0xD0, 0x65, 0x00, 0xB0}},
    {"crossfade_7", "Crossfade 7", 19, {0xE9, 0x11, 0x00, 0x44, 0x0F, 0x51, 0x42, 0x58, 0xF4, 0x48, 0x82, 0xD1, 0x46, 0x05, 0x0F, 0xD0, 0x65, 0x00, 0xB0}},
    {"spin_buzz", "Spin & buzz", 20, {0xE9, 0x12, 0x00, 0x01, 0x0F, 0xBC, 0xBD, 0xBD, 0xBD, 0xBD, 0x30, 0xD0, 0x37, 0xF4, 0xD2, 0x46, 0x00, 0x00, 0xFC, 0xBB}},
    {"spin_buzz_2", "Spin & buzz 2", 20, {0xE9, 0x12, 0x00, 0x01, 0x29, 0x04, 0x02, 0x02, 0x11, 0x11, 0x48, 0x96, 0xD0, 0x0E, 0xFF, 0xD1, 0x46, 0x07, 0x07, 0xB0}},
    {"spin_buzz_3", "Spin & buzz 3", 20, {0xE9, 0x12, 0x00, 0x03, 0x0F, 0xA2, 0xA2, 0xA4, 0xA4, 0xA2, 0x30, 0xD0, 0x37, 0xF4, 0xD2, 0x46, 0x00, 0x64, 0xFC, 0xB0}},
    {"show_0e_1", "Show 0E 1", 16, {0xE9, 0x0E, 0x00, 0x01, 0x0F, 0xBD, 0xA0, 0xA0, 0xBD, 0xA0, 0x59, 0x07, 0x00, 0x48, 0xAE, 0xB5}},
    {"show_0e_2", "Show 0E 2", 16, {0xE9, 0x0E, 0x00, 0x02, 0x0F, 0xBC, 0xA0, 0xBC, 0xA0, 0xBC, 0x59, 0x17, 0xFB, 0x48, 0xAE, 0xBB}},
    {"show_0e_3", "Show 0E 3", 16, {0xE9, 0x0E, 0x00, 0x11, 0x0F, 0xBC, 0xA7, 0xB9, 0xA7, 0xB9, 0x59, 0x19, 0x02, 0x48, 0xAE, 0xB0}},
    {"show_0e_4", "Show 0E 4", 16, {0xE9, 0x0E, 0x00, 0x15, 0x0F, 0xBB, 0xBB, 0xBB, 0xBB, 0xBB, 0x59, 0x19, 0x02, 0x48, 0xAE, 0xB0}},
    {"show_0e_5", "Show 0E 5", 16, {0xE9, 0x0E, 0x00, 0x83, 0x0F, 0xB5, 0xB9, 0xB2, 0xAD, 0xB6, 0x59, 0x19, 0x0B, 0x48, 0xAE, 0xB0}},
    {"show_0f_1", "Show 0F 1", 17, {0xE9, 0x0F, 0x00, 0x11, 0x0F, 0x4F, 0x42, 0x58, 0x07, 0x48, 0x8D, 0xD2, 0x46, 0x2A, 0x07, 0x17, 0xB8}},
    {"show_0f_2", "Show 0F 2", 17, {0xE9, 0x0F, 0x00, 0x2A, 0x0F, 0x46, 0x43, 0x58, 0x12, 0x48, 0x8D, 0xD2, 0x46, 0x02, 0x12, 0x00, 0xB0}},
    {"show_e913", "Show 13 1", 21, {0xE9, 0x13, 0x00, 0xB6, 0x0F, 0x40, 0x44, 0x58, 0xF4, 0x48, 0x82, 0xD0, 0x65, 0x19, 0xD1, 0x46, 0x06, 0x0A, 0x30, 0x7B, 0xFF}},
    {"show_13_2", "Show 13 2", 21, {0xE9, 0x13, 0x00, 0x02, 0xD0, 0x37, 0xF0, 0xD2, 0x3D, 0x05, 0x05, 0x00, 0x0E, 0xFA, 0x89, 0x83, 0x51, 0x0E, 0xE7, 0xA0, 0xB0}},
    {"show_13_3", "Show 13 3", 21, {0xE9, 0x13, 0x00, 0x65, 0x0F, 0xBD, 0xB5, 0xBC, 0xB5, 0xBC, 0x7A, 0xEC, 0x5C, 0x0A, 0x29, 0x15, 0x29, 0x15, 0x48, 0xAB, 0xB0}},
    {"show_14_1", "Show 14 1", 22, {0xE9, 0x14, 0x00, 0x0C, 0xD0, 0x37, 0xF0, 0xD2, 0x3D, 0x05, 0x0C, 0x0C, 0x0E, 0xEC, 0x89, 0x83, 0x51, 0x0E, 0xEE, 0x0C, 0x3D, 0xB0}},
    {"show_14_2", "Show 14 2", 22, {0xE9, 0x14, 0x00, 0x2C, 0xD0, 0x37, 0xF0, 0xD2, 0x3D, 0x02, 0x12, 0x00, 0x0E, 0xEA, 0x89, 0x83, 0x51, 0x0E, 0xE3, 0x0C, 0x1E, 0xB0}},
    {"show_14_3", "Show 14 3", 22, {0xE9, 0x14, 0x00, 0x42, 0x0F, 0x55, 0x5B, 0x58, 0xF4, 0x48, 0x82, 0xD0, 0x65, 0x1B, 0xD1, 0x46, 0x2A, 0x02, 0x30, 0x7B, 0x5D, 0xB0}},
    {"show_07_1", "Show 07 1", 9, {0xE9, 0x07, 0x00, 0x22, 0x0F, 0x43, 0x43, 0x41, 0xB0}},
    {"show_07_2", "Show 07 2", 9, {0xE9, 0x07, 0x00, 0x22, 0x0F, 0x44, 0x44, 0x41, 0xB0}},
};
// clang-format on
static constexpr size_t SCENE_COUNT = sizeof(SCENES) / sizeof(SCENES[0]);

size_t MagicBand::scene_count() { return SCENE_COUNT; }
const char *MagicBand::scene_name(size_t i) { return i < SCENE_COUNT ? SCENES[i].name : ""; }
const char *MagicBand::scene_label(size_t i) { return i < SCENE_COUNT ? SCENES[i].label : ""; }

// "Spin & buzz 2" / "spin-buzz-2" / "Colour cycle" -> "spin_buzz_2" / "color_cycle".
static std::string scene_key(const std::string &input) {
  std::string s;
  for (char c : input) {
    if (std::isalnum(static_cast<unsigned char>(c))) {
      s.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    } else if (!s.empty() && s.back() != '_') {
      s.push_back('_');
    }
  }
  while (!s.empty() && s.back() == '_')
    s.pop_back();
  size_t at = s.find("colour");
  if (at != std::string::npos)
    s.replace(at, 6, "color");
  return s;
}

bool MagicBand::send_animation(const std::string &input, uint32_t duration_ms) {
  std::string key = scene_key(input);
  for (const auto &a : SCENES) {
    if (key == a.name || key == scene_key(a.label))
      return this->send_raw(std::vector<uint8_t>(a.bytes, a.bytes + a.len), duration_ms);
  }
  ESP_LOGW(TAG, "Unknown scene '%s'", input.c_str());
  return false;
}

// ---------------------------------------------------------------------------
// JSON commands (from the "Command" text entity)
// ---------------------------------------------------------------------------

bool MagicBand::run_command_json(const std::string &input) {
  // Home Assistant turns template output that looks like JSON into a dict, so
  // callers prefix it (e.g. "mb{...}"). Everything before the first '{' is ignored.
  size_t brace = input.find('{');
  if (brace == std::string::npos) {
    ESP_LOGW(TAG, "Command has no JSON object: %s", input.c_str());
    return false;
  }
  const std::string json = input.substr(brace);
  JsonDocument doc = json::parse_json(json);
  JsonObject o = doc.as<JsonObject>();
  if (o.isNull()) {
    ESP_LOGW(TAG, "Command is not a JSON object: %s", json.c_str());
    return false;
  }
  std::string effect = o["effect"] | "color";
  uint8_t vib = static_cast<uint8_t>(o["vibration"] | 0);
  float on_seconds = o["on_seconds"] | 0.0f;
  uint8_t fade = static_cast<uint8_t>(o["fade_seconds"] | 0);
  bool always_on = o["always_on"] | false;
  uint32_t duration = o["duration_ms"] | 0u;
  std::string c1 = o["color"] | (o["color1"] | "white");
  std::string c2 = o["color2"] | "pink";

  ESP_LOGD(TAG, "Command: %s", json.c_str());
  if (effect == "color") {
    this->send_single_color(color_from_string(c1), vib,
                            timing_or(TIMING_SINGLE_DEFAULT, on_seconds, fade, always_on),
                            leds_from_string(o["leds"] | "all"), duration);
  } else if (effect == "rgb") {
    uint8_t r = o["red"] | 0, g = o["green"] | 0, b = o["blue"] | 0;
    JsonArrayConst arr = o["rgb"].as<JsonArrayConst>();
    if (!arr.isNull() && arr.size() >= 3) {
      r = arr[0] | 0;
      g = arr[1] | 0;
      b = arr[2] | 0;
    }
    this->send_rgb(r, g, b, vib, timing_or(TIMING_SINGLE_DEFAULT, on_seconds, fade, always_on),
                   o["flash"] | false, duration);
  } else if (effect == "dual_color") {
    std::string inner = o["inner"] | c1.c_str();
    std::string outer = o["outer"] | c2.c_str();
    this->send_dual_color(color_from_string(inner), color_from_string(outer), vib,
                          timing_or(TIMING_DUAL_DEFAULT, on_seconds, fade, always_on), duration);
  } else if (effect == "five_color") {
    this->send_five_color(o["colors"] | "red, orange, yellow, green, blue", vib,
                          timing_or(TIMING_FIVE_DEFAULT, on_seconds, fade, always_on), duration);
  } else if (effect == "crossfade") {
    this->send_crossfade(color_from_string(c1), color_from_string(c2), vib, duration);
  } else if (effect == "circle") {
    this->send_circle(vib, duration);
  } else if (effect == "animation" || effect == "scene") {
    return this->send_animation(o["name"] | (o["scene"] | "color_cycle"), duration);
  } else if (effect == "wake") {
    this->wake_bands(o["seconds"] | 15.0f);
  } else if (effect == "buzz") {
    this->send_single_color(OFF, vib, TIMING_SINGLE_DEFAULT, LEDS_ALL, duration);
  } else if (effect == "ping") {
    this->send_ping(o["fast"] | false, duration);
  } else if (effect == "off") {
    this->send_off(duration);
  } else if (effect == "raw") {
    return this->send_hex(o["hex"] | "", duration);
  } else if (effect == "stop") {
    this->stop();
  } else {
    ESP_LOGW(TAG, "Unknown effect '%s'", effect.c_str());
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

uint8_t MagicBand::timing(float on_seconds, uint8_t fade_seconds, bool always_on) {
  uint8_t fade = static_cast<uint8_t>(std::min<int>(std::max<int>(fade_seconds, 0), 3)) << 4;
  if (always_on)
    return 0x80 | fade;
  // Two scalers: on = 1.5*v + 6.5 (6.5-29s) or on = 3.1*v + 5.5 (5.5-52s). Pick the closest.
  uint8_t best = 0;
  float best_err = 1e9f;
  for (uint8_t scaler = 0; scaler < 2; scaler++) {
    for (uint8_t v = 0; v < 16; v++) {
      float t = scaler ? 3.1f * v + 5.5f : 1.5f * v + 6.5f;
      float err = std::fabs(t - on_seconds);
      if (err < best_err) {
        best_err = err;
        best = static_cast<uint8_t>((scaler << 6) | v);
      }
    }
  }
  return best | fade;
}

uint8_t MagicBand::timing_or(uint8_t fallback, float on_seconds, uint8_t fade_seconds, bool always_on) {
  if (always_on || on_seconds > 0)
    return timing(on_seconds, fade_seconds, always_on);
  return fallback;
}

uint8_t MagicBand::leds_from_string(const std::string &input) {
  std::string s;
  for (char c : input) {
    if (c == ' ' || c == '-')
      c = '_';
    s.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
  }
  if (s == "top_left")
    return LEDS_TOP_LEFT;
  if (s == "top_right")
    return LEDS_TOP_RIGHT;
  if (s == "bottom_left")
    return LEDS_BOTTOM_LEFT;
  if (s == "bottom_right")
    return LEDS_BOTTOM_RIGHT;
  return LEDS_ALL;
}

uint8_t MagicBand::color_from_string(const std::string &input) {
  std::string s;
  for (char c : input) {
    if (c == ' ' || c == '-')
      c = '_';
    s.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
  }
  if (!s.empty() && std::isdigit(static_cast<unsigned char>(s[0])))
    return static_cast<uint8_t>(strtol(s.c_str(), nullptr, 0) & 0x1F);

  struct Entry {
    const char *name;
    uint8_t code;
  };
  static const Entry TABLE[] = {
      {"cyan", CYAN},
      {"purple", PURPLE},
      {"blue", BLUE},
      {"midnight_blue", MIDNIGHT_BLUE},
      {"bright_purple", BRIGHT_PURPLE},
      {"lavender", LAVENDER},
      {"pink", PINK},
      {"yellow_orange", YELLOW_ORANGE},
      {"yellow", YELLOW_ORANGE},
      {"off_yellow", OFF_YELLOW},
      {"lime", LIME},
      {"orange", ORANGE},
      {"red_orange", RED_ORANGE},
      {"red", RED},
      {"green", GREEN},
      {"lime_green", LIME_GREEN},
      {"white", WHITE},
      {"off", OFF},
      {"unique", UNIQUE},
      {"random", RANDOM},
  };
  for (const auto &e : TABLE) {
    if (s == e.name)
      return e.code;
  }
  ESP_LOGW(TAG, "Unknown colour '%s', using white", input.c_str());
  return WHITE;
}

}  // namespace esphome::magicband

#endif  // USE_ESP32
