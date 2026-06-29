"""
holiday_calendar.py — single source of truth for U.S. federal holidays used to
adjust the attendance-percentage denominator.

Imported by BOTH weekly_report.py and attendance_app.py so the two entry points
can never drift on which days the office was closed (drift between those two files
has been a recurring failure mode in this project).

Policy (HR-confirmed for 2026):
  * TechSur observes all 11 U.S. federal holidays, including Columbus Day and
    Veterans Day.
  * TechSur is OPEN the day after Thanksgiving (it is not a federal holiday, so
    the `holidays` package never adds it — no special-casing needed).
  * Weekend holidays use the federal observance rule (Saturday -> observed the
    preceding Friday; Sunday -> observed the following Monday). The `holidays`
    package applies this automatically with observed=True, and the *observed*
    weekday is the day the office is actually closed.

A week containing an observed holiday is scored out of (weekdays - holidays)
instead of a flat 5, so nobody is marked absent for a day the office was shut.

If TechSur ever stops observing a specific federal holiday (e.g. Columbus or
Veterans Day) or adds a company-specific closure (e.g. Christmas Eve), adjust the
set returned by `_us_federal()` — that is the only place the calendar is defined.
The pinned test in test_holiday_calendar.py asserts the 2026 dates match HR's
published list, so any drift in the upstream `holidays` package is caught in CI.
"""

from datetime import date, datetime, timedelta
from functools import lru_cache

import holidays as _holidays


# Company-wide default in-office requirement (days per week). Per-person overrides
# live in CUSTOM_SCHEDULES in weekly_report.py / attendance_app.py. Defined here so
# both entry points import the same number and can never drift.
IN_OFFICE_REQUIRED_DAYS = 3


def _to_date(value) -> date:
    """Coerce a date / datetime / pandas.Timestamp / ISO string to a plain date."""
    if isinstance(value, datetime):          # also covers pandas.Timestamp
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):               # any other datetime-like
        try:
            return value.date()
        except Exception:
            pass
    return datetime.fromisoformat(str(value)[:10]).date()


@lru_cache(maxsize=None)
def _us_federal(year: int):
    """Observed U.S. federal holidays for a year (weekend dates shifted onto the
    adjacent weekday, which is the day the office is actually closed)."""
    return _holidays.US(years=year, observed=True)


def is_observed_holiday(value) -> bool:
    """True if `value` is an observed U.S. federal holiday (office closed)."""
    d = _to_date(value)
    return d in _us_federal(d.year)


def observed_holidays_in_range(start, end) -> set:
    """Set of observed federal holidays that fall on a weekday (Mon-Fri) within
    [start, end] inclusive. Weekend holiday dates are ignored — the office is
    already closed weekends, so they never reduce the business-day count."""
    start, end = _to_date(start), _to_date(end)
    holidays_found = set()
    for n in range((end - start).days + 1):
        day = start + timedelta(n)
        if day.weekday() < 5 and day in _us_federal(day.year):
            holidays_found.add(day)
    return holidays_found


def expected_business_days(start, end) -> int:
    """Expected working days in [start, end]: Mon-Fri count minus observed federal
    holidays that fall on a weekday. Never negative."""
    start, end = _to_date(start), _to_date(end)
    weekdays = sum(
        1 for n in range((end - start).days + 1)
        if (start + timedelta(n)).weekday() < 5
    )
    return max(0, weekdays - len(observed_holidays_in_range(start, end)))
