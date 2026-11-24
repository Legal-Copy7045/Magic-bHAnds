// set_time_zone() (components/magicband/time_zone.h), against ESPHome's own
// posix_tz.cpp compiled for the host. Prints machine-readable lines for
// host_tests.py, which compares them with aioesphomeapi's parse_posix_tz and
// Python's zoneinfo:
//   ZONE|<name>|<ok>|std|dst|start type,month,week,dow,day,time|end ...
//   LOCAL|<name>|<epoch>|Y-m-d H:M:S|isdst
//   UNKNOWN|<name>|<ok>|<global tz unchanged>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>
#include "esphome/components/magicband/time_zone.h"

using namespace esphome;

static void rule(const time::DSTRule &r) {
  printf("%d,%d,%d,%d,%d,%d", (int) r.type, r.month, r.week, r.day_of_week, r.day, (int) r.time_seconds);
}

int main() {
  std::vector<long long> epochs;
  long long e;
  while (scanf("%lld", &e) == 1) epochs.push_back(e);
  for (const char *name : magicband::TIME_ZONES) {
    bool ok = magicband::set_time_zone(name);
    const auto &tz = time::get_global_tz();
    printf("ZONE|%s|%d|%d|%d|", name, ok ? 1 : 0, (int) tz.std_offset_seconds, (int) tz.dst_offset_seconds);
    rule(tz.dst_start);
    printf("|");
    rule(tz.dst_end);
    printf("\n");
    for (long long ep : epochs) {
      struct tm out {};
      time::epoch_to_local_tm((time_t) ep, tz, &out);
      printf("LOCAL|%s|%lld|%04d-%02d-%02d %02d:%02d:%02d|%d\n", name, ep, out.tm_year + 1900, out.tm_mon + 1, out.tm_mday,
             out.tm_hour, out.tm_min, out.tm_sec, out.tm_isdst);
    }
  }
  // Unknown names: false, and the zone in force is left alone.
  magicband::set_time_zone("UK (London)");
  const time::ParsedTimezone before = time::get_global_tz();
  for (const char *bad : {"", "Eastern", "eastern (new york)", "Eastern (New York) ", "Europe/London", "UTC+1"}) {
    bool ok = magicband::set_time_zone(bad);
    const bool same = memcmp(&before, &time::get_global_tz(), sizeof before) == 0;
    printf("UNKNOWN|%s|%d|%d\n", bad, ok ? 1 : 0, same ? 1 : 0);
  }
  return 0;
}
