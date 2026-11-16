#include "magicband.h"

#ifdef USE_ESP32

#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>

namespace esphome::magicband {

static const char *const TAG = "magicband";

// If the BLE stack never confirms a config/start/stop, give up after this long.
static constexpr uint32_t GAP_TIMEOUT_MS = 1000;

static inline uint8_t vib_byte(uint8_t v) { return 0xB0 | (std::min<uint8_t>(v, 15) & 0x0F); }
static inline uint8_t col(uint8_t mode, uint8_t c) { return mode | (c & 0x1F); }

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
  ESP_LOGCONFIG(TAG, "  TX power: %ddBm", (this->tx_power_ * 3) - 12);
#endif
}

void MagicBand::loop() {
  const uint32_t now = millis();
  switch (this->state_) {
    case State::IDLE:
      if (!this->queue_.empty() && esp32_ble::global_ble != nullptr && esp32_ble::global_ble->is_active())
        this->start_next_();
      break;
    case State::CONFIGURING:
      if (now - this->state_since_ > GAP_TIMEOUT_MS) {
        ESP_LOGW(TAG, "Timed out configuring advertisement data");
        this->state_ = State::IDLE;
      }
      break;
    case State::ADVERTISING:
      if (this->stop_requested_ || now - this->state_since_ >= this->current_.duration_ms)
        this->request_stop_();
      break;
    case State::STOPPING:
      if (now - this->state_since_ > GAP_TIMEOUT_MS) {
        ESP_LOGW(TAG, "Timed out stopping advertising");
        this->state_ = State::IDLE;
      }
      break;
  }
}

void MagicBand::start_next_() {
  this->current_ = std::move(this->queue_.front());
  this->queue_.pop_front();
  this->stop_requested_ = false;

  // Flags AD + manufacturer-specific AD (0xFF) with Disney company ID.
  uint8_t adv[31];
  size_t n = 0;
  adv[n++] = 0x02;
  adv[n++] = 0x01;
  adv[n++] = 0x06;
  adv[n++] = static_cast<uint8_t>(1 + 2 + this->current_.payload.size());
  adv[n++] = 0xFF;
  adv[n++] = DISNEY_COMPANY_ID & 0xFF;
  adv[n++] = DISNEY_COMPANY_ID >> 8;
  memcpy(adv + n, this->current_.payload.data(), this->current_.payload.size());
  n += this->current_.payload.size();

  char hex[MAX_PAYLOAD_LEN * 3 + 1];
  format_hex_pretty_to(hex, this->current_.payload.data(), this->current_.payload.size(), ' ');
  ESP_LOGD(TAG, "Broadcasting 83 01 %s for %ums", hex, (unsigned) this->current_.duration_ms);

#ifndef CONFIG_BT_CONTROLLER_DISABLED
  esp_err_t err = esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV, this->tx_power_);
  if (err != ESP_OK)
    ESP_LOGW(TAG, "esp_ble_tx_power_set failed: %s", esp_err_to_name(err));
#endif

  esp_err_t cfg = esp_ble_gap_config_adv_data_raw(adv, n);
  if (cfg != ESP_OK) {
    ESP_LOGE(TAG, "esp_ble_gap_config_adv_data_raw failed: %s", esp_err_to_name(cfg));
    return;
  }
  this->state_ = State::CONFIGURING;
  this->state_since_ = millis();
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
      break;
    case ESP_GAP_BLE_ADV_STOP_COMPLETE_EVT:
      if (this->state_ == State::STOPPING)
        this->state_ = State::IDLE;
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

// ---------------------------------------------------------------------------
// Command builders. Byte layouts come from community reverse engineering
// (see docs/protocol.md). Byte after the 0xE9 opcode is the remaining length.
// ---------------------------------------------------------------------------

void MagicBand::send_single_color(uint8_t color, uint8_t vibration, uint8_t timing, uint32_t duration_ms) {
  this->send_raw({0xE9, 0x05, 0x00, timing, 0x0E, col(0xE0, color), vib_byte(vibration)}, duration_ms);
}

void MagicBand::send_dual_color(uint8_t c1, uint8_t c2, uint8_t vibration, uint8_t timing, uint32_t duration_ms) {
  this->send_raw({0xE9, 0x06, 0x00, timing, 0x0F, col(0x80, c1), col(0x80, c2), vib_byte(vibration)}, duration_ms);
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

void MagicBand::send_crossfade(uint8_t c1, uint8_t c2, uint8_t vibration, uint32_t duration_ms) {
  this->send_raw({0xE1, 0x00, 0xE9, 0x11, 0x00, 0x6F, 0x0F, col(0x40, c1), col(0x40, c2), 0x58, 0xF4, 0x48, 0x82,
                  0xD1, 0x46, 0x02, 0x08, 0xD0, 0x65, 0x00, vib_byte(vibration)},
                 duration_ms);
}

void MagicBand::send_circle(uint8_t vibration, uint32_t duration_ms) {
  this->send_raw(
      {0xE9, 0x0B, 0x0B, 0x0F, 0x0F, 0x5C, 0x5D, 0x48, 0xA5, 0xD1, 0x45, 0x32, vib_byte(vibration)}, duration_ms);
}

void MagicBand::send_ping(uint32_t duration_ms) { this->send_raw({0xCC, 0x03, 0x00, 0x00, 0x00}, duration_ms); }

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
