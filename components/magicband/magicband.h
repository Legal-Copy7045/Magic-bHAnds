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

/// Palette indexes (5-bit). Community-sourced; see docs/protocol.md.
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
  UNIQUE = 0x1E,
  RANDOM = 0x1F,
};

/// LED mask for single-colour commands (top 3 bits of the colour byte).
enum Leds : uint8_t {
  LEDS_ALL = 0b111,
  LEDS_TOP_RIGHT = 0b001,
  LEDS_BOTTOM_RIGHT = 0b010,
  LEDS_BOTTOM_LEFT = 0b011,
  LEDS_TOP_LEFT = 0b100,
};

/// Timing byte values captured from park shows, used as defaults.
static constexpr uint8_t TIMING_SINGLE_DEFAULT = 0x2E;  // ~27.5s on, 2s fade
static constexpr uint8_t TIMING_DUAL_DEFAULT = 0x22;    // ~9.5s on, 2s fade
static constexpr uint8_t TIMING_FIVE_DEFAULT = 0x2E;
static constexpr uint8_t TIMING_ALWAYS_ON = 0x80;

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

  // ---- Command builders. `duration_ms` is the broadcast length (0 = configured default). ----

  /// Whole band (or some LEDs) one palette colour.
  void send_single_color(uint8_t color, uint8_t vibration = 0, uint8_t timing = TIMING_SINGLE_DEFAULT,
                         uint8_t leds = LEDS_ALL, uint32_t duration_ms = 0);
  /// Two palette colours: centre (inner) and outer ring.
  void send_dual_color(uint8_t inner, uint8_t outer, uint8_t vibration = 0, uint8_t timing = TIMING_DUAL_DEFAULT,
                       uint32_t duration_ms = 0);
  /// Five palette colours: "centre, top right, bottom right, bottom left, top left". Fewer than five repeat.
  void send_five_color(const std::string &colors, uint8_t vibration = 0, uint8_t timing = TIMING_FIVE_DEFAULT,
                       uint32_t duration_ms = 0);
  /// Any colour (0-255 per channel, sent as 6-bit). `flash` makes the band blink.
  void send_rgb(uint8_t red, uint8_t green, uint8_t blue, uint8_t vibration = 0,
                uint8_t timing = TIMING_SINGLE_DEFAULT, bool flash = false, uint32_t duration_ms = 0);
  /// Two colours crossfading.
  void send_crossfade(uint8_t color1, uint8_t color2, uint8_t vibration = 0, uint32_t duration_ms = 0);
  /// Spinning circle animation.
  void send_circle(uint8_t vibration = 0, uint32_t duration_ms = 0);
  /// Captured park animation by name (see animation_names()). Returns false if unknown.
  bool send_animation(const std::string &name, uint32_t duration_ms = 0);
  /// Park "ping"; `fast` uses the variant believed to put bands in a quicker-response mode.
  void send_ping(bool fast = false, uint32_t duration_ms = 0);
  /// Turn the band's lights off (clears an always-on colour).
  void send_off(uint32_t duration_ms = 0);

  /// Any payload as hex, e.g. "E9 05 00 2E 0E E5 B3". A leading "83 01" is accepted and stripped.
  bool send_hex(const std::string &hex, uint32_t duration_ms = 0);
  /// Any payload bytes (excluding the 0x83 0x01 company ID).
  bool send_raw(const std::vector<uint8_t> &payload, uint32_t duration_ms = 0);

  /// Stop broadcasting now and drop anything queued.
  void stop();

  /// Run a command given as JSON, e.g. {"effect":"color","color":"red","vibration":3}.
  /// This is what the "Command" text entity feeds, so HA can target many bridges at once.
  /// See docs/commands.md for the fields. Returns false if invalid.
  bool run_command_json(const std::string &json);

  /// Light entity support: debounced so colour-wheel drags don't flood the queue.
  void request_light_state(bool on, uint8_t red, uint8_t green, uint8_t blue);

  // ---- Helpers ----

  /// Build a timing byte. `on_seconds` ~5.5-52s (rounded to what the band supports), `fade_seconds` 0-3.
  static uint8_t timing(float on_seconds, uint8_t fade_seconds = 0, bool always_on = false);
  /// Timing for the simple actions: on_seconds <= 0 keeps `fallback`, always_on wins over on_seconds.
  static uint8_t timing_or(uint8_t fallback, float on_seconds, uint8_t fade_seconds, bool always_on);
  /// Colour name ("red", "lime_green", ...) or number ("21", "0x15") -> palette index. Unknown -> white.
  static uint8_t color_from_string(const std::string &name);
  /// "all", "top_left", "top_right", "bottom_left", "bottom_right" -> LED mask. Unknown -> all.
  static uint8_t leds_from_string(const std::string &name);
  /// Names accepted by send_animation().
  static const char *const *animation_names(size_t &count);

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

  // Light entity debounce
  bool light_pending_{false};
  bool light_on_{false};
  bool light_was_on_{false};
  uint8_t light_rgb_[3]{0, 0, 0};
  uint32_t light_changed_at_{0};

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
