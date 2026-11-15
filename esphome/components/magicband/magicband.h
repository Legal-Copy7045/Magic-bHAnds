#pragma once

#include "esphome/components/esp32_ble/ble.h"
#include "esphome/core/component.h"

#ifdef USE_ESP32

#ifndef CONFIG_BT_CONTROLLER_DISABLED
#include <esp_bt.h>
#endif
#include <esp_gap_ble_api.h>

#include <deque>
#include <string>
#include <vector>

namespace esphome::magicband {

/// Disney's Bluetooth SIG company identifier, little-endian on air.
static constexpr uint16_t DISNEY_COMPANY_ID = 0x0183;

/// Max payload after the company ID: 31 (legacy adv) - 3 (flags AD) - 2 (mfg AD header) - 2 (company ID).
static constexpr size_t MAX_PAYLOAD_LEN = 24;

/// Known palette indexes (5-bit). Community-sourced; see docs/protocol.md.
enum Color : uint8_t {
  CYAN = 0x00,
  PURPLE = 0x01,
  BLUE = 0x02,
  MIDNIGHT_BLUE = 0x03,
  BRIGHT_PURPLE = 0x05,
  LAVENDER = 0x06,
  PINK = 0x08,
  YELLOW_ORANGE = 0x0F,
  OFF_YELLOW = 0x10,
  LIME = 0x12,
  ORANGE = 0x13,
  RED_ORANGE = 0x14,
  RED = 0x15,
  GREEN = 0x19,
  LIME_GREEN = 0x1A,
  WHITE = 0x1B,
  OFF = 0x1D,
  RANDOM = 0x1F,
};

class MagicBand : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_BLUETOOTH; }

  void set_duration(uint32_t ms) { this->duration_ms_ = ms; }
  void set_min_interval(uint32_t ms) { this->min_interval_ms_ = ms; }
  void set_max_interval(uint32_t ms) { this->max_interval_ms_ = ms; }
  void set_queue_size(uint8_t n) { this->queue_size_ = n; }
#ifndef CONFIG_BT_CONTROLLER_DISABLED
  void set_tx_power(esp_power_level_t p) { this->tx_power_ = p; }
#else
  void set_tx_power(int) {}
#endif

  void gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param);

  // ---- High level commands (duration_ms = 0 uses the configured default) ----

  /// Whole band one colour. `timing` is the community-observed default 0x2E.
  void send_single_color(uint8_t color, uint8_t vibration = 0, uint8_t timing = 0x2E, uint32_t duration_ms = 0);
  /// Two colours split across the band.
  void send_dual_color(uint8_t color1, uint8_t color2, uint8_t vibration = 0, uint8_t timing = 0x22,
                       uint32_t duration_ms = 0);
  /// Five colours around the band, e.g. "red, orange, yellow, green, blue". Fewer than five repeat.
  void send_five_color(const std::string &colors, uint8_t vibration = 0, uint8_t timing = 0x2E,
                       uint32_t duration_ms = 0);
  /// Two colours crossfading.
  void send_crossfade(uint8_t color1, uint8_t color2, uint8_t vibration = 0, uint32_t duration_ms = 0);
  /// Spinning circle animation.
  void send_circle(uint8_t vibration = 0, uint32_t duration_ms = 0);
  /// "Ping" packet seen from park beacons; may help wake bands.
  void send_ping(uint32_t duration_ms = 0);

  /// Any payload as hex, e.g. "E9 05 00 2E 0E E5 B3". A leading "83 01" is accepted and stripped.
  bool send_hex(const std::string &hex, uint32_t duration_ms = 0);
  /// Any payload bytes (excluding the 0x83 0x01 company ID).
  bool send_raw(const std::vector<uint8_t> &payload, uint32_t duration_ms = 0);

  /// Stop broadcasting now and drop anything queued.
  void stop();

  /// Resolve a colour name ("red", "lime_green", ...) or a number ("21", "0x15") to a palette index.
  /// Returns WHITE for anything unrecognised.
  static uint8_t color_from_string(const std::string &name);

  bool is_broadcasting() const { return this->state_ != State::IDLE; }

 protected:
  enum class State : uint8_t { IDLE, CONFIGURING, ADVERTISING, STOPPING };

  struct Command {
    std::vector<uint8_t> payload;
    uint32_t duration_ms;
  };

  void start_next_();
  void request_stop_();

  std::deque<Command> queue_;
  Command current_;
  State state_{State::IDLE};
  uint32_t state_since_{0};
  bool stop_requested_{false};

  uint32_t duration_ms_{2000};
  uint32_t min_interval_ms_{20};
  uint32_t max_interval_ms_{40};
  uint8_t queue_size_{8};
#ifndef CONFIG_BT_CONTROLLER_DISABLED
  esp_power_level_t tx_power_{ESP_PWR_LVL_P9};
#endif
  esp_ble_adv_params_t adv_params_{};
};

}  // namespace esphome::magicband

#endif  // USE_ESP32
