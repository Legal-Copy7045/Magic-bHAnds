#pragma once
// Host mock of the generated defines.h: the time zone code is compiled in, and
// USE_HOST keeps posix_tz.cpp from replacing libc's localtime on the test host.
#define USE_TIME_TIMEZONE
#define USE_HOST
