"""Holidays and birthdays: which celebration show a day gets.

On a holiday the readers play its show after each welcome (and "Today" in
magicband.play_show plays it); on someone's birthday their own taps get the
Birthday show. Dates are US ones, worked out for any year (Easter by the
Gregorian computus, Hanukkah from the Hebrew calendar).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Holiday:
    key: str
    name: str
    show: str


NEW_YEAR = Holiday("new_year", "New Year", "New Year")
VALENTINE = Holiday("valentine", "Valentine's Day", "Valentine")
ST_PATRICK = Holiday("st_patrick", "St Patrick's Day", "St Patrick")
EASTER = Holiday("easter", "Easter", "Easter")
MEMORIAL = Holiday("memorial_day", "Memorial Day", "Stars and Stripes")
INDEPENDENCE = Holiday("independence_day", "Independence Day", "Stars and Stripes")
LABOR = Holiday("labor_day", "Labor Day", "Stars and Stripes")
HALLOWEEN = Holiday("halloween", "Halloween", "Halloween")
VETERANS = Holiday("veterans_day", "Veterans Day", "Stars and Stripes")
THANKSGIVING = Holiday("thanksgiving", "Thanksgiving", "Thanksgiving")
HANUKKAH = Holiday("hanukkah", "Hanukkah", "Hanukkah")
CHRISTMAS = Holiday("christmas", "Christmas", "Christmas")

ALL = (NEW_YEAR, VALENTINE, ST_PATRICK, EASTER, MEMORIAL, INDEPENDENCE, LABOR, HALLOWEEN, VETERANS,
       THANKSGIVING, HANUKKAH, CHRISTMAS)
CELEBRATION_SHOWS = ("Birthday", "New Year", "Valentine", "St Patrick", "Easter", "Stars and Stripes",
                     "Halloween", "Thanksgiving", "Hanukkah", "Christmas")


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th `weekday` (Mon=0) of a month; n=-1 for the last."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = (date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def easter(year: int) -> date:
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    return date(year, month, (h + l - 7 * m + 33 * month + 19) % 32)


# Hebrew calendar (from Dershowitz & Reingold, Calendrical Calculations), enough for 25 Kislev.
_HEBREW_EPOCH = -1373427  # fixed day (date.toordinal) of 1 Tishrei, year 1


def _elapsed_days(year: int) -> int:
    months = (235 * year - 234) // 19
    parts = 12084 + 13753 * months
    day = months * 29 + parts // 25920
    return day + 1 if (3 * (day + 1)) % 7 < 3 else day


def _new_year_delay(year: int) -> int:
    ny0, ny1, ny2 = _elapsed_days(year - 1), _elapsed_days(year), _elapsed_days(year + 1)
    if ny2 - ny1 == 356:
        return 2
    return 1 if ny1 - ny0 == 382 else 0


def _rosh_hashanah(year: int) -> int:
    return _HEBREW_EPOCH + _elapsed_days(year) + _new_year_delay(year)


def hanukkah(year: int) -> date:
    """The first day of Hanukkah (25 Kislev) that falls in Gregorian `year` (late Nov or Dec).

    The first candle is lit the evening before.
    """
    hyear = year + 3761
    start = _rosh_hashanah(hyear)
    length = _rosh_hashanah(hyear + 1) - start
    cheshvan = 30 if length % 10 == 5 else 29  # a "complete" year has a long Cheshvan
    return date.fromordinal(start + 30 + cheshvan + 24)


def holidays_on(day: date) -> list[Holiday]:
    """The holidays on `day` (usually none, rarely two)."""
    y, found = day.year, []
    fixed = {
        (1, 1): NEW_YEAR, (12, 31): NEW_YEAR, (2, 14): VALENTINE, (3, 17): ST_PATRICK, (7, 4): INDEPENDENCE,
        (10, 31): HALLOWEEN, (11, 11): VETERANS, (12, 24): CHRISTMAS, (12, 25): CHRISTMAS,
    }
    if (h := fixed.get((day.month, day.day))) is not None:
        found.append(h)
    if day == easter(y):
        found.append(EASTER)
    if day == _nth_weekday(y, 5, 0, -1):
        found.append(MEMORIAL)
    if day == _nth_weekday(y, 9, 0, 1):
        found.append(LABOR)
    if day == _nth_weekday(y, 11, 3, 4):
        found.append(THANKSGIVING)
    # Hanukkah lasts eight days and can run into January (the one that started the previous December).
    if any(first <= day < first + timedelta(days=8) for first in (hanukkah(y), hanukkah(y - 1))):
        found.append(HANUKKAH)
    return found


def is_birthday(birthday: str | None, day: date) -> bool:
    """`birthday` is "MM-DD"; 29 February counts on 28 February in other years."""
    if not birthday:
        return False
    try:
        month, dom = (int(x) for x in birthday.split("-")[:2])
    except ValueError:
        return False
    if (month, dom) == (2, 29) and not _leap(day.year):
        return (day.month, day.day) == (2, 28)
    return (day.month, day.day) == (month, dom)


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def upcoming(day: date, count: int = 4) -> list[dict]:
    """The next `count` holidays from `day` (today included), for the page."""
    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for offset in range(0, 400):
        d = day + timedelta(days=offset)
        for h in holidays_on(d):
            key = (h.key, d.year + (1 if h is NEW_YEAR and d.month == 12 else 0))
            if key in seen:
                continue  # one entry per multi-day holiday
            seen.add(key)
            out.append({"key": h.key, "name": h.name, "show": h.show, "date": d.isoformat()})
            if len(out) >= count:
                return out
    return out
