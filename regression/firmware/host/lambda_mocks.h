#pragma once
// Stand-ins for the ESPHome objects the reader's lambdas touch (numbers,
// selects, switches, scripts, the speaker, the clock), so lambdas extracted
// from esphome/magicband-reader.yaml (lambdas.py) compile and run on the host.
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <string>

#include "esphome/components/time/posix_tz.h"

namespace mock {

inline uint32_t now_ms = 0;
inline uint32_t millis() { return now_ms; }

__attribute__((format(printf, 3, 4))) inline void log(const char *lvl, const char *tag, const char *f, ...) {
  char buf[512];
  va_list ap;
  va_start(ap, f);
  vsnprintf(buf, sizeof buf, f, ap);
  va_end(ap);
  printf("LOG|%s|%s|%s\n", lvl, tag, buf);
}

// ESPHome 2026.10's select current_option() returns a StringRef.
struct Str {
  std::string s;
  bool operator==(const char *o) const { return s == o; }
  bool operator!=(const char *o) const { return s != o; }
  bool operator==(const std::string &o) const { return s == o; }
  operator std::string() const { return s; }
  std::string str() const { return s; }
  const char *c_str() const { return s.c_str(); }
};
struct Number {
  float state = NAN;
};
struct Select {
  std::string opt;
  Str current_option() const { return Str{opt}; }
};
struct Switch {
  bool state = false;
};
struct BinarySensor {
  bool state = false;
  int published = 0;
  void publish_state(bool s) { state = s, published++; }
};
struct TextSensor {
  std::string state;
  void publish_state(const std::string &s) { state = s; }
};
struct Script {
  bool running = false;
  int executed = 0;
  bool is_running() const { return running; }
  void execute() { executed++; }
};
struct Speaker;
struct SpeakerCall {
  Speaker *sp;
  float vol = NAN;
  SpeakerCall &set_volume(float v) {
    vol = v;
    return *this;
  }
  void perform();
};
struct Speaker {
  float volume = 0.7f;
  int calls = 0;
  SpeakerCall make_call() { return SpeakerCall{this}; }
};
inline void SpeakerCall::perform() {
  sp->calls++;
  if (!std::isnan(vol)) sp->volume = vol;
}

}  // namespace mock

namespace esphome {
// ESPTime: only what the lambdas use. Local time comes from ESPHome's own
// posix_tz.cpp and the global zone set_time_zone() installs.
struct ESPTime {
  int hour = 0, minute = 0, second = 0;
  bool valid = false;
  bool is_valid() const { return valid; }
  static ESPTime from_epoch_local(time_t e) {
    struct tm t {};
    time::epoch_to_local_tm(e, time::get_global_tz(), &t);
    ESPTime r;
    r.hour = t.tm_hour, r.minute = t.tm_min, r.second = t.tm_sec, r.valid = true;
    return r;
  }
};
}  // namespace esphome

namespace mock {
struct Clock {
  esphome::ESPTime t;
  esphome::ESPTime now() const { return t; }
};
}  // namespace mock

#define ESP_LOGE(tag, ...) ::mock::log("E", tag, __VA_ARGS__)
#define ESP_LOGW(tag, ...) ::mock::log("W", tag, __VA_ARGS__)
#define ESP_LOGI(tag, ...) ::mock::log("I", tag, __VA_ARGS__)
#define ESP_LOGD(tag, ...) ::mock::log("D", tag, __VA_ARGS__)
