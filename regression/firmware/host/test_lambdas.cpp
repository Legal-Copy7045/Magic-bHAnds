// The reader's lambdas, extracted from esphome/magicband-reader.yaml by
// lambdas.py (lambdas_gen.h), run on the host with ASan/UBSan.
#include <set>
#include "lambdas_gen.h"

using hosttest::fmt;
using hosttest::MockRing;
using hosttest::result;
using esphome::Color;

static const float NaN = NAN;
static const Color WARM(255, 178, 89);

// ---------------------------------------------------------------- effects
static void fw150_idle_circle() {
  std::string why;
  long frames = 0;
  const int ns[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 35, 60, 99, 100};
  const float heads[] = {NaN, -1, 0, 1, 2, 3, 4, 5, 9};
  const float fades[] = {NaN, -10, 0, 50, 150};
  const float times[] = {NaN, 0.5f, 10};
  for (int n : ns)
    for (float hs : heads) {
      const float tails[] = {NaN, 0, 1, 2, 3, (float) (n / 2), (float) n, (float) n + 5, 1000};
      for (float ts : tails)
        for (float fs : fades)
          for (float ct : times) {
            mock::idle_circle_heads.state = hs, mock::idle_circle_tail.state = ts, mock::idle_tail_fade.state = fs, mock::idle_circle_time.state = ct;
            const int he = std::isnan(hs) ? 1 : std::max(1, std::min(4, (int) hs));
            int te = std::isnan(ts) || ts < 1 ? std::max(n / 5, 3) : (int) ts;
            te = std::max(1, std::min(te, n / he));
            for (uint32_t base : {0u, 0xFFFFF000u}) {
              mock::now_ms = base;
              MockRing f(n, false), r(n, false);
              mock::idle_circle_direction.opt = "Forward";
              gen::fx_idle_circle(f, WARM, true);
              mock::idle_circle_direction.opt = "Reverse";
              gen::fx_idle_circle(r, WARM, true);
              for (uint32_t dt = 0; dt < 12000; dt += 1201) {
                mock::now_ms = base + dt;
                mock::idle_circle_direction.opt = "Forward";
                gen::fx_idle_circle(f, WARM, false);
                mock::idle_circle_direction.opt = "Reverse";
                gen::fx_idle_circle(r, WARM, false);
                frames += 2;
                if (!f.guards_ok() || !r.guards_ok()) { why += fmt("n=%d: wrote outside the ring; ", n); break; }
                const int lit = f.lit();
                const int want = n >= he ? he * te : -1;
                if ((want >= 0 && lit != want) || (want < 0 && (lit < 1 || lit > n))) {
                  if (why.size() < 1200) why += fmt("n=%d heads=%g tail=%g fade=%g: %d LEDs lit, expected %d heads x %d; ", n, hs, ts, fs, lit, he, te);
                  break;
                }
                bool mirror = true;
                for (int i = 0; i < n && mirror; i++)
                  if (memcmp(f.px(i), r.px(n - 1 - i), 3) != 0) mirror = false;
                if (!mirror) { if (why.size() < 1200) why += fmt("n=%d: Reverse isn't the mirror of Forward; ", n); break; }
              }
            }
          }
    }
  result("FW-150", why.empty(), why.empty() ? fmt("%ld frames: heads clamp to 1-4, tail to 1..n/heads (NaN/0 = a fifth, at least 3), no overlap, Reverse mirrors Forward, nothing outside the ring (n 1-100, millis wrap)", frames) : why);
}

static void fw151_other_effects() {
  std::string why;
  long frames = 0;
  const int ns[] = {1, 2, 3, 5, 8, 12, 24, 60, 100};
  const float any[] = {NaN, -1, 0, 0.05f, 0.2f, 1, 2, 10, 100, 1e6f};
  for (int n : ns)
    for (float v : any)
      for (bool w : {false, true})
        for (uint32_t base : {0u, 0xFFFFFF00u}) {
          mock::circle_time.state = v, mock::circle_tail.state = v * 7, mock::pulse_time.state = v;
          mock::welcome_fade_in.state = v, mock::welcome_hold.state = v, mock::welcome_fade_out.state = v;
          for (int pc : {0, 1, 5}) {
            mock::pulse_count = pc;
            MockRing a(n, w), b(n, w), c(n, w), d(n, w), e(n, w);
            mock::now_ms = base;
            gen::fx_chase(a, WARM, true);
            gen::fx_pulse(b, WARM, true);
            gen::fx_welcome(c, WARM, true);
            gen::fx_spin(d, WARM, true);
            gen::fx_breathe(e, WARM, true);
            for (uint32_t dt = 0; dt < 8000; dt += 173) {
              mock::now_ms = base + dt;
              gen::fx_chase(a, WARM, false);
              gen::fx_pulse(b, WARM, false);
              gen::fx_welcome(c, WARM, false);
              gen::fx_spin(d, WARM, false);
              gen::fx_breathe(e, WARM, false);
              frames += 5;
            }
            if (!a.guards_ok() || !b.guards_ok() || !c.guards_ok() || !d.guards_ok() || !e.guards_ok()) why += fmt("n=%d v=%g: wrote outside the ring; ", n, v);
            if (pc == 0 && (b.lit() || c.lit())) why += fmt("n=%d: Pulse/Welcome lit with pulse_count 0; ", n);
          }
        }
  // Welcome with all times 0 never divides by zero (UBSan would stop) and Pulse ends dark after its pulses.
  result("FW-151", why.empty(), why.empty() ? fmt("%ld frames of Chase, Pulse, Welcome, Spin, Breathe with NaN/negative/zero/huge settings, RGB and RGBW, millis wrap: no overrun, no UB", frames) : why);
}

static void fw152_warm_glow() {
  std::string why;
  for (int n : {1, 24, 100})
    for (bool night : {false, true})
      for (float g : {NaN, -5.0f, 0.0f, 5.0f, 10.0f, 30.0f, 50.0f, 100.0f, 150.0f}) {
        mock::night = night;
        (night ? mock::idle_glow_night : mock::idle_glow).state = g;
        (night ? mock::idle_glow : mock::idle_glow_night).state = 77;  // the other one must be ignored
        MockRing r(n, false);
        gen::fx_warm_glow(r, WARM, true);
        uint8_t *p0 = r.px(0);
        for (int i = 1; i < n; i++)
          if (memcmp(r.px(i), p0, 3)) { why += "LEDs differ; "; break; }
        const int R = p0[0], G = p0[1], B = p0[2];
        const bool off = !std::isnan(g) && g <= 0;
        if (off && (R || G || B)) why += fmt("glow %g: lit %d,%d,%d; ", g, R, G, B);
        if (!off && (R < 5 || G == 0 || G > R || B > G)) why += fmt("glow %g (night %d): %d,%d,%d isn't a warm white; ", g, night, R, G, B);
        if (!off && std::abs(G - 0.37f * R) > 1.0f + 0.05f * R) why += fmt("glow %g: green %d not 37%% of red %d; ", g, G, R);
      }
  // brighter setting never dimmer
  int prev = 0;
  mock::night = false;
  for (int g = 5; g <= 100; g += 5) {
    mock::idle_glow.state = g;
    MockRing r(1, false);
    gen::fx_warm_glow(r, WARM, true);
    if (r.px(0)[0] < prev) why += fmt("glow %d dimmer than %d; ", g, g - 5);
    prev = r.px(0)[0];
  }
  result("FW-152", why.empty(), why.empty() ? "Warm glow: same warm mix on every LED (green ~37 % of red, blue below green), off at 0 %, uses the night setting at night, brighter with the setting" : why);
}

// ---------------------------------------------------------------- lockout
static void reset_lockout() {
  mock::refusal_times.fill(0);
  mock::lockout_until = 0;
  mock::tap_lockout.state = true;
  mock::lockout_refusals.state = 5, mock::lockout_window.state = 60, mock::lockout_minutes.state = 5;
}
static void refuse(uint32_t at) {
  mock::now_ms = at;
  gen::script_note_refusal();
}
static void fw153_note_refusal() {
  std::string why;
  // off: counted but never locks
  reset_lockout();
  mock::tap_lockout.state = false;
  for (int i = 0; i < 10; i++) refuse(1000 + i * 100);
  if (mock::lockout_until) why += "locked out with the switch off; ";
  if (mock::refusal_times[0] != 1900 || mock::refusal_times[9] != 1000) why += "refusals not recorded newest first; ";
  // on: 4 in the window no, 5th yes, for 5 min, and the list is cleared
  reset_lockout();
  for (int i = 0; i < 4; i++) refuse(10000 + i * 1000);
  if (mock::lockout_until) why += "locked out after 4 of 5; ";
  refuse(20000);
  if (mock::lockout_until != 20000 + 5 * 60000) why += fmt("5th refusal: lockout_until %u, expected %u; ", mock::lockout_until, 20000 + 5 * 60000);
  for (uint32_t t : mock::refusal_times)
    if (t) { why += "refusal list not cleared at lockout; "; break; }
  // spread wider than the window: never
  reset_lockout();
  for (int i = 0; i < 12; i++) refuse(100000 + i * 16000);  // 5 span 64 s > 60 s
  if (mock::lockout_until) why += "locked out by refusals spread over more than the window; ";
  // exactly the window apart still counts (<=)
  reset_lockout();
  for (int i = 0; i < 5; i++) refuse(500000 + i * 15000);  // first to last = 60 s
  if (!mock::lockout_until) why += "5 refusals exactly 60 s apart (first to last) didn't lock; ";
  // NaN settings use the defaults 5 / 60 s / 5 min
  reset_lockout();
  mock::lockout_refusals.state = NaN, mock::lockout_window.state = NaN, mock::lockout_minutes.state = NaN;
  for (int i = 0; i < 5; i++) refuse(700000 + i * 10000);
  if (mock::lockout_until != 740000 + 300000) why += fmt("defaults: lockout_until %u; ", mock::lockout_until);
  // the most the setting allows (20) still works with the 20-slot list
  reset_lockout();
  mock::lockout_refusals.state = 20;
  for (int i = 0; i < 19; i++) refuse(900000 + i * 1000);
  if (mock::lockout_until) why += "locked after 19 of 20; ";
  refuse(920000);
  if (!mock::lockout_until) why += "20 of 20 didn't lock (list too short?); ";
  // millis wrap: refusals across 2^32 still count, and lockout_until is never 0
  reset_lockout();
  for (int i = 0; i < 5; i++) refuse(0xFFFFFFFFu - 20000 + i * 10000);
  if (!mock::lockout_until) why += "refusals across the millis() wrap didn't lock; ";
  reset_lockout();
  mock::lockout_minutes.state = 1;
  for (int i = 0; i < 5; i++) refuse(0u - 60000u - 4 + i);  // the 5th at 2^32 - 60000 -> until wraps to 0
  if (mock::lockout_until == 0) why += "lockout_until wrapped to 0 (no lockout); ";
  reset_lockout();
  refuse(0);
  if (mock::refusal_times[0] != 1) why += "a refusal at millis()=0 was stored as 0 (not counted); ";
  result("FW-153", why.empty(), why.empty() ? "note_refusal: counts only with the switch on, N within the window (inclusive) locks for the set minutes, clears its list, NaN uses 5/60 s/5 min, 20-of-20 works, millis wrap handled" : why);
}

static void fw154_lockout_end() {
  std::string why;
  mock::lockout_until = 0;
  mock::now_ms = 12345;
  if (gen::lockout_over()) why += "over while not locked; ";
  if (gen::tag_locked()) why += "taps refused while not locked; ";
  mock::lockout_until = 50000;
  mock::now_ms = 49999;
  if (gen::lockout_over()) why += "over 1 ms early; ";
  if (!gen::tag_locked()) why += "tap taken during lockout; ";
  mock::now_ms = 50000;
  if (!gen::lockout_over()) why += "not over at its time; ";
  mock::lockout_until = 100;  // set just before the wrap, now just after
  mock::now_ms = 0xFFFFFF00u;
  if (gen::lockout_over()) why += "wrap: over before its time; ";
  mock::now_ms = 200;
  if (!gen::lockout_over()) why += "wrap: not over after its time; ";
  mock::refusal_times.fill(7);
  gen::script_end_lockout();
  if (mock::lockout_until != 0) why += "end_lockout left lockout_until set; ";
  for (uint32_t t : mock::refusal_times)
    if (t) { why += "end_lockout left refusals; "; break; }
  result("FW-154", why.empty(), why.empty() ? "the tap handler refuses taps exactly while lockout_until != 0; the 5 s interval ends it at its time (millis wrap safe); end_lockout clears it and the refusals" : why);
}

// ---------------------------------------------------------------- quiet
static void fw155_apply_quiet() {
  std::string why;
  auto &sp = mock::reader_speaker;
  mock::sound_at_night.opt = "Quieter";
  mock::night_volume.state = 30;
  mock::quiet_applied = false;
  sp.volume = 0.8f, sp.calls = 0;
  mock::night = false;
  gen::script_apply_quiet();
  if (sp.calls) why += "day with nothing applied: touched the volume; ";
  mock::night = true;
  gen::script_apply_quiet();
  if (fabsf(sp.volume - 0.3f) > 1e-6f || !mock::quiet_applied || fabsf(mock::day_volume - 0.8f) > 1e-6f) why += fmt("night: volume %.2f, day volume %.2f; ", sp.volume, mock::day_volume);
  sp.volume = 0.55f;  // changed by hand during the night
  int calls = sp.calls;
  gen::script_apply_quiet();
  if (sp.calls != calls || fabsf(sp.volume - 0.55f) > 1e-6f) why += "night again: overrode a volume set by hand; ";
  mock::night = false;
  gen::script_apply_quiet();
  if (fabsf(sp.volume - 0.8f) > 1e-6f || mock::quiet_applied) why += fmt("morning: volume %.2f, not back to 0.80; ", sp.volume);
  calls = sp.calls;
  gen::script_apply_quiet();
  if (sp.calls != calls) why += "day again: touched the volume; ";
  // "Same" at night: nothing changes
  mock::sound_at_night.opt = "Same";
  mock::night = true;
  sp.volume = 0.6f;
  gen::script_apply_quiet();
  if (fabsf(sp.volume - 0.6f) > 1e-6f || mock::quiet_applied) why += "not Quieter: volume changed at night; ";
  // switched to Quieter during the night, then off again during the night
  mock::sound_at_night.opt = "Quieter";
  mock::night_volume.state = NaN;
  gen::script_apply_quiet();
  if (fabsf(sp.volume - 0.3f) > 1e-6f) why += fmt("NaN night volume: %.2f, not the 30 %% default; ", sp.volume);
  mock::sound_at_night.opt = "Same";
  gen::script_apply_quiet();
  if (fabsf(sp.volume - 0.6f) > 1e-6f) why += "turning Quieter off at night didn't restore the day volume; ";
  result("FW-155", why.empty(), why.empty() ? "apply_quiet: night saves the day volume and sets Night volume, morning restores it, acts only on a change (hand-set volumes stay), Same leaves it, NaN = 30 %" : why);
}

// ---------------------------------------------------------------- night
static bool night_at(int h, int m) {
  mock::ha_time.t.valid = true, mock::ha_time.t.hour = h, mock::ha_time.t.minute = m;
  gen::script_update_night();
  return mock::night;
}
static void fw156_update_night() {
  std::string why;
  mock::ring_ready = false;
  mock::night_mode.opt = "Fixed hours";
  mock::night_from.state = 22, mock::night_until.state = 6;
  struct C { int h, m; bool want; } cs[] = {{21, 59, false}, {22, 0, true}, {23, 59, true}, {0, 0, true}, {5, 59, true}, {6, 0, false}, {12, 0, false}};
  for (auto c : cs)
    if (night_at(c.h, c.m) != c.want) why += fmt("22-6: %02d:%02d gave %d; ", c.h, c.m, !c.want);
  mock::night_from.state = 1, mock::night_until.state = 5;
  if (!night_at(3, 0) || night_at(0, 59) || night_at(5, 0)) why += "1-5 window wrong; ";
  mock::night_from.state = 7, mock::night_until.state = 7;
  if (night_at(7, 0) || night_at(19, 0)) why += "from == until should never be night; ";
  mock::night_from.state = NaN, mock::night_until.state = NaN;
  if (night_at(0, 0)) why += "NaN hours gave night; ";
  // sunset to sunrise (minutes), with offsets, wrapping midnight
  mock::night_mode.opt = "Sunset to sunrise";
  mock::sunset_min = 17 * 60 + 30, mock::sunrise_min = 7 * 60 + 10;
  mock::night_after_sunset.state = 30, mock::night_after_sunrise.state = -10;
  if (night_at(17, 59) || !night_at(18, 0) || !night_at(6, 59) || night_at(7, 0)) why += "sunset+30 to sunrise-10 window wrong; ";
  mock::night_after_sunset.state = 240, mock::sunset_min = 22 * 60;  // pushes past midnight
  if (night_at(23, 0) || !night_at(2, 0)) why += "sunset offset past midnight wrong; ";
  mock::sunset_min = -1;  // not known yet: falls back to the fixed hours
  mock::night_from.state = 22, mock::night_until.state = 6;
  if (!night_at(23, 0)) why += "unknown sunset didn't fall back to Night from/until; ";
  mock::ha_time.t.valid = false;
  mock::night = true;
  gen::script_update_night();
  if (mock::night) why += "clock not set: still night; ";
  // redraw only when it changes, and only when idle
  mock::ring_ready = true;
  mock::reader_idle.executed = 0;
  mock::band_tapped.running = false;
  night_at(23, 0);
  night_at(23, 30);
  if (mock::reader_idle.executed != 1) why += fmt("idle glow redrawn %d times for one change; ", mock::reader_idle.executed);
  mock::band_tapped.running = true;
  night_at(12, 0);
  if (mock::reader_idle.executed != 1) why += "redrew the ring during a tap; ";
  result("FW-156", why.empty(), why.empty() ? "update_night: fixed hours and sunset/sunrise windows (with offsets) wrap midnight, from==until is never night, unknown sun falls back, unset clock is day, redraws once per change and never during a tap" : why);
}

static void fw157_sun_time() {
  std::string why;
  struct C { const char *zone, *iso; bool rising; int want; } cs[] = {
      {"Eastern (New York)", "2026-11-20T21:41:07.123+00:00", false, 16 * 60 + 41},
      {"Eastern (New York)", "2026-07-01T09:30:00+00:00", true, 5 * 60 + 30},
      {"Eastern (New York)", "2026-11-20T16:41:07-05:00", false, 16 * 60 + 41},
      {"UK (London)", "2026-06-21T03:43:00+00:00", true, 4 * 60 + 43},
      {"Central Europe (Paris)", "2026-12-21T07:42:00+00:00", true, 8 * 60 + 42},
      {"Hawaii (Honolulu)", "2026-03-08T04:30:00Z", false, 18 * 60 + 30},
      {"Pacific (Los Angeles)", "2026-03-09T02:05:00+00:00", false, 19 * 60 + 5},
  };
  for (auto &c : cs) {
    esphome::magicband::set_time_zone(c.zone);
    mock::sunset_min = mock::sunrise_min = -1;
    mock::ha_time.t.valid = false;
    gen::script_sun_time(c.iso, c.rising);
    const int got = c.rising ? mock::sunrise_min : mock::sunset_min;
    if (got != c.want) why += fmt("%s %s: %02d:%02d, expected %02d:%02d; ", c.zone, c.iso, got / 60, got % 60, c.want / 60, c.want % 60);
  }
  mock::sunset_min = 123;
  gen::script_sun_time("not a time", false);
  if (mock::sunset_min != 123) why += "garbage changed the stored sunset; ";
  result("FW-157", why.empty(), why.empty() ? "sun_time turns Home Assistant's ISO times (any UTC offset or Z) into local minutes in the set zone; garbage is ignored" : why);
}

// ---------------------------------------------------------------- bands
static void set_list(const std::string &s) {
  mock::known_list.fill(0);
  std::copy(s.begin(), s.end(), mock::known_list.begin());
}
static void fw158_known_decision() {
  std::string why;
  set_list(",04A1B2C3D4E5F6,0A0B0C0D,11223344556677889900,");
  struct C { const char *uid; int want; } cs[] = {
      {"04A1B2C3D4E5F6", 1}, {"04-a1-b2-c3-d4-e5-f6", 1}, {"04:A1:B2:C3:D4:E5:F6", 1}, {"0a0b0c0d", 1}, {"11223344556677889900", 1},
      {"04A1B2C3D4E5", 2}, {"A1B2C3D4", 2}, {"04A1B2C3D4E5F600", 2}, {"", 2}, {"TEST", 2}, {"0A0B0C0D0E", 2}, {"0A0B0C0Dzz", 1}};
  for (auto &c : cs) {
    mock::decision = 0;
    gen::known_decision(c.uid);
    if (mock::decision != c.want) why += fmt("uid '%s': %s; ", c.uid, mock::decision == 1 ? "welcomed" : "denied");
  }
  set_list("");
  mock::decision = 0;
  gen::known_decision("04A1B2C3D4E5F6");
  if (mock::decision != 2) why += "empty list welcomed a band; ";
  result("FW-158", why.empty(), why.empty() ? "Known bands only: 4/7/10-byte IDs match whole entries case- and separator-insensitively; other lengths, partial IDs and an empty list are denied" : why);
}

static void fw159_allow_last_band() {
  std::string why;
  using namespace esphome::magicband;
  auto list = [] { return std::string(mock::known_list.data()); };
  mock::pair_key.fill(0);
  set_list("");
  mock::last_band.state = "04-A1-B2-C3-D4-E5-F6";
  gen::allow_last_band();
  if (list() != ",04A1B2C3D4E5F6,") why += "unpaired: not added as ,ID, (" + list() + "); ";
  gen::allow_last_band();
  if (list() != ",04A1B2C3D4E5F6,") why += "added twice; ";
  mock::last_band.state = "TEST";
  gen::allow_last_band();
  if (list() != ",04A1B2C3D4E5F6,") why += "the test button's TEST was added; ";
  reader_pair(mock::pair_key, std::string(64, 'a'));
  mock::last_band.state = "0A0B0C0D";
  gen::allow_last_band();
  if (list() != ",04A1B2C3D4E5F6,") why += "paired: the button still added a band; ";
  mock::pair_key.fill(0);
  std::string full = ",";
  while (full.size() + 15 < mock::known_list.size()) full += "04A1B2C3D4E5F6,";
  set_list(full);
  mock::last_band.state = "0A0B0C0D";
  gen::allow_last_band();
  if (list() != full) why += "a full list overflowed or changed; ";
  if (mock::known_list.back() != 0) why += "list not terminated; ";
  result("FW-159", why.empty(), why.empty() ? "Allow last band: adds a real band ID once, ignores TEST, does nothing on a paired reader, refuses when the list is full" : why);
}

static void fw161_tag_pairing() {
  std::string why;
  using namespace esphome::magicband;
  mock::pair_key.fill(0), mock::pending_key.fill(0);
  mock::now_ms = 1000;
  if (gen::tag_confirms_pair()) why += "a tap with nothing pending confirmed pairing; ";
  reader_request_pair(mock::pair_key, mock::pending_key, mock::pending_until, std::string(32, 'b'), 1000);
  mock::now_ms = 50000;
  mock::lockout_until = 99999;  // even during a lockout
  const bool confirmed = gen::tag_confirms_pair();
  if (!confirmed || !reader_paired(mock::pair_key)) why += "a tap during the wait didn't confirm pairing; ";
  mock::lockout_until = 0;
  result("FW-161", why.empty(), why.empty() ? "on_tag: a tap confirms a waiting first pairing (also during a refused-tap lockout) and does nothing else; with nothing pending it falls through" : why);
}

// SEC-006: Forget last band / Forget all bands do nothing on a paired reader
static void fw174_forget_buttons() {
  std::string why;
  using namespace esphome::magicband;
  auto list = [] { return std::string(mock::known_list.data()); };
  const std::string two = ",04A1B2C3D4E5F6,0A0B0C0D,";
  mock::pair_key.fill(0);
  reader_pair(mock::pair_key, std::string(64, 'a'));
  set_list(two);
  mock::last_band.state = "0A0B0C0D";
  gen::forget_last_band();
  if (list() != two) why += "paired: Forget last band changed the list (" + list() + "); ";
  gen::forget_all_bands();
  if (list() != two) why += "paired: Forget all bands changed the list (" + list() + "); ";
  mock::pair_key.fill(0);
  gen::forget_last_band();
  if (list() != ",04A1B2C3D4E5F6,") why += "unpaired: Forget last band didn't remove the band (" + list() + "); ";
  gen::forget_all_bands();
  if (!list().empty()) why += "unpaired: Forget all bands didn't empty the list (" + list() + "); ";
  set_list("");
  result("FW-174", why.empty(), why.empty() ? "Forget last band and Forget all bands leave a paired reader's list alone and work as before on an unpaired one" : why);
}

// SEC-008: unknown bands reach Home Assistant at most 6 new a minute / 30 an hour; listed bands always
static void fw175_tag_report() {
  std::string why;
  mock::unknown_tags = esphome::magicband::UnknownTagLimit{};
  set_list(",04A1B2C3D4E5F6,");
  uint32_t t = 5000;
  int sent = 0;
  // a flood of made-up 7-byte IDs, one every 3 s for an hour
  for (int i = 0; i < 1200; i++, t += 3000) {
    mock::now_ms = t;
    if (gen::tag_report(fmt("04%012X", 0x100000 + i))) sent++;
    // the household's listed band in between, in any spelling, is always sent
    if (i % 50 == 0 && !gen::tag_report("04-a1-b2-c3-d4-e5-f6")) why += fmt("a listed band was held back at t=%u; ", t);
  }
  if (sent > 30) why += fmt("%d made-up IDs reported in an hour (limit 30); ", sent);
  if (sent < 30) why += fmt("only %d made-up IDs reported in an hour (expected 30: the limit shouldn't be stricter than documented); ", sent);
  // within a minute: no more than 6 new ones, and a reported one tapped again still goes
  mock::unknown_tags = esphome::magicband::UnknownTagLimit{};
  int minute = 0;
  for (int i = 0; i < 20; i++) {
    mock::now_ms = 10000000 + i * 1000;
    if (gen::tag_report(fmt("0A0B%04X", i))) minute++;
  }
  if (minute != 6) why += fmt("%d new IDs in 20 s (want 6); ", minute);
  mock::now_ms += 1000;
  if (!gen::tag_report("0A0B0003")) why += "a band reported a moment ago, tapped again, was held back; ";
  // after the minute, new ones go again
  mock::now_ms += 61000;
  if (!gen::tag_report("0A0BFFFF")) why += "no new ID reported a minute later; ";
  set_list("");
  mock::unknown_tags = esphome::magicband::UnknownTagLimit{};
  result("FW-175", why.empty(), why.empty() ? fmt("unknown bands: 6 new a minute and 30 an hour reach Home Assistant (a 1-hour flood of 1,200 made-up IDs: %d), retaps of a reported band and listed bands always do", sent) : why);
}

// SEC-011: the play_show action plays at most 12 shows a minute
static void fw176_play_show_limit() {
  std::string why;
  mock::show_calls = esphome::magicband::RateLimit<12>{};
  int ok = 0;
  for (int i = 0; i < 40; i++) {
    mock::now_ms = 0xFFFFFFFFu - 20000 + i * 1000;  // across the millis() wrap
    if (gen::play_show_allowed()) ok++;
  }
  if (ok != 12) why += fmt("%d of 40 calls in 40 s allowed (want 12); ", ok);
  mock::now_ms += 60000;
  if (!gen::play_show_allowed()) why += "a call a minute later was refused; ";
  mock::show_calls = esphome::magicband::RateLimit<12>{};
  ok = 0;
  for (int i = 0; i < 120; i++) {
    mock::now_ms = 100000 + i * 5000;  // one every 5 s for 10 minutes
    if (gen::play_show_allowed()) ok++;
  }
  if (ok != 120) why += fmt("one call every 5 s: %d of 120 allowed (want all); ", ok);
  result("FW-176", why.empty(), why.empty() ? "play_show action: 12 calls a minute, sliding (also across the millis() wrap); one every 5 s always plays" : why);
}

// BUG-008: start-up sound after a power cut, before the clock is set
static void fw172_boot_sound() {
  std::string why;
  struct C { bool sound, valid, night; const char *mode; bool want; } cs[] = {
      {true, false, false, "Normal", true},  {true, false, false, "Quieter", false}, {true, false, false, "Off", false},
      {true, true, true, "Off", false},      {true, true, false, "Off", true},       {true, true, true, "Quieter", true},
      {true, true, true, "Normal", true},    {false, true, false, "Normal", false},  {false, false, false, "Normal", false}};
  for (auto &c : cs) {
    mock::sound_enabled.state = c.sound;
    mock::sntp_time.t.valid = c.valid;
    mock::ha_time.t.valid = false;
    mock::night = c.night;
    mock::sound_at_night.opt = c.mode;
    if (gen::boot_sound() != c.want)
      why += fmt("sound %d, time %s, night %d, Sound at night %s: %s; ", c.sound, c.valid ? "known" : "unknown", c.night, c.mode, c.want ? "silent" : "played");
  }
  mock::sntp_time.t.valid = false;
  mock::ha_time.t.valid = true, mock::night = true, mock::sound_at_night.opt = "Off", mock::sound_enabled.state = true;
  if (gen::boot_sound()) why += "Home Assistant's clock alone set, night, Off: played; ";
  result("FW-172", why.empty(), why.empty() ? "start-up sound: with the time unknown only 'Sound at night' Normal plays it; with the time known, Off at night is silent" : why);
}

int main() {
  fw150_idle_circle();
  fw151_other_effects();
  fw152_warm_glow();
  fw153_note_refusal();
  fw154_lockout_end();
  fw155_apply_quiet();
  fw156_update_night();
  fw157_sun_time();
  fw158_known_decision();
  fw159_allow_last_band();
  fw161_tag_pairing();
  fw172_boot_sound();
  fw174_forget_buttons();
  fw175_tag_report();
  fw176_play_show_limit();
  return 0;
}
