"""Integration test: a week containing an observed federal holiday is scored out
of (weekdays − holidays), and a swipe on the closed holiday is ignored so nobody
exceeds 100 % or shows negative Days Absent.

Uses the Independence Day week (Jun 29 – Jul 3 2026; Jul 3 is the observed holiday
because Jul 4 falls on a Saturday). This is the first report the feature changes
(ships Mon Jul 6 2026).

Run:  pytest test_holiday_denominator.py   (or: python test_holiday_denominator.py)
"""
import io
import os
from datetime import date

import pandas as pd

# weekly_report.py reads these at import time; processing logic never uses them.
os.environ.setdefault("DATAWATCH_USERNAME", "x")
os.environ.setdefault("DATAWATCH_PASSWORD", "x")
os.environ.setdefault("AZURE_TENANT_ID", "x")
os.environ.setdefault("AZURE_CLIENT_ID", "x")
os.environ.setdefault("AZURE_CLIENT_SECRET", "x")
os.environ.setdefault("REPORT_FROM_EMAIL", "x@x.com")
os.environ.setdefault("REPORT_TO_EMAILS", "x@x.com")

import weekly_report as wr

# Independence Day week: Jul 4 2026 is a Saturday -> observed Friday Jul 3.
START, END = date(2026, 6, 29), date(2026, 7, 3)
WORKDAYS = [date(2026, 6, 29), date(2026, 6, 30),
            date(2026, 7, 1),  date(2026, 7, 2)]   # Mon–Thu (the 4 real workdays)
HOLIDAY = date(2026, 7, 3)                          # observed Independence Day (Fri)
OFFICE = "11190 Sunrise Valley Drive"
TENANT = "Techsur Solutions"


def _badge_excel(rows) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def _row(first, last, d):
    return {"Date/Time": pd.Timestamp(d), "First Name": first, "Last Name": last,
            "Address": OFFICE, "Tenant": TENANT}


def test_denominator_drops_to_four_in_holiday_week():
    rows  = [_row("Full", "Week", d) for d in WORKDAYS]       # present all 4 real workdays
    rows += [_row("Half", "Week", d) for d in WORKDAYS[:2]]   # present 2 of 4
    unique_days, _zero, total, _merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, pd.DataFrame(), set())

    assert total == 4, f"holiday week should be 4 business days, got {total}"

    full = unique_days[unique_days["_name"] == "Full Week"].iloc[0]
    assert int(full["Days Present"]) == 4
    assert int(full["Total Weekdays"]) == 4
    assert float(full["Attendance %"]) == 100.0
    assert int(full["Days Absent"]) == 0

    half = unique_days[unique_days["_name"] == "Half Week"].iloc[0]
    assert int(half["Days Present"]) == 2
    assert float(half["Attendance %"]) == 50.0
    assert int(half["Days Absent"]) == 2


def test_badge_swipe_on_holiday_is_ignored_no_over_100():
    """Someone who badges in on the closed holiday plus all 4 workdays is 4/4 = 100 %,
    never 5/4 = 125 %, and Days Absent stays 0 (not negative)."""
    rows  = [_row("Keen", "Bean", d) for d in WORKDAYS]
    rows += [_row("Keen", "Bean", HOLIDAY)]   # extra swipe on the observed holiday
    unique_days, _zero, total, _merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, pd.DataFrame(), set())

    assert total == 4
    keen = unique_days[unique_days["_name"] == "Keen Bean"].iloc[0]
    assert int(keen["Days Present"]) == 4, "the holiday swipe must be dropped"
    assert float(keen["Attendance %"]) == 100.0, "must cap at 100, not 125"
    assert int(keen["Days Absent"]) == 0


def test_custom_schedule_employee_in_holiday_week():
    """A 1-day/week employee (Joe Ghaleb) present 1 day is still 100 % in a 4-day
    week; a 2-day/week employee (Aashti Alam) present 1 of 2 is 50 %."""
    rows  = [_row("Joe", "Ghaleb", WORKDAYS[0])]
    rows += [_row("Aashti", "Alam", WORKDAYS[0])]   # 1 of expected 2
    unique_days, _zero, total, _merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, pd.DataFrame(), set())

    assert total == 4
    joe = unique_days[unique_days["_name"] == "Joe Ghaleb"].iloc[0]
    assert int(joe["Total Weekdays"]) == 1, "min(1 sched, 4 week) = 1"
    assert float(joe["Attendance %"]) == 100.0

    aashti = unique_days[unique_days["_name"] == "Aashti Alam"].iloc[0]
    assert int(aashti["Total Weekdays"]) == 2
    assert float(aashti["Attendance %"]) == 50.0


def test_zero_attendance_uses_holiday_adjusted_denominator():
    """A DataWatch holder with no swipes in a holiday week shows Days Absent = 4."""
    rows = [_row("Present", "Person", d) for d in WORKDAYS]
    unique_days, _zero, total, _merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, pd.DataFrame(), {"Absent Andy"})

    assert total == 4
    andy = unique_days[unique_days["_name"] == "Absent Andy"]
    assert len(andy) == 1, f"expected Absent Andy as a zero row, got {set(unique_days['_name'])}"
    andy = andy.iloc[0]
    assert int(andy["Days Present"]) == 0
    assert int(andy["Days Absent"]) == 4, "absent the whole 4-day week"
    assert int(andy["Total Weekdays"]) == 4
    assert float(andy["Attendance %"]) == 0.0


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
