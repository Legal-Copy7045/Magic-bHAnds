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
