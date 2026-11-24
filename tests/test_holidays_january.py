"""Hanukkah days that fall in January (the festival that began the previous December)."""

from datetime import date

from custom_components.magicband import holidays


def test_hanukkah_running_into_january_counts() -> None:
    # Hanukkah 5785: first candle the evening of 25 December 2024, so its eight days are 26 Dec - 2 Jan.
    assert holidays.hanukkah(2024) == date(2024, 12, 26)
    assert holidays.HANUKKAH in holidays.holidays_on(date(2025, 1, 2))
    assert holidays.HANUKKAH not in holidays.holidays_on(date(2025, 1, 3))


def test_every_hanukkah_day_is_found_for_a_decade() -> None:
    for year in range(2024, 2035):
        first = holidays.hanukkah(year)
        days = [date.fromordinal(first.toordinal() + i) for i in range(8)]
        assert all(holidays.HANUKKAH in holidays.holidays_on(d) for d in days), year


def test_upcoming_lists_hanukkah_once_when_it_runs_into_january() -> None:
    """BUG-019: the January days of a Hanukkah that began in December aren't a second Hanukkah."""
    for start in (date(2024, 12, 20), date(2027, 12, 20)):
        keys = [h["key"] for h in holidays.upcoming(start, 12)]
        assert keys.count("hanukkah") == 1, (start, keys)
    # ...and next December's Hanukkah is still listed in a long enough list.
    dates = [h["date"] for h in holidays.upcoming(date(2024, 12, 20), 30) if h["key"] == "hanukkah"]
    assert dates == ["2024-12-26", "2025-12-15"], dates
