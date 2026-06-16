"""Regression test for the mid-week name-audit (collect_name_audit).

The Thursday name-audit emails the operator every badge name that needs
correcting in DataWatch before the week ends, grouped into four buckets:
  typos       — matched Azure AD only via fuzzy / last-name+initial
                ('Arhun Kesiraju'->'Arjun', 'Jim Rader'->'James' — the 0.80 case
                the day-count merge can't reach, so it MUST surface here)
  splits      — same person logged under >1 spelling that week ('Honey Warma')
  unmapped    — no Azure AD match at all ('Aaniya Yadav')
  junk_active — a spare/temporary fob that actually swiped ('Spare Mitchel Office')
Exact AD matches, the owner, and guest/excluded names must stay clean.

Run:  python test_name_audit.py   (or: pytest test_name_audit.py)
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

START, END = date(2026, 6, 8), date(2026, 6, 12)   # a Mon–Fri week
OFFICE = "11190 Sunrise Valley Drive"
TENANT = "Techsur Solutions"


def _badge_excel(rows) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def _row(first, last, d):
    return {"Date/Time": pd.Timestamp(d), "First Name": first, "Last Name": last,
            "Address": OFFICE, "Tenant": TENANT}


MANAGERS = pd.DataFrame([
    {"Employee": "Arjun Kesiraju", "Manager": "Shailendra Gohil", "Manager Email": "shailendra@techsur.solutions"},
    {"Employee": "James Rader",    "Manager": "Parag Matalia",    "Manager Email": "parag@techsur.solutions"},
    {"Employee": "Honey Varma",    "Manager": "Pankaj Shishodia", "Manager Email": "pankaj@techsur.solutions"},
    {"Employee": "Joe Ghaleb",     "Manager": "Amit Yadav",       "Manager Email": "amit@techsur.solutions"},
    {"Employee": "Amit Yadav",     "Manager": "No Manager",       "Manager Email": ""},
])


def _audit_from(rows, datawatch=None):
    unique_days, _zero, _total, merged, junk = wr.process_attendance(
        _badge_excel(rows), START, END, MANAGERS, datawatch or set())
    return wr.collect_name_audit(unique_days, MANAGERS, merged, junk), unique_days


def test_lone_typos_surface_in_typos_bucket():
    """A typo whose AD-correct spelling did NOT swipe that week stays a one-off row and
    is flagged as a typo: Arhun (fuzzy 0.93) and a lone Jim (last-initial, no James)."""
    rows = [_row("Arhun", "Kesiraju", date(2026, 6, 8)),
            _row("Jim",   "Rader",    date(2026, 6, 9))]
    audit, _ = _audit_from(rows)
    assert ("Arhun Kesiraju", "Arjun Kesiraju") in audit["typos"], audit["typos"]
    assert ("Jim Rader", "James Rader") in audit["typos"], audit["typos"]


def test_nickname_with_twin_moves_to_splits_not_typos():
    """When BOTH Jim and James swiped, the report folds them into one 'James Rader'
    row, so the audit reports it as a SPLIT to consolidate — not a typo."""
    rows = [_row("Jim",   "Rader", date(2026, 6, 8)),
            _row("James", "Rader", date(2026, 6, 9))]
    audit, unique_days = _audit_from(rows)
    assert audit["splits"] == {"Jim Rader": "James Rader"}, audit["splits"]
    assert all(b != "Jim Rader" for b, _ in audit["typos"]), audit["typos"]
    assert "James Rader" not in audit["unmapped"]
    assert set(unique_days["_name"]) == {"James Rader"}, set(unique_days["_name"])


def test_split_spellings_go_to_splits_not_typos():
    """'Honey Warma' merges into 'Honey Varma' (0.91) at day-count time, so it shows
    up as a split, and 'Honey Varma' itself stays clean."""
    rows = [_row("Honey", "Varma", date(2026, 6, 8)),
            _row("Honey", "Warma", date(2026, 6, 9))]
    audit, _ = _audit_from(rows)
    assert audit["splits"] == {"Honey Warma": "Honey Varma"}, audit["splits"]
    assert all(b != "Honey Varma" for b, _ in audit["typos"])


def test_unmapped_and_junk_and_clean():
    """A non-excluded name not in AD -> unmapped; spare fob with a swipe -> junk_active
    (via the 5th return, already dropped from the report); owner and an exact match
    produce nothing."""
    rows = [_row("Zara", "Quinn", date(2026, 6, 8)),     # not in AD, not excluded
            _row("Spare", "Mitchel Office", date(2026, 6, 9)),
            _row("Joe",   "Ghaleb", date(2026, 6, 10)),
            _row("Amit",  "Yadav",  date(2026, 6, 11))]
    audit, unique_days = _audit_from(rows)
    assert "Zara Quinn" in audit["unmapped"], audit["unmapped"]
    assert "Spare Mitchel Office" in audit["junk_active"], audit["junk_active"]
    assert "Spare Mitchel Office" not in set(unique_days["_name"]), "junk must not be a report row"
    flat = {n for n, _ in audit["typos"]} | set(audit["unmapped"]) | set(audit["junk_active"])
    assert "Joe Ghaleb" not in flat and "Amit Yadav" not in flat, flat


def test_clean_week_produces_nothing():
    rows = [_row("Joe", "Ghaleb", date(2026, 6, 8)),
            _row("James", "Rader", date(2026, 6, 9))]
    audit, _ = _audit_from(rows)
    assert audit["typos"] == [] and audit["splits"] == {} \
        and audit["unmapped"] == [] and audit["junk_active"] == [], audit


if __name__ == "__main__":
    test_lone_typos_surface_in_typos_bucket()
    test_nickname_with_twin_moves_to_splits_not_typos()
    test_split_spellings_go_to_splits_not_typos()
    test_unmapped_and_junk_and_clean()
    test_clean_week_produces_nothing()
    print("All name-audit regression tests passed ✅")
