"""Regression test for the 3-source name reconciliation (collect_source_audit):
DataWatch roster (D) <-> Hardware list (H) <-> Azure AD (A).

Implements the matrix the owner asked for:
  - in D and/or H but NOT in AD            -> not_in_ad
  - in DataWatch + AD but NOT Hardware     -> in_dw_not_hardware
  - in Hardware + AD but NOT DataWatch     -> in_hardware_not_dw
  - consistent across all three            -> nothing
Junk/spare/guest/placeholder names are skipped.

Run:  python test_source_audit.py   (or: pytest test_source_audit.py)
"""
import os
import pandas as pd

for _v in ("DATAWATCH_USERNAME", "DATAWATCH_PASSWORD", "AZURE_TENANT_ID",
           "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):
    os.environ.setdefault(_v, "x")
os.environ.setdefault("REPORT_FROM_EMAIL", "x@x.com")
os.environ.setdefault("REPORT_TO_EMAILS", "x@x.com")

import weekly_report as wr

AD = pd.DataFrame([{"Employee": e, "Manager": "M", "Manager Email": "m@x.com"}
                   for e in ["Ahmed Zaied", "Aashti Alam", "Paul Schomburg",
                             "James Rader", "Amit Yadav"]])


def test_matrix_buckets():
    D = {"Ahmed Zaied", "Jim Rader", "Aashti Alam", "Spare Mitchel Office"}
    H = {"Paul Schomburg", "Aashti Alam", "will be deleted after audit"}
    a = wr.collect_source_audit(D, H, AD)

    # Ahmed: D + AD, not Hardware -> in_dw_not_hardware
    assert a["in_dw_not_hardware"] == ["Ahmed Zaied"], a["in_dw_not_hardware"]
    # Paul: Hardware + AD, not DataWatch -> in_hardware_not_dw
    assert a["in_hardware_not_dw"] == ["Paul Schomburg"], a["in_hardware_not_dw"]
    # Jim: in DataWatch, not in AD (James != Jim) -> not_in_ad, with AD suggestion
    jim = [x for x in a["not_in_ad"] if x["name"] == "Jim Rader"]
    assert jim, a["not_in_ad"]
    assert jim[0]["ad_suggestion"] == "James Rader", jim[0]
    assert jim[0]["in_dw"] and not jim[0]["in_hw"]
    # Aashti: consistent across all three -> in no bucket
    flat = ([x["name"] for x in a["not_in_ad"]]
            + a["in_dw_not_hardware"] + a["in_hardware_not_dw"])
    assert "Aashti Alam" not in flat, flat
    # junk + placeholder skipped
    assert "Spare Mitchel Office" not in flat
    assert all("will be deleted" not in n.lower() for n in flat)


def test_clean_when_all_consistent():
    D = {"Ahmed Zaied", "Aashti Alam"}
    H = {"Ahmed Zaied", "Aashti Alam"}
    a = wr.collect_source_audit(D, H, AD)
    assert a == {"not_in_ad": [], "in_dw_not_hardware": [], "in_hardware_not_dw": [],
                 "unknown_sitecodes": {}}, a


def test_middle_name_does_not_false_flag():
    """AD 'Daniel Joseph Thompson' must reconcile with badge 'Daniel Thompson'."""
    ad = pd.DataFrame([{"Employee": "Daniel Joseph Thompson", "Manager": "M", "Manager Email": "m@x.com"}])
    a = wr.collect_source_audit({"Daniel Thompson"}, {"Daniel Thompson"}, ad)
    assert a["not_in_ad"] == [], a["not_in_ad"]


def test_bluetooth_only_not_flagged_as_missing_hardware():
    """A mobile/Bluetooth-only cardholder (site code 1205/1212) has no card to
    inventory, so they must NOT appear in in_dw_not_hardware. Someone with a physical
    card (274) still does, and someone with BOTH (mobile + physical) still does."""
    ad = pd.DataFrame([{"Employee": e, "Manager": "M", "Manager Email": "m@x.com"}
                       for e in ["Phys Person", "Mobile Person", "Both Cred"]])
    roster = [
        {"name": "Phys Person",   "sitecode": "274"},    # physical, not in HW -> flag
        {"name": "Mobile Person", "sitecode": "1205"},   # mobile only -> NOT flagged
        {"name": "Both Cred",     "sitecode": "1205"},   # mobile + ...
        {"name": "Both Cred",     "sitecode": "278"},    # ...physical -> flag
    ]
    a = wr.collect_source_audit(roster, set(), ad)        # empty Hardware list
    assert a["in_dw_not_hardware"] == ["Both Cred", "Phys Person"], a["in_dw_not_hardware"]
    assert "Mobile Person" not in a["in_dw_not_hardware"]


def test_name_only_input_treats_all_as_physical():
    """Back-compat: passing a plain set of names (no site codes) flags all as physical."""
    ad = pd.DataFrame([{"Employee": "Ahmed Zaied", "Manager": "M", "Manager Email": "m@x.com"}])
    a = wr.collect_source_audit({"Ahmed Zaied"}, set(), ad)
    assert a["in_dw_not_hardware"] == ["Ahmed Zaied"], a["in_dw_not_hardware"]


def test_unrecognized_sitecode_is_surfaced_and_treated_as_physical():
    """A brand-new site code (neither known-mobile nor known-physical) must be surfaced
    for classification AND treated conservatively as physical, so a real card gap is
    never silently skipped while the operator is told to classify the new code."""
    ad = pd.DataFrame([{"Employee": "New Code Person", "Manager": "M", "Manager Email": "m@x.com"}])
    roster = [{"name": "New Code Person", "sitecode": "1300"}]   # unknown code
    a = wr.collect_source_audit(roster, set(), ad)               # empty Hardware list
    assert a["unknown_sitecodes"] == {"1300": 1}, a["unknown_sitecodes"]
    assert a["in_dw_not_hardware"] == ["New Code Person"], a["in_dw_not_hardware"]


def test_known_sitecodes_are_not_surfaced_as_unknown():
    ad = pd.DataFrame([{"Employee": e, "Manager": "M", "Manager Email": "m@x.com"}
                       for e in ["A B", "C D"]])
    roster = [{"name": "A B", "sitecode": "274"}, {"name": "C D", "sitecode": "1205"}]
    a = wr.collect_source_audit(roster, {"A B"}, ad)
    assert a["unknown_sitecodes"] == {}, a["unknown_sitecodes"]


def test_credential_suffix_strip_and_amit_combine():
    """'Amit Yadav (2)' (his 2nd card) must collapse onto 'Amit Yadav' so it reconciles;
    bare/parenthesised digits are stripped, alpha tenant tags like '(1DTS)' are kept."""
    assert wr._strip_credential_suffix("Amit Yadav (2)") == "Amit Yadav"
    assert wr._strip_credential_suffix("Craig Park 2") == "Craig Park"
    assert wr._strip_credential_suffix("Amit Yadav (1DTS)") == "Amit Yadav (1DTS)"
    assert wr._strip_credential_suffix("Amit Yadav") == "Amit Yadav"
    ad = pd.DataFrame([{"Employee": "Amit Yadav", "Manager": "No Manager", "Manager Email": ""}])
    roster = [{"name": "Amit Yadav", "sitecode": "264"},
              {"name": "Amit Yadav (2)", "sitecode": "264"}]
    a = wr.collect_source_audit(roster, {"Amit Yadav"}, ad)
    flat = ([x["name"] for x in a["not_in_ad"]]
            + a["in_dw_not_hardware"] + a["in_hardware_not_dw"])
    assert flat == [], f"Amit should fully reconcile after suffix strip, got {flat}"


if __name__ == "__main__":
    test_matrix_buckets()
    test_clean_when_all_consistent()
    test_middle_name_does_not_false_flag()
    test_bluetooth_only_not_flagged_as_missing_hardware()
    test_name_only_input_treats_all_as_physical()
    test_unrecognized_sitecode_is_surfaced_and_treated_as_physical()
    test_known_sitecodes_are_not_surfaced_as_unknown()
    test_credential_suffix_strip_and_amit_combine()
    print("All source-audit regression tests passed ✅")
