"""Compliance model: an honest Attendance % for EVERYONE plus a per-person
Required/Status (Met / Not Met).

  Required  = custom schedule, else company default (IN_OFFICE_REQUIRED_DAYS=3),
              capped by the holiday-adjusted week.
  Status    = "Met" if Days Present >= Required else "Not Met".
  Attendance % = Days Present / expected_business_days  (SAME formula for everyone) —
              so a 1-day-per-week person reads 20%, with Status "Met", NOT a fake 100%.

Covers a normal 5-day week (no holiday) — the case nothing tested before.

Run:  pytest test_compliance_status.py
"""
import io
import os
from datetime import date

import pandas as pd

for _k, _v in {
    "DATAWATCH_USERNAME": "x", "DATAWATCH_PASSWORD": "x",
    "AZURE_TENANT_ID": "x", "AZURE_CLIENT_ID": "x", "AZURE_CLIENT_SECRET": "x",
    "REPORT_FROM_EMAIL": "x@x.com", "REPORT_TO_EMAILS": "x@x.com",
}.items():
    os.environ.setdefault(_k, _v)

import weekly_report as wr
from holiday_calendar import IN_OFFICE_REQUIRED_DAYS

# A clean Mon–Fri week with no federal holiday (Jun 8–12 2026; Juneteenth is Jun 19).
START, END = date(2026, 6, 8), date(2026, 6, 12)
WORKDAYS = [date(2026, 6, d) for d in (8, 9, 10, 11, 12)]
OFFICE = "11190 Sunrise Valley Drive"
TENANT = "Techsur Solutions"


def _badge_excel(rows):
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def _row(first, last, d):
    return {"Date/Time": pd.Timestamp(d), "First Name": first, "Last Name": last,
            "Address": OFFICE, "Tenant": TENANT}


def _run(rows, datawatch=set()):
    unique_days, _z, total, _m, _j = wr.process_attendance(
        _badge_excel(rows), START, END, pd.DataFrame(), datawatch)
    return unique_days, total


def test_default_requirement_is_three():
    assert IN_OFFICE_REQUIRED_DAYS == 3


def test_normal_week_three_of_five_is_met_at_60pct():
    ud, total = _run([_row("Reg", "Ular", d) for d in WORKDAYS[:3]])   # 3 of 5
    assert total == 5
    r = ud[ud["_name"] == "Reg Ular"].iloc[0]
    assert int(r["Total Weekdays"]) == 5
    assert int(r["Required"]) == 3
    assert float(r["Attendance %"]) == 60.0          # honest %, unchanged from before
    assert r["Status"] == "Met"                      # 3 >= 3
    assert int(r["Days Absent"]) == 0


def test_normal_week_two_of_five_is_not_met():
    ud, _ = _run([_row("Short", "Fall", d) for d in WORKDAYS[:2]])     # 2 of 5
    r = ud[ud["_name"] == "Short Fall"].iloc[0]
    assert int(r["Required"]) == 3
    assert float(r["Attendance %"]) == 40.0
    assert r["Status"] == "Not Met"                  # 2 < 3 (count-based, not the old <60%)
    assert int(r["Days Absent"]) == 1                # 3 required - 2 present


def test_full_week_caps_and_is_met():
    ud, _ = _run([_row("All", "In", d) for d in WORKDAYS])            # 5 of 5
    r = ud[ud["_name"] == "All In"].iloc[0]
    assert float(r["Attendance %"]) == 100.0
    assert r["Status"] == "Met"
    assert int(r["Days Absent"]) == 0


def test_one_day_person_reads_honest_20pct_but_met():
    """Joe Ghaleb (custom 1 day) present 1 of 5 → honest 20% with Status Met (NOT 100%).
    This is the exact case the owner described."""
    ud, _ = _run([_row("Joe", "Ghaleb", WORKDAYS[0])])
    joe = ud[ud["_name"] == "Joe Ghaleb"].iloc[0]
    assert int(joe["Required"]) == 1
    assert int(joe["Total Weekdays"]) == 5           # denominator NOT overridden anymore
    assert float(joe["Attendance %"]) == 20.0        # honest share of the week
    assert joe["Status"] == "Met"                    # 1 >= 1
    assert int(joe["Days Absent"]) == 0


def test_two_day_person_met_at_40pct():
    """A custom 2-office-days person present 2 → 40% honest, Met."""
    ud, _ = _run([_row("Mary", "Raguso", WORKDAYS[0]), _row("Mary", "Raguso", WORKDAYS[1])])
    a = ud[ud["_name"] == "Mary Raguso"].iloc[0]
    assert int(a["Required"]) == 2
    assert float(a["Attendance %"]) == 40.0
    assert a["Status"] == "Met"
    assert int(a["Days Absent"]) == 0


def test_two_day_person_one_day_is_not_met():
    ud, _ = _run([_row("Mary", "Raguso", WORKDAYS[0])])   # 1 of required 2
    a = ud[ud["_name"] == "Mary Raguso"].iloc[0]
    assert int(a["Required"]) == 2
    assert float(a["Attendance %"]) == 20.0
    assert a["Status"] == "Not Met"
    assert int(a["Days Absent"]) == 1


def test_aashti_one_day_requirement_met():
    """Aashti Alam is at FAA two days/week, so her TechSur requirement is 1 day/week
    (owner request, Marina Fox 2026-07-01). Present 1 → honest 20%, Met."""
    ud, _ = _run([_row("Aashti", "Alam", WORKDAYS[0])])
    a = ud[ud["_name"] == "Aashti Alam"].iloc[0]
    assert int(a["Required"]) == 1
    assert float(a["Attendance %"]) == 20.0
    assert a["Status"] == "Met"                # 1 >= 1
    assert int(a["Days Absent"]) == 0


def test_zero_attendance_person_is_not_met():
    ud, _ = _run([_row("Present", "Person", d) for d in WORKDAYS], datawatch={"Absent Andy"})
    andy = ud[ud["_name"] == "Absent Andy"].iloc[0]
    assert int(andy["Days Present"]) == 0
    assert int(andy["Required"]) == 3
    assert int(andy["Days Absent"]) == 3
    assert andy["Status"] == "Not Met"
    assert float(andy["Attendance %"]) == 0.0


def test_custom_schedules_identical_across_modules():
    """Guard against drift between the two duplicated CUSTOM_SCHEDULES dicts."""
    import ast
    import pathlib

    def _extract(fname):
        src = (pathlib.Path(__file__).parent / fname).read_text()
        for node in ast.walk(ast.parse(src)):
            target_ids = (
                [getattr(node.target, "id", "")] if isinstance(node, ast.AnnAssign)
                else [getattr(t, "id", "") for t in getattr(node, "targets", [])]
            )
            if "CUSTOM_SCHEDULES" in target_ids:
                return ast.literal_eval(node.value)
        raise AssertionError(f"CUSTOM_SCHEDULES not found in {fname}")

    wr_cs = _extract("weekly_report.py")
    app_cs = _extract("attendance_app.py")
    assert wr_cs == app_cs, f"CUSTOM_SCHEDULES drift: {wr_cs} != {app_cs}"
    assert wr_cs == wr.CUSTOM_SCHEDULES


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
