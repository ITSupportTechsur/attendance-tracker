# Plan — In-office requirement (3 days/week) attendance model

> ⚠️ **SUPERSEDED 2026-06-29** by `2026-06-29_hybrid-compliance-status-model.md`. The owner chose to keep the % formula honest (no denominator change) and add a separate Met/Below status. This doc's "change the denominator to `required` and cap" approach is NOT the chosen path — kept for history only.

**Status:** PLAN ONLY — not executed. Awaiting owner go-ahead.
**Policy (locked):** 3 days/week company-wide default · cap at 100% · keep `CUSTOM_SCHEDULES` as per-person overrides.

## Rule
```
person_required = CUSTOM_SCHEDULES.get(name, 3)         # company default 3, custom wins
required        = min(person_required, expected_business_days_in_week)   # holiday ceiling
Attendance %    = min(Days Present / required, 1) × 100   # 3/3 = 100, 4/3 capped at 100
Days Absent     = max(0, required − Days Present)
```
The shipped holiday adjustment stays as the **ceiling** (only bites if a week has fewer working days than the requirement).

## Logic changes (small — the custom-schedule loops already do this)
- New shared constant `IN_OFFICE_REQUIRED_DAYS = 3` in `holiday_calendar.py` (the existing shared module), imported by both files — avoids drift.
- `weekly_report.py` default block (~L822-829): `_req_default = min(3, total_weekdays)`; write it into the column, use as denominator (keep `.clip(upper=100)`), `Days Absent = (_req_default - present).clip(lower=0)`.
- `weekly_report.py` zero-row literal (~L879-884): `total_weekdays` → `_req_default`.
- Mirror in `attendance_app.py` default block (~L573-576) + zero-row literal (~L635-638).
- The two `CUSTOM_SCHEDULES` override loops in EACH file (main + zero rows) need **no change** — they already use `min(_cs_exp, total_weekdays)` and overwrite, so no double-application. 3-day custom entries (shawn/david/nat/tapan) become redundant but are kept as explicit pins.
- **Scope note (blocker):** compute `_req_default` where it's visible to BOTH the default block and the gated zero-row block (NameError risk otherwise).

## Display relabel surface (owner wants HTML + Excel updated)
| Surface | Site | Old → New |
|---|---|---|
| Excel | wr `_NUM_COLS` L965, `col_widths` L1064, cols L1080/L1108 | "Total Weekdays" column → **"Required"** |
| HTML | wr table header L1212 | `<th>Total</th>` → **`<th>Required</th>`** |
| HTML | wr report-meta L1394 | `{n} working day(s)` → **`{n} business day(s)` (holiday-adjusted)** |
| Email | wr L1515 | "Working days" → **"Expected business days"** (+ optional "In-office requirement: 3/wk") |
| Teams | wr L1605 | "Working days" fact → **"Expected business days"** |
| Streamlit | app caption L219, metric L682 ("Weekdays in Range"), banner L884, table cols L814/L901/L939 | → **"Required"** (per-person) / **"Expected Business Days"** (company) |

## Tests
- UPDATE `test_holiday_denominator.py` — all existing asserts run in the 4-day holiday week; under the new rule many flip (denom→3, %→capped, Days Absent→off-3). Rename the misnamed test.
- ADD a **non-holiday 5-day-week** fixture (blocker — currently nothing tests a normal week): present 3 of 5 → 100%/0 absent; 2 of 5 → 66.7%/1 absent; 5 of 5 → 100% (cap); 0 → 0%/3 absent.
- ADD: ceiling-bites test (2-business-day week → required 2); zero-attendance custom person; parity (CUSTOM_SCHEDULES + constant identical across both modules).
- UPDATE `test_report_format.py` (blocker — it's a SECOND COPY of the renderer with its own headers/_NUM_COLS/col_widths): mirror EVERY label change here too, and keep rendered-header assertions or tests false-green.

## ⚠️ Things the critic flagged that need your call
1. **At-risk threshold regression (important).** Today "at risk" = `<60%`. With 3 days = 100%, someone present **2 of 3 = 66.7%** sits ABOVE 60% → would NOT be flagged, even though they missed a third of their required days. Likely want to move the band (e.g. `<67%` = missed ≥1 of 3). Decide before shipping.
2. **Pre-existing Streamlit bug** (`attendance_app.py:895-897`): the labels say "≥80% / 50–79% / <50%" but the code uses 60/40 bands. Already wrong; the new model makes it more visible. Reconcile labels + thresholds together.
3. **Everything shifts upward.** Present 3-of-5 was 60%/2-absent → now 100%/0-absent. Week-over-week history breaks; average attendance jumps. Intended, but worth communicating.

## Open decisions (gate execution)
1. Column wording: **"Required"** vs "Required Days" vs "Days Required" (apply uniformly).
2. Move the at-risk threshold? (see #1 above)
3. Constant `3` hardcoded vs env-configurable (`IN_OFFICE_REQUIRED_DAYS`)?
4. Add an explicit "In-office requirement: 3 days/week" line to email/Teams? (recommended)
5. Rename the pandas column KEY ("Total Weekdays"→"Required") everywhere, or relabel only at render? (key rename = cleaner but wider diff; must grep all sites incl. `test_report_format.py` to avoid KeyError)

## Ordered steps (for execution)
1. Owner confirms open decisions (esp. wording + at-risk band).
2. Add `IN_OFFICE_REQUIRED_DAYS=3` to `holiday_calendar.py`; import in both files.
3. Edit `weekly_report.py` default block + zero-row literal.
4. Mirror in `attendance_app.py`.
5. Apply all display relabels (incl. `test_report_format.py`'s embedded copy).
6. Grep both files + test_report_format.py for stale "Total Weekdays"/"working day(s)"/"Weekdays in Range".
7. Update + add tests; run `pytest -v` green.
8. End-to-end smoke: generate Excel/HTML/email for a normal week AND the Jul-3 holiday week; check Required=3, % caps at 100, Days Absent recomputed, labels correct; repeat in Streamlit.
