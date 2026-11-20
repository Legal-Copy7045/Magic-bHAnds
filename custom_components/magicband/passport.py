"""The tap passport: each person's taps, streaks and badges ("stamps").

Only welcomed taps count (not denied ones, not the tap that enrols a band),
and guests don't get a passport. A new badge fires ``magicband_badge`` and,
if passport shows are on, the readers play the Stamp show after the welcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .holidays import holidays_on, is_birthday

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.passport"
STORAGE_VERSION = 1


@dataclass(frozen=True)
class Badge:
    key: str
    name: str
    how: str
    icon: str


BADGES = (
    Badge("first", "First tap", "Your first tap in", "🎟️"),
    Badge("taps_10", "Regular", "10 taps", "🔟"),
    Badge("taps_50", "Frequent visitor", "50 taps", "⭐"),
    Badge("taps_100", "Century", "100 taps", "💯"),
    Badge("taps_250", "Super fan", "250 taps", "🌟"),
    Badge("taps_500", "Annual passholder", "500 taps", "🏰"),
    Badge("taps_1000", "Legend", "1,000 taps", "👑"),
    Badge("early_bird", "Early bird", "A tap before 7 am", "🌅"),
    Badge("night_owl", "Night owl", "A tap after 10 pm", "🦉"),
    Badge("weekend", "Weekender", "Taps on a Saturday and the Sunday after", "🎡"),
    Badge("streak_7", "Week streak", "Taps on 7 days in a row", "🔥"),
    Badge("streak_30", "Month streak", "Taps on 30 days in a row", "🚀"),
    Badge("holiday", "Holiday tap", "A tap on a holiday", "🎉"),
    Badge("holidays_5", "Holiday hopper", "Taps on 5 different holidays", "🎊"),
    Badge("birthday", "Birthday tap", "A tap on your birthday", "🎂"),
    Badge("seasons", "Four seasons", "Taps in winter, spring, summer and autumn", "🍂"),
)
BADGE_BY_KEY = {b.key: b for b in BADGES}
_TAP_MILESTONES = ((1, "first"), (10, "taps_10"), (50, "taps_50"), (100, "taps_100"), (250, "taps_250"),
                   (500, "taps_500"), (1000, "taps_1000"))


def _season(day: date) -> str:
    return ("winter", "spring", "summer", "autumn")[(day.month % 12) // 3]


class Passport:
    """Per-person tap stats and badges, kept in their own store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._people: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        raw = await self._store.async_load() or {}
        people = raw.get("people") if isinstance(raw, dict) else None
        self._people = {k: v for k, v in (people or {}).items() if isinstance(k, str) and isinstance(v, dict)}

    async def async_flush(self) -> None:
        await self._store.async_save({"people": self._people})

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"people": self._people}, 2.0)

    def get(self, person_id: str) -> dict[str, Any]:
        """A person's passport for the page: stats, earned badges and the ones still to get."""
        p = self._people.get(person_id) or {}
        earned = p.get("badges") or {}
        return {
            "taps": p.get("taps", 0),
            "days": p.get("days", 0),
            "streak": p.get("streak", 0),
            "best_streak": p.get("best_streak", 0),
            "first": p.get("first"),
            "badges": [
                {"key": b.key, "name": b.name, "how": b.how, "icon": b.icon, "earned": earned.get(b.key)}
                for b in BADGES
            ],
        }

    @callback
    def forget(self, person_id: str) -> None:
        if self._people.pop(person_id, None) is not None:
            self._save()

    @callback
    def record(self, person_id: str, when: datetime, birthday: str | None = None) -> list[Badge]:
        """Count a welcomed tap at `when` (local time). Returns the badges it newly earned."""
        p = self._people.setdefault(person_id, {})
        today = when.date()
        p["taps"] = p.get("taps", 0) + 1
        p.setdefault("first", when.isoformat())
        last = date.fromisoformat(p["last_day"]) if p.get("last_day") else None
        if last != today:
            p["days"] = p.get("days", 0) + 1
            p["streak"] = p.get("streak", 0) + 1 if last == today - timedelta(days=1) else 1
            p["best_streak"] = max(p.get("best_streak", 0), p["streak"])
            p["last_day"] = today.isoformat()
        seasons = set(p.get("seasons") or [])
        seasons.add(_season(today))
        p["seasons"] = sorted(seasons)
        if today.weekday() == 5:
            p["last_saturday"] = today.isoformat()
        holidays = set(p.get("holidays") or [])
        for h in holidays_on(today):
            holidays.add(f"{today.year}-{h.key}")
        p["holidays"] = sorted(holidays)[-60:]

        earned: dict[str, str] = p.setdefault("badges", {})
        want = [key for count, key in _TAP_MILESTONES if p["taps"] >= count]
        if when.hour < 7 and when.hour >= 4:
            want.append("early_bird")
        if when.hour >= 22:
            want.append("night_owl")
        if today.weekday() == 6 and p.get("last_saturday") == (today - timedelta(days=1)).isoformat():
            want.append("weekend")
        if p["streak"] >= 7:
            want.append("streak_7")
        if p["streak"] >= 30:
            want.append("streak_30")
        if holidays_on(today):
            want.append("holiday")
        if len(holidays) >= 5:
            want.append("holidays_5")
        if is_birthday(birthday, today):
            want.append("birthday")
        if len(seasons) == 4:
            want.append("seasons")
        new = [BADGE_BY_KEY[k] for k in dict.fromkeys(want) if k not in earned]
        for badge in new:
            earned[badge.key] = when.isoformat()
        self._save()
        return new
