"""U.S. special-day calendar used by the daily-profile study: federal holidays, observed days,
bridge days and Super Bowl Sundays, 2015 to 2026. No external dependency."""

from __future__ import annotations

from datetime import date, timedelta


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) given weekday (Mon=0) of a month; n=-1 for the last one."""
    if n > 0:
        d = date(year, month, 1)
        shift = (weekday - d.weekday()) % 7
        return d + timedelta(days=shift + 7 * (n - 1))
    d = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    shift = (d.weekday() - weekday) % 7
    return d - timedelta(days=shift)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


SUPER_BOWL = {
    2016: date(2016, 2, 7),
    2017: date(2017, 2, 5),
    2018: date(2018, 2, 4),
    2019: date(2019, 2, 3),
    2020: date(2020, 2, 2),
    2021: date(2021, 2, 7),
    2022: date(2022, 2, 13),
    2023: date(2023, 2, 12),
    2024: date(2024, 2, 11),
    2025: date(2025, 2, 9),
    2026: date(2026, 2, 8),
}


def special_days(year: int) -> dict[date, str]:
    """Map date -> label for one year."""
    out: dict[date, str] = {}

    def add(d: date, label: str, observe: bool = True) -> None:
        out.setdefault(d, label)
        if observe:
            o = _observed(d)
            if o != d:
                out.setdefault(o, label + " (observed)")

    add(date(year, 1, 1), "New Year's Day")
    add(_nth_weekday(year, 1, 0, 3), "MLK Day", observe=False)
    add(_nth_weekday(year, 2, 0, 3), "Presidents' Day", observe=False)
    add(_nth_weekday(year, 5, 0, -1), "Memorial Day", observe=False)
    if year >= 2021:
        add(date(year, 6, 19), "Juneteenth")
    add(date(year, 7, 4), "Independence Day")
    add(_nth_weekday(year, 9, 0, 1), "Labor Day", observe=False)
    add(_nth_weekday(year, 10, 0, 2), "Columbus Day", observe=False)
    add(date(year, 11, 11), "Veterans Day")
    tg = _nth_weekday(year, 11, 3, 4)
    add(tg, "Thanksgiving", observe=False)
    add(tg + timedelta(days=1), "Day after Thanksgiving", observe=False)
    add(date(year, 12, 24), "Christmas Eve", observe=False)
    add(date(year, 12, 25), "Christmas Day")
    add(date(year, 12, 31), "New Year's Eve", observe=False)
    if year in SUPER_BOWL:
        add(SUPER_BOWL[year], "Super Bowl Sunday", observe=False)
    return out


def special_calendar(first_year: int = 2015, last_year: int = 2026) -> dict[date, str]:
    cal: dict[date, str] = {}
    for y in range(first_year, last_year + 1):
        cal.update(special_days(y))
    return cal


MAJOR_HOLIDAYS = (
    "New Year's Day",
    "Memorial Day",
    "Independence Day",
    "Labor Day",
    "Thanksgiving",
    "Christmas Day",
)
