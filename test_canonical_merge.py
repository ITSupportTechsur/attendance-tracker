"""Regression test for the Honey Varma split-spelling day-count bug.

DataWatch sometimes logs one person under two spellings in the same week
(e.g. 'Honey Varma' on one day, 'Honey Warma' on the others). Before the fix,
day-counting grouped by the raw badge name, so those days landed in two separate
rows and the manager only saw the days under the spelling they recognised.
process_attendance() now canonicalises split spellings onto the Azure AD display
name BEFORE counting, so the days sum into one row.

Run:  python test_canonical_merge.py   (or: pytest test_canonical_merge.py)
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
    {"Employee": "Honey Varma",   "Manager": "Pankaj Shishodia", "Manager Email": "pankaj@techsur.solutions"},
    {"Employee": "Kamal Mostofa",  "Manager": "Pankaj Shishodia", "Manager Email": "pankaj@techsur.solutions"},
    # AD carries a middle name; the badge log only ever says "Daniel Thompson".
    {"Employee": "Daniel Joseph Thompson", "Manager": "Craig Park", "Manager Email": "craig@techsur.solutions"},
])


def test_split_spellings_are_summed_into_one_row():
    """Honey in 4 days across two spellings -> one row, 4 days, under Pankaj."""
    rows = [_row("Honey", "Varma", date(2026, 6, 8))]                 # correct spelling, 1 day
    rows += [_row("Honey", "Warma", d) for d in                       # misspelled, 3 days
             (date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11))]
    rows += [_row("Kamal", "Mostofa", date(2026, 6, 8)),             # control: single spelling
             _row("Kamal", "Mostofa", date(2026, 6, 9))]

    unique_days, _zero, total, merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, MANAGERS, {"Honey Varma", "Kamal Mostofa"})

    # the split is surfaced for the pre-flight email
    assert merged == {"Honey Warma": "Honey Varma"}, f"unexpected merge map: {merged}"

    honey = unique_days[unique_days["_name"].str.contains("Honey", case=False)]
    assert len(honey) == 1, f"expected 1 Honey row, got {len(honey)}:\n{honey}"
    assert int(honey["Days Present"].iloc[0]) == 4, "Honey's 4 office days should be summed"
    assert honey["_name"].iloc[0] == "Honey Varma", "should keep the AD-correct spelling"
    assert honey["Manager"].iloc[0] == "Pankaj Shishodia"
    # control person is untouched
    kamal = unique_days[unique_days["_name"] == "Kamal Mostofa"]
    assert int(kamal["Days Present"].iloc[0]) == 2


def test_single_spelling_is_never_renamed_to_full_ad_name():
    """A person logged under ONE spelling keeps that exact name — we never expand
    'Daniel Thompson' to the AD 'Daniel Joseph Thompson' ('know the name ... without
    changing anything'). Manager still resolves correctly."""
    rows = [_row("Daniel", "Thompson", d) for d in
            (date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10))]
    unique_days, _zero, _total, _merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, MANAGERS, set())
    names = set(unique_days["_name"])
    assert "Daniel Thompson" in names, f"badge spelling must be kept, got {names}"
    assert "Daniel Joseph Thompson" not in names, "must NOT expand to the full AD name"
    daniel = unique_days[unique_days["_name"] == "Daniel Thompson"]
    assert int(daniel["Days Present"].iloc[0]) == 3
    assert daniel["Manager"].iloc[0] == "Craig Park", "manager still resolves via the AD match"


def test_owner_is_never_collapsed_into():
    """A near-namesake must not snap onto an owner exception (Aaniya != Amit)."""
    mgrs = pd.DataFrame([
        {"Employee": "Amit Yadav",   "Manager": "No Manager",      "Manager Email": ""},
        {"Employee": "Aaniya Yadav", "Manager": "Tanisha Brown",   "Manager Email": "tanisha@techsur.solutions"},
    ])
    rows = [_row("Aaniya", "Yadav", date(2026, 6, 8)),
            _row("Amit",   "Yadav", date(2026, 6, 9))]
    unique_days, _zero, _total, _merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, mgrs, set())
    names = set(unique_days["_name"])
    assert "Aaniya Yadav" in names and "Amit Yadav" in names, \
        f"Aaniya and Amit must stay separate, got {names}"


def test_nickname_folds_into_one_row_when_ad_twin_present():
    """'Jim Rader' (0.80 vs 'James Rader', below the 0.82 fuzzy cutoff) must fold into
    'James Rader' when BOTH swiped that week — one row, summed days, AD-correct kept."""
    mgrs = pd.DataFrame([
        {"Employee": "James Rader", "Manager": "Parag Matalia", "Manager Email": "parag@techsur.solutions"},
    ])
    rows = [_row("Jim",   "Rader", date(2026, 6, 8)),
            _row("James", "Rader", date(2026, 6, 9)),
            _row("James", "Rader", date(2026, 6, 10))]
    unique_days, _zero, _total, merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, mgrs, set())
    assert merged == {"Jim Rader": "James Rader"}, f"expected Jim->James fold, got {merged}"
    rader = unique_days[unique_days["_name"].str.contains("Rader")]
    assert len(rader) == 1 and rader["_name"].iloc[0] == "James Rader", rader["_name"].tolist()
    assert int(rader["Days Present"].iloc[0]) == 3, "1+2 days must sum into one row"


def test_lone_nickname_without_twin_is_not_folded():
    """If only 'Jim Rader' swiped (no 'James Rader' that week), there is no anchor to
    fold onto — the day count must NOT move; Jim stays his own row."""
    mgrs = pd.DataFrame([
        {"Employee": "James Rader", "Manager": "Parag Matalia", "Manager Email": "parag@techsur.solutions"},
    ])
    rows = [_row("Jim", "Rader", d) for d in (date(2026, 6, 8), date(2026, 6, 9))]
    unique_days, _zero, _total, merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, mgrs, set())
    assert merged == {}, f"lone nickname must not be folded, got {merged}"
    assert set(unique_days["_name"]) == {"Jim Rader"}, set(unique_days["_name"])
    assert unique_days["Manager"].iloc[0] == "Parag Matalia", "manager still resolves"


def test_nickname_does_not_fold_onto_owner():
    """A near-namesake NOT in AD must not snap onto the owner via the second pass:
    'Aaniya Yadav' (absent from AD) + owner 'Amit Yadav' present -> stay separate."""
    mgrs = pd.DataFrame([
        {"Employee": "Amit Yadav", "Manager": "No Manager", "Manager Email": ""},
    ])
    rows = [_row("Aaniya", "Yadav", date(2026, 6, 8)),
            _row("Amit",   "Yadav", date(2026, 6, 9))]
    unique_days, _zero, _total, merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, mgrs, set())
    assert merged == {}, f"Aaniya must not fold onto the owner, got {merged}"
    assert {"Aaniya Yadav", "Amit Yadav"} <= set(unique_days["_name"]), set(unique_days["_name"])


def test_junk_fob_with_activity_is_dropped_and_surfaced():
    """A spare fob that swiped is removed from the report but returned in junk_active."""
    rows = [_row("Spare", "Mitchel Office", date(2026, 6, 8)),
            _row("Kamal", "Mostofa", date(2026, 6, 9))]
    unique_days, _zero, _total, _merged, junk = wr.process_attendance(
        _badge_excel(rows), START, END, MANAGERS, set())
    assert "Spare Mitchel Office" not in set(unique_days["_name"]), "spare must not be a person row"
    assert "Spare Mitchel Office" in junk, f"spare must be surfaced in junk_active, got {junk}"


if __name__ == "__main__":
    test_split_spellings_are_summed_into_one_row()
    test_single_spelling_is_never_renamed_to_full_ad_name()
    test_owner_is_never_collapsed_into()
    test_nickname_folds_into_one_row_when_ad_twin_present()
    test_lone_nickname_without_twin_is_not_folded()
    test_nickname_does_not_fold_onto_owner()
    test_junk_fob_with_activity_is_dropped_and_surfaced()
    print("All canonical-merge regression tests passed ✅")
