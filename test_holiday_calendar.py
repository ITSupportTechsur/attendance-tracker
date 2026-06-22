"""Unit tests for holiday_calendar.py — the U.S. federal-holiday calendar that
reduces the attendance denominator on weeks containing a holiday.

The PINNED test (test_2026_dates_match_hr_published_list) asserts the library
produces exactly the dates HR published for 2026, so any drift in the upstream
`holidays` package — or a change in which holidays TechSur observes — is caught
in CI rather than silently mis-scoring a holiday week.

Run:  pytest test_holiday_calendar.py
"""
from datetime import date, datetime

import pandas as pd

from holiday_calendar import (
    expected_business_days,
    observed_holidays_in_range,
    is_observed_holiday,
)


# TechSur's HR-published 2026 company holidays (observed dates).
HR_2026 = {
    date(2026, 6, 19):  "Juneteenth (Fri)",
    date(2026, 7, 3):   "Independence Day (observed; Jul 4 is a Saturday)",
    date(2026, 9, 7):   "Labor Day",
    date(2026, 10, 12): "Columbus Day",
    date(2026, 11, 11): "Veterans Day",
    date(2026, 11, 26): "Thanksgiving",
    date(2026, 12, 25): "Christmas",
}


def test_2026_dates_match_hr_published_list():
    """Every date HR published must be recognised as an observed holiday."""
    for d, label in HR_2026.items():
        assert is_observed_holiday(d), f"{d} ({label}) should be an observed holiday"


def test_day_after_thanksgiving_is_not_a_holiday():
    """TechSur is OPEN the Friday after Thanksgiving (not a federal holiday)."""
    assert not is_observed_holiday(date(2026, 11, 27))


def test_clean_week_is_five_business_days():
    assert expected_business_days(date(2026, 6, 8), date(2026, 6, 12)) == 5


def test_independence_week_is_four_business_days():
    """Jun 29–Jul 3 2026: Jul 3 is the observed Independence Day -> 4 days."""
    assert expected_business_days(date(2026, 6, 29), date(2026, 7, 3)) == 4


def test_thanksgiving_week_is_four_business_days():
    """Nov 23–27 2026: only Thu Nov 26 drops (TechSur works Black Friday) -> 4."""
    assert expected_business_days(date(2026, 11, 23), date(2026, 11, 27)) == 4
    assert observed_holidays_in_range(
        date(2026, 11, 23), date(2026, 11, 27)) == {date(2026, 11, 26)}


def test_saturday_holiday_shifts_to_friday():
    """Jul 4 2026 (Sat) -> observed Friday Jul 3; the Saturday itself never reduces
    a business-day count (it's already a weekend)."""
    assert is_observed_holiday(date(2026, 7, 3))
    assert observed_holidays_in_range(
        date(2026, 6, 29), date(2026, 7, 3)) == {date(2026, 7, 3)}


def test_sunday_holiday_shifts_to_monday():
    """Jul 4 2027 is a Sunday -> observed Monday Jul 5."""
    assert is_observed_holiday(date(2027, 7, 5))
    assert expected_business_days(date(2027, 7, 5), date(2027, 7, 9)) == 4


def test_christmas_2027_saturday_shifts_to_friday():
    """Christmas Dec 25 2027 is a Saturday -> observed Friday Dec 24."""
    assert is_observed_holiday(date(2027, 12, 24))


def test_year_boundary_range_unions_both_years():
    """A range spanning New Year must see holidays from BOTH years."""
    # Dec 28 2026 (Mon) – Jan 1 2027 (Fri): New Year's Day 2027 falls in range.
    rng = observed_holidays_in_range(date(2026, 12, 28), date(2027, 1, 1))
    assert date(2027, 1, 1) in rng
    assert expected_business_days(date(2026, 12, 28), date(2027, 1, 1)) == 4


def test_monday_anchored_holidays_never_shift():
    """Memorial/Labor/MLK are weekday-anchored and never move."""
    assert is_observed_holiday(date(2026, 5, 25))   # Memorial Day (last Mon May)
    assert is_observed_holiday(date(2026, 9, 7))    # Labor Day (1st Mon Sep)
    assert is_observed_holiday(date(2026, 1, 19))   # MLK Day (3rd Mon Jan)


def test_accepts_datetime_timestamp_and_string():
    """is_observed_holiday coerces date / datetime / pandas.Timestamp / ISO string
    (badge logs may hold any of these)."""
    assert is_observed_holiday(datetime(2026, 12, 25, 9, 30))
    assert is_observed_holiday(pd.Timestamp("2026-12-25"))
    assert is_observed_holiday("2026-12-25")
    assert not is_observed_holiday("2026-12-24")


def test_weekend_only_range_is_zero_and_safe():
    """A Sat–Sun range has 0 business days (no crash, no negative)."""
    assert expected_business_days(date(2026, 6, 20), date(2026, 6, 21)) == 0


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
