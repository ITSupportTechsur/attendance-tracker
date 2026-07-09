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
    """A near-namesake (same last name + first initial) must not snap onto an owner
    exception. (Uses 'Anita Yadav' — the real 'Aaniya Yadav' is now globally excluded.)"""
    mgrs = pd.DataFrame([
        {"Employee": "Amit Yadav",  "Manager": "No Manager",    "Manager Email": ""},
        {"Employee": "Anita Yadav", "Manager": "Tanisha Brown", "Manager Email": "tanisha@techsur.solutions"},
    ])
    rows = [_row("Anita", "Yadav", date(2026, 6, 8)),
            _row("Amit",  "Yadav", date(2026, 6, 9))]
    unique_days, _zero, _total, _merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, mgrs, set())
    names = set(unique_days["_name"])
    assert "Anita Yadav" in names and "Amit Yadav" in names, \
        f"Anita and Amit must stay separate, got {names}"


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
    'Anita Yadav' (absent from AD) + owner 'Amit Yadav' present -> stay separate.
    (The real 'Aaniya Yadav' is now globally excluded, so a stand-in is used here.)"""
    mgrs = pd.DataFrame([
        {"Employee": "Amit Yadav", "Manager": "No Manager", "Manager Email": ""},
    ])
    rows = [_row("Anita", "Yadav", date(2026, 6, 8)),
            _row("Amit",  "Yadav", date(2026, 6, 9))]
    unique_days, _zero, _total, merged, _junk = wr.process_attendance(
        _badge_excel(rows), START, END, mgrs, set())
    assert merged == {}, f"Anita must not fold onto the owner, got {merged}"
    assert {"Anita Yadav", "Amit Yadav"} <= set(unique_days["_name"]), set(unique_days["_name"])


def test_credential_suffix_combines_report_rows():
    """A 2nd card labelled 'Amit Yadav (2)' must combine with 'Amit Yadav' into one
    report row with summed days (the owner's two cards under one main name)."""
    mgrs = pd.DataFrame([{"Employee": "Amit Yadav", "Manager": "No Manager", "Manager Email": ""}])
    rows = [_row("Amit", "Yadav", date(2026, 6, 8)),
            _row("Amit", "Yadav (2)", date(2026, 6, 9))]
    unique_days, _z, _t, _m, _j = wr.process_attendance(
        _badge_excel(rows), START, END, mgrs, set())
    amit = unique_days[unique_days["_name"].str.contains("Amit")]
    assert len(amit) == 1, f"expected one Amit row, got {amit['_name'].tolist()}"
    assert amit["_name"].iloc[0] == "Amit Yadav", amit["_name"].iloc[0]
    assert int(amit["Days Present"].iloc[0]) == 2


def test_junk_fob_with_activity_is_dropped_and_surfaced():
    """A spare fob that swiped is removed from the report but returned in junk_active."""
    rows = [_row("Spare", "Mitchel Office", date(2026, 6, 8)),
            _row("Kamal", "Mostofa", date(2026, 6, 9))]
    unique_days, _zero, _total, _merged, junk = wr.process_attendance(
        _badge_excel(rows), START, END, MANAGERS, set())
    assert "Spare Mitchel Office" not in set(unique_days["_name"]), "spare must not be a person row"
    assert "Spare Mitchel Office" in junk, f"spare must be surfaced in junk_active, got {junk}"


# ── Report display name fix: _typo_display_map ────────────────────────────────
# A lone consistent typo ('Rami Dasari' when only that spelling swiped) is left as
# a distinct row by process_attendance so the mid-week source audit keeps flagging
# it, then relabeled to the Azure AD display name for the REPORT ONLY.

_DISPLAY_MGRS = pd.DataFrame([
    {"Employee": "Ram Dasari",             "Manager": "Kumud Trikha",  "Manager Email": "kumud@techsur.solutions"},
    {"Employee": "Arjun Kesiraju",         "Manager": "Parag Matalia", "Manager Email": "parag@techsur.solutions"},
    {"Employee": "Daniel Joseph Thompson", "Manager": "Craig Park",    "Manager Email": "craig@techsur.solutions"},
])


def test_typo_display_relabels_lone_misspelling():
    """The exact bug: 'Rami Dasari' swiped alone all week -> report shows 'Ram Dasari'."""
    m = wr._typo_display_map(["Rami Dasari"], _DISPLAY_MGRS)
    assert m == {"Rami Dasari": "Ram Dasari"}, f"expected Rami->Ram relabel, got {m}"


def test_typo_display_leaves_exact_ad_match_untouched():
    """A name already spelled like AD needs no relabel."""
    assert wr._typo_display_map(["Ram Dasari"], _DISPLAY_MGRS) == {}


def test_typo_display_preserves_legit_short_form():
    """'Daniel Thompson' shares the first+last key with AD 'Daniel Joseph Thompson',
    so it is an EXACT key match, not a typo — the short badge form is preserved and
    NOT force-expanded to the full AD name (same contract as the merge path)."""
    assert wr._typo_display_map(["Daniel Thompson"], _DISPLAY_MGRS) == {}


def test_typo_display_never_relabels_onto_owner():
    """A near-namesake absent from AD must not snap onto an owner exception."""
    mgrs = pd.DataFrame([
        {"Employee": "Amit Yadav",  "Manager": "No Manager",    "Manager Email": ""},
    ])
    # OWNER_EXCEPTIONS excludes Amit from the anchor pool, so 'Anita Yadav' finds no
    # match and is left alone rather than being renamed to the owner.
    assert wr._typo_display_map(["Anita Yadav"], mgrs) == {}


def test_typo_display_leaves_unmapped_name_alone():
    """A name that matches no AD person at all is left as-is (surfaced elsewhere as
    'unmapped'), never relabeled onto an unrelated person."""
    assert wr._typo_display_map(["Zoltan Qwixby"], _DISPLAY_MGRS) == {}


def test_typo_display_relabels_last_first_initial_nickname():
    """'Arhun Kesiraju' (fuzzy) and nickname-style last+first-initial cases resolve to
    the AD display name just like the audit classifies them."""
    m = wr._typo_display_map(["Arhun Kesiraju"], _DISPLAY_MGRS)
    assert m == {"Arhun Kesiraju": "Arjun Kesiraju"}, f"got {m}"


if __name__ == "__main__":
    test_split_spellings_are_summed_into_one_row()
    test_single_spelling_is_never_renamed_to_full_ad_name()
    test_owner_is_never_collapsed_into()
    test_nickname_folds_into_one_row_when_ad_twin_present()
    test_lone_nickname_without_twin_is_not_folded()
    test_nickname_does_not_fold_onto_owner()
    test_credential_suffix_combines_report_rows()
    test_junk_fob_with_activity_is_dropped_and_surfaced()
    test_typo_display_relabels_lone_misspelling()
    test_typo_display_leaves_exact_ad_match_untouched()
    test_typo_display_preserves_legit_short_form()
    test_typo_display_never_relabels_onto_owner()
    test_typo_display_leaves_unmapped_name_alone()
    test_typo_display_relabels_last_first_initial_nickname()
    print("All canonical-merge regression tests passed ✅")
