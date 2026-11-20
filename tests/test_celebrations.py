"""Guest passes, lockdown, holiday and birthday shows, and the tap passport."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.magicband import holidays
from custom_components.magicband.const import DOMAIN

TAG = "04AABBCCDDEEFF"
OTHER = "04AABBCCDD0001"


def _data(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data


async def _person_with_band(hass: HomeAssistant, name: str = "Alice", uid: str = TAG, **extra) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": name, **extra}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": uid, "person": name}, blocking=True)


async def _tap(hass: HomeAssistant, uid: str, device_id: str) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": uid, "device_id": device_id})
    await hass.async_block_till_done(wait_background_tasks=True)


def _shows(hass: HomeAssistant) -> list[ServiceCall]:
    shows: list[ServiceCall] = []
    hass.services.async_register("esphome", "lounge_reader_play_show", lambda c: shows.append(c))
    return shows


# ---------------------------------------------------------------------------- holidays

@pytest.mark.parametrize(
    ("year", "first_day"),
    [(2023, date(2023, 12, 8)), (2024, date(2024, 12, 26)), (2025, date(2025, 12, 15)), (2026, date(2026, 12, 5))],
)
def test_hanukkah_dates(year: int, first_day: date) -> None:
    assert holidays.hanukkah(year) == first_day


def test_holiday_dates() -> None:
    assert holidays.easter(2026) == date(2026, 4, 5)
    names = lambda d: [h.name for h in holidays.holidays_on(d)]  # noqa: E731
    assert names(date(2026, 11, 26)) == ["Thanksgiving"]
    assert names(date(2026, 5, 25)) == ["Memorial Day"]
    assert names(date(2026, 9, 7)) == ["Labor Day"]
    assert names(date(2026, 12, 12)) == ["Hanukkah"] and names(date(2026, 12, 13)) == []
    assert names(date(2026, 12, 31)) == ["New Year"] and names(date(2026, 7, 3)) == []
    assert holidays.is_birthday("02-29", date(2027, 2, 28)) and not holidays.is_birthday("02-29", date(2028, 2, 28))
    upcoming = holidays.upcoming(date(2026, 12, 24), 3)
    assert [u["name"] for u in upcoming] == ["Christmas", "New Year", "Valentine's Day"]


def test_celebration_shows_are_reader_shows() -> None:
    from custom_components.magicband.readers import SHOW_NAMES

    assert {h.show for h in holidays.ALL} | {"Birthday", "Stamp"} <= set(SHOW_NAMES)


# ---------------------------------------------------------------------------- guest passes

async def test_guest_pass_dates_and_uses(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    await _person_with_band(hass, "Walker", guest=True)
    registry = _data(hass).registry
    start = dt_util.now() + timedelta(hours=1)
    await hass.services.async_call(
        DOMAIN, "set_guest_pass",
        {"person": "Walker", "starts": start.isoformat(), "ends": (start + timedelta(days=2)).isoformat(), "uses": 2},
        blocking=True,
    )
    assert not registry.band_allowed(TAG)  # not started yet
    freezer.tick(timedelta(hours=2))
    assert registry.band_allowed(TAG)
    taps = []
    hass.bus.async_listen("magicband_tap", lambda e: taps.append(e.data))
    await _tap(hass, TAG, reader_device.id)
    await _tap(hass, TAG, reader_device.id)
    assert [t["allowed"] for t in taps] == [True, True]
    assert registry.find_person("Walker").uses_left == 0
    await _tap(hass, TAG, reader_device.id)
    assert taps[-1]["allowed"] is False and TAG not in registry.allowed_uids()  # used up
    await hass.services.async_call(DOMAIN, "set_guest_pass", {"person": "Walker", "uses": None}, blocking=True)
    assert registry.band_allowed(TAG)
    freezer.tick(timedelta(days=3))
    assert not registry.band_allowed(TAG)  # expired
    # guests get no passport
    assert _data(hass).passport.get(registry.find_person("Walker").id)["taps"] == 0


async def test_guest_pass_daily_window(hass: HomeAssistant, setup_integration) -> None:
    await _person_with_band(hass, "Cleaner")
    registry = _data(hass).registry
    await hass.services.async_call(
        DOMAIN, "set_guest_pass", {"person": "Cleaner", "from": "09:00", "until": "12:00", "days": ["tue"]}, blocking=True
    )
    person = registry.find_person("Cleaner")
    assert person.guest
    tz = dt_util.get_default_time_zone()
    assert registry.band_allowed(TAG, datetime(2026, 11, 24, 10, 0, tzinfo=tz))  # a Tuesday
    assert not registry.band_allowed(TAG, datetime(2026, 11, 24, 13, 0, tzinfo=tz))
    assert not registry.band_allowed(TAG, datetime(2026, 11, 25, 10, 0, tzinfo=tz))
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_guest_pass",
            {"person": "Cleaner", "starts": "2026-12-02T10:00:00", "ends": "2026-12-01T10:00:00"}, blocking=True,
        )
    await hass.services.async_call(DOMAIN, "set_guest_pass", {"person": "Cleaner", "clear": True}, blocking=True)
    assert registry.band_allowed(TAG, datetime(2026, 11, 25, 10, 0, tzinfo=tz))


# ---------------------------------------------------------------------------- lockdown

async def test_lockdown_lets_in_only_exempt_people(hass: HomeAssistant, setup_integration) -> None:
    await _person_with_band(hass, "Alex")
    await _person_with_band(hass, "Kid", OTHER)
    registry = _data(hass).registry
    await hass.services.async_call(DOMAIN, "update_person", {"person": "Alex", "lockdown_exempt": True}, blocking=True)
    assert registry.allowed_uids() == sorted([TAG, OTHER])

    result = await hass.services.async_call(DOMAIN, "set_settings", {"lockdown": True}, blocking=True, return_response=True)
    assert result["lockdown"] == ["Lockdown is on"]
    await hass.async_block_till_done()
    assert registry.allowed_uids() == [TAG]
    assert hass.states.get("binary_sensor.magicbhands_lockdown").state == "on"
    await hass.services.async_call(DOMAIN, "set_settings", {"lockdown": False}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.magicbhands_lockdown").state == "off"


async def test_lockdown_when_nobody_home_and_when_the_alarm_is_armed(hass: HomeAssistant, setup_integration) -> None:
    await _person_with_band(hass, "Kid", OTHER)
    registry = _data(hass).registry
    hass.states.async_set("zone.home", "1")
    hass.states.async_set("alarm_control_panel.house", "disarmed", {"friendly_name": "House alarm"})
    await hass.services.async_call(
        DOMAIN, "set_settings", {"lockdown_away": True, "lockdown_alarm": "alarm_control_panel.house"}, blocking=True
    )
    assert registry.lockdown_reasons() == []
    hass.states.async_set("zone.home", "0")
    await hass.async_block_till_done()
    assert registry.lockdown_reasons() == ["Nobody's home"] and registry.allowed_uids() == []
    assert hass.states.get("binary_sensor.magicbhands_lockdown").state == "on"
    hass.states.async_set("zone.home", "2")
    hass.states.async_set("alarm_control_panel.house", "armed_night", {"friendly_name": "House alarm"})
    await hass.async_block_till_done()
    assert registry.lockdown_reasons() == ["House alarm is armed night"]
    with pytest.raises(Exception):
        await hass.services.async_call(DOMAIN, "set_settings", {"lockdown_alarm": "light.porch"}, blocking=True)


async def test_lockdown_at_night(hass: HomeAssistant, setup_integration) -> None:
    await _person_with_band(hass, "Kid", OTHER)
    registry = _data(hass).registry
    await hass.services.async_call(
        DOMAIN, "set_settings", {"lockdown_night": True, "lockdown_from": "22:00", "lockdown_until": "06:30"}, blocking=True
    )
    tz = dt_util.get_default_time_zone()
    assert registry.band_allowed(OTHER, datetime(2026, 11, 24, 21, 59, tzinfo=tz))
    assert not registry.band_allowed(OTHER, datetime(2026, 11, 24, 23, 0, tzinfo=tz))
    assert not registry.band_allowed(OTHER, datetime(2026, 11, 25, 6, 0, tzinfo=tz))
    assert registry.band_allowed(OTHER, datetime(2026, 11, 25, 6, 30, tzinfo=tz))
    assert registry.settings["lockdown_until"] == "06:30"


async def test_settings_survive_a_reload(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "set_settings", {"holiday_shows": False, "lockdown_from": "21:15"}, blocking=True)
    await _data(hass).registry.async_flush()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    cfg = _data(hass).registry.settings
    assert cfg["holiday_shows"] is False and cfg["lockdown_from"] == "21:15" and cfg["birthday_shows"] is True


# ---------------------------------------------------------------------------- celebrations and passport

async def test_birthday_holiday_and_badge_shows(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    shows = _shows(hass)
    badges = []
    hass.bus.async_listen("magicband_badge", lambda e: badges.append(e.data))
    freezer.move_to(datetime(2026, 10, 31, 15, 0, tzinfo=dt_util.get_default_time_zone()))  # Halloween
    await _person_with_band(hass, "Alice")
    await hass.services.async_call(DOMAIN, "update_person", {"person": "Alice", "birthday": "07-14"}, blocking=True)
    await _tap(hass, TAG, reader_device.id)
    # the first tap earns badges (First tap, Holiday tap): the Stamp show beats the holiday
    assert [c.data["show"] for c in shows] == ["Stamp"]
    assert {b["badge"] for b in badges} == {"first", "holiday"}
    await _tap(hass, TAG, reader_device.id)
    assert shows[-1].data["show"] == "Halloween"

    freezer.move_to(datetime(2027, 7, 14, 15, 0, tzinfo=dt_util.get_default_time_zone()))
    await _tap(hass, TAG, reader_device.id)
    assert shows[-1].data["show"] == "Stamp"  # Birthday tap badge (and Four seasons? not yet)
    await _tap(hass, TAG, reader_device.id)
    assert shows[-1].data["show"] == "Birthday"

    await hass.services.async_call(DOMAIN, "set_settings", {"birthday_shows": False}, blocking=True)
    count = len(shows)
    await _tap(hass, TAG, reader_device.id)
    assert len(shows) == count  # no show on an ordinary day

    # denied taps never count
    await _tap(hass, "04AABBCCDD9999", reader_device.id)
    passport = _data(hass).passport.get(_data(hass).registry.find_person("Alice").id)
    assert passport["taps"] == 5
    earned = {b["key"] for b in passport["badges"] if b["earned"]}
    assert {"first", "holiday", "birthday"} <= earned


async def test_passport_streaks_and_milestones(hass: HomeAssistant) -> None:
    from custom_components.magicband.passport import Passport

    passport = Passport(hass)
    tz = dt_util.get_default_time_zone()
    got = []
    for day in range(7):
        got += [b.key for b in passport.record("p", datetime(2026, 3, 2 + day, 6, 30, tzinfo=tz))]
    p = passport.get("p")
    assert p["streak"] == 7 and p["days"] == 7 and p["taps"] == 7
    assert {"first", "early_bird", "weekend", "streak_7"} <= set(got)
    passport.record("p", datetime(2026, 3, 10, 23, 0, tzinfo=tz))  # a day missed
    assert passport.get("p")["streak"] == 1 and passport.get("p")["best_streak"] == 7
    for _ in range(2):
        got += [b.key for b in passport.record("p", datetime(2026, 3, 10, 23, 5, tzinfo=tz))]
    assert "taps_10" in got and "night_owl" in [b["key"] for b in passport.get("p")["badges"] if b["earned"]]


async def test_play_show_today(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    shows = _shows(hass)
    freezer.move_to(datetime(2026, 12, 25, 12, 0, tzinfo=dt_util.get_default_time_zone()))
    result = await hass.services.async_call(DOMAIN, "play_show", {"show": "Today"}, blocking=True, return_response=True)
    assert shows[-1].data["show"] == "Christmas" and result["show"] == "Christmas"
    freezer.move_to(datetime(2026, 12, 27, 12, 0, tzinfo=dt_util.get_default_time_zone()))
    await hass.services.async_call(DOMAIN, "play_show", {"show": "Today"}, blocking=True)
    assert shows[-1].data["show"] == "Random"


async def test_list_has_the_new_fields(hass: HomeAssistant, setup_integration) -> None:
    await _person_with_band(hass, "Alice")
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Guest", "guest": True}, blocking=True)
    result = await hass.services.async_call(DOMAIN, "list", {}, blocking=True, return_response=True)
    people = {p["name"]: p for p in result["people"]}
    assert people["Alice"]["passport"]["taps"] == 0 and people["Alice"]["allowed_now"] is True
    assert people["Guest"]["passport"] is None and people["Guest"]["guest"] is True
    assert result["settings"]["holiday_shows"] is True and result["lockdown"] == []
    assert "holidays" in result["today"] and len(result["upcoming"]) == 4
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "update_person", {"person": "Alice", "birthday": "13-40"}, blocking=True)
