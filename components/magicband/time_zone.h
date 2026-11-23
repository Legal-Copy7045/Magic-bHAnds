#pragma once
// The devices' "Time zone" setting. ESPHome builds its time zone in at compile
// time and has no runtime parser, so the zones the setting offers are listed
// here, already parsed (the same values ESPHome generates from a POSIX string).
// set_time_zone() applies one to every clock on the device (SNTP and Home
// Assistant share ESPHome's global time zone).

#include <cstring>
#include <string>

#include "esphome/core/defines.h"
#ifdef USE_TIME_TIMEZONE
#include "esphome/components/time/posix_tz.h"
#endif

namespace esphome {
namespace magicband {

// The setting's options, in order; keep in step with the "Time zone" select.
static const char *const TIME_ZONES[] = {
    "Eastern (New York)",   "Central (Chicago)", "Mountain (Denver)", "Arizona (Phoenix)",
    "Pacific (Los Angeles)", "Alaska (Anchorage)", "Hawaii (Honolulu)", "UK (London)",
    "Central Europe (Paris)", "UTC",
};

#ifdef USE_TIME_TIMEZONE
// Daylight-saving rules: US (2nd Sun Mar 02:00 to 1st Sun Nov 02:00), UK (last Sun
// Mar 01:00 to last Sun Oct 02:00) and central Europe (last Sun Mar 02:00 to last
// Sun Oct 03:00), all in local time as POSIX writes them.
enum class DstRule : uint8_t { NONE, US, UK, CET };

inline time::DSTRule mwd(uint8_t month, uint8_t week, int32_t at) {
  time::DSTRule r{};
  r.type = time::DSTRuleType::MONTH_WEEK_DAY;
  r.month = month;
  r.week = week;
  r.day_of_week = 0;  // Sunday
  r.time_seconds = at;
  return r;
}

// Applies the named zone. Returns false for a name it doesn't know (nothing changes).
inline bool set_time_zone(const std::string &name) {
  struct Zone {
    const char *name;
    int32_t std_hours_west;  // POSIX sign: positive = west of UTC
    DstRule dst;
  };
  static const Zone ZONES[] = {
      {"Eastern (New York)", 5, DstRule::US},  {"Central (Chicago)", 6, DstRule::US},
      {"Mountain (Denver)", 7, DstRule::US},   {"Arizona (Phoenix)", 7, DstRule::NONE},
      {"Pacific (Los Angeles)", 8, DstRule::US}, {"Alaska (Anchorage)", 9, DstRule::US},
      {"Hawaii (Honolulu)", 10, DstRule::NONE}, {"UK (London)", 0, DstRule::UK},
      {"Central Europe (Paris)", -1, DstRule::CET}, {"UTC", 0, DstRule::NONE},
  };
  for (const auto &z : ZONES) {
    if (name != z.name) continue;
    time::ParsedTimezone tz{};
    tz.std_offset_seconds = z.std_hours_west * 3600;
    tz.dst_offset_seconds = 0;  // as ESPHome parses a zone without daylight saving
    if (z.dst != DstRule::NONE) {
      tz.dst_offset_seconds = tz.std_offset_seconds - 3600;  // an hour ahead in summer
      if (z.dst == DstRule::US) {
        tz.dst_start = mwd(3, 2, 7200);
        tz.dst_end = mwd(11, 1, 7200);
      } else if (z.dst == DstRule::UK) {
        tz.dst_start = mwd(3, 5, 3600);
        tz.dst_end = mwd(10, 5, 7200);
      } else {
        tz.dst_start = mwd(3, 5, 7200);
        tz.dst_end = mwd(10, 5, 10800);
      }
    }
    time::set_global_tz(tz);
    return true;
  }
  return false;
}
#else
inline bool set_time_zone(const std::string &) { return false; }
#endif

}  // namespace magicband
}  // namespace esphome
