# Plan — Hybrid compliance: honest % + Met/Not Met status

**Status:** PLAN ONLY — design locked via owner Q&A 2026-06-29; awaiting go-ahead to build.
**Supersedes:** `2026-06-23_in-office-requirement-3day.md` (that plan changed the *denominator* to "required days"; this one does NOT — see "Why this differs").
**Origin:** TechSur Teams policy thread (Pankaj's "Total Weekdays varies / 3-of-3 should be 100%" question + Kumud's authoritative answer: *"minimum of 60% in-office attendance"*, *"2 days office + 1 day customer site"*, *"holidays not made up"*) + Marina's note that Shivalik/Aashti took offset days for FAA weekend release work.

---

## Locked decisions (owner, 2026-06-29)

1. **Attendance % stays honest and identical for everyone:** `Days Present ÷ expected_business_days` (holiday-adjusted), capped 100. The percentage is NOT redefined and NOT scored against the requirement.
2. **Add two derived columns:** `Required` (the person's in-office requirement) and `Status` (`present/required` + `✅ Met` / `⚠️ Not Met`).
3. **Compliance is shown via Status, not via the number.** A person who meets their requirement reads `✅ Met` even at a low honest % (e.g. Joe = 1 of 1 = **20% ✅ Met**).
4. **Special-schedule people show their HONEST %, not % of requirement.** Joe shows **20%** (not 100%), Aashti shows **40%** (not 100%) — each with `✅ Met`. → This **removes the current denominator-override** behavior (see "Central logic change").
5. **At-risk / RAG color driven by Status (`Not Met`), not the flat `<60%`.** So Joe (1/1) and Aashti (2/2) stop showing red; a required-3 person who came twice correctly shows red.
6. **Customer-site handled implicitly — NO note.** People who split office/customer-site just get `Required` = their office days (Aashti = 2); 2 days in the office = `✅ Met`. No customer-site annotation displayed. Registry stays a plain `name → int`.
7. **Hard-exclude list unchanged:** guest fobs, contractors, building badges, junk, non-AD names (Aaniya) stay excluded. No remote employees surfaced (owner confirmed "excluded" meant the custom-schedule people, not the hard-excludes).
8. **Holidays:** already shipped (`expected_business_days` drops federal holidays) — acts as the ceiling on `Required`. Add a one-line visible note that holidays are excluded and need no make-up.
9. **No exceptions / PTO / comp-time mechanism — explicitly out of scope.** The report states `Met` / `Not Met` for everyone, one rule. When someone is `Not Met`, the **manager explains why in the Teams channel** (e.g. Marina's FAA offset-days note). Capturing reasons is not the report's job.

---

## The rule

```
person_required = REQUIRED_DAYS.get(name, IN_OFFICE_REQUIRED_DAYS)   # default 3, registry wins
required        = min(person_required, expected_business_days)        # holiday ceiling
Attendance %    = min(Days Present / expected_business_days, 1) * 100  # UNCHANGED — same for all
Status          = "Met"   if Days Present >= required else "Not Met"
Days short      = max(0, required - Days Present)                      # for the Not Met detail
```

`Days Absent` (existing column) stays `max(0, required - present)` so it lines up with Status.

## Why this differs from the 2026-06-23 plan (lower risk)
The old plan changed the denominator to `required` and capped — which forced moving the at-risk threshold AND reset week-over-week history. This model **leaves the % formula untouched**, so:
- the percentage means exactly what it always has (no history reset);
- "at-risk" simply re-points to `Status == Not Met` instead of `< 60`;
- the work becomes **additive columns + a color/threshold re-point**, not a denominator rewrite.

---

## Central logic change (the one behavior change)

Today both files compute a custom-schedule person's % by **overriding the denominator**:
- `attendance_app.py` ~579-590 (active rows) and ~643-649 (zero rows)
- `weekly_report.py` ~822-829 (default) + the custom-schedule override loops + zero-row literals ~857-885

**Change:** stop overriding `Total Weekdays`/denominator for custom people. Keep `Total Weekdays = expected_business_days` for everyone; compute `Required` separately from the registry; compute `%` with the single shared formula. Net effect: custom-schedule people drop from ~100% to their honest % (Joe 100%→20%), offset by `✅ Met`.

> ⚠️ **Verify-first:** confirm the active-row override loop actually exists at ~579-590 before editing — one mapper agent reported the override only on zero rows. The plan doc (old) and the compliance map both say two loops per file; check both files.

---

## Registry (keep bare `CUSTOM_SCHEDULES` shape — `name → int`)

Today: `CUSTOM_SCHEDULES = {name_key: int}` ([attendance_app.py:49-58](../../attendance_app.py#L49-L58)) — current contents: `aashti alam→2`, `joe ghaleb→1`, `shawn faunce→3`, `david prompovitch→3`, `nat iyer→3`, `tapan rath→3`, `gyvonda mccain→2`, `mary raguso→2`. **Keep this exact shape** — value = required office days. No dict, no customer-site note (Aashti stays `2`; 2 office days = Met).

New shared constant `IN_OFFICE_REQUIRED_DAYS = 3` in `holiday_calendar.py`, imported by both files. De-duplicate the schedule dict into ONE place imported by both files (today it's copied in each).

---

## Display changes by surface

New columns: **`Required`** and **`Status`** (Status = `present/required` + Met/Not Met glyph). Color/RAG keys off Status.

| Surface | File:line (from code map) | Change |
|---|---|---|
| Excel `_NUM_COLS` / `col_widths` / sheet cols | weekly_report.py 965, 1062-1069, 1080, 1108-1110 | add `Required` (num), `Status` (text) cols |
| Excel color bands | weekly_report.py 993-998, 1047-1052 | drive fill off Status (Met=green, Not Met=amber/red, zero=red) instead of `<60`/`<100` |
| HTML table headers + rows | weekly_report.py 1188-1214 | add `Required` + `Status` cells; badge follows Status |
| HTML stat cards | weekly_report.py 1310-1323 | "At Risk (<60%)" → "Not Met requirement"; count = `Status==Not Met` |
| HTML manager accordion | weekly_report.py 1270-1278 | risk-pill count → `Status==Not Met` |
| HTML report-meta | weekly_report.py 1394 | add holiday note when week has a holiday |
| Email summary | weekly_report.py 1509-1525 | "At risk (<60%)" → "Not Met requirement" |
| Teams card facts | weekly_report.py 1603-1610 | same relabel |
| Streamlit metrics / tables / cards / charts | attendance_app.py 680-685, 814-825, 870-908, 939-952, 827-829/913, 973-978, 219 | add `Required`+`Status`; color (688-699) keys off Status |
| **`test_report_format.py` (SECOND COPY of renderer)** | 34-43, 46-76, 182-198, 497-613, 529, 607-612 | mirror EVERY change here or tests go false-green |

## Cleanups to do in the same pass
- **Streamlit manager-card label bug:** labels say "On Track (≥80%) / At Risk (50–79%) / Critical (<50%)" but the counts use 60/40 ([attendance_app.py:895-897](../../attendance_app.py#L895-L897) vs 865-867). Replace with Met/Not Met framing so all six surfaces finally agree.
- Optional: remove now-orphaned `count_weekdays` (dead since the holiday fix).

---

## Tests
- ADD: Met/Not Met logic — present≥required→Met; present<required→Not Met; honest % unchanged.
- ADD: special-schedule person shows honest % + Met (Joe 1/1 → 20% Met; Aashti 2/2 → 40% Met).
- ADD: required-3 person at 2 days → Not Met (the case that flat `<60%` used to miss at 66.7% under the old plan — here it's `2<3` = Not Met, correct).
- UPDATE: `test_holiday_denominator.py` — required uses holiday-adjusted week as ceiling.
- UPDATE: `test_report_format.py` embedded renderer — new headers/cols/badges.
- Parity test: registry + `IN_OFFICE_REQUIRED_DAYS` identical across both modules.

---

## Out of scope (explicitly NOT building)
No PTO / comp-time / "Excused" mechanism, and no reason-capture. The report's job is the `Met` / `Not Met` fact for everyone under one rule; the manager explains any `Not Met` in the Teams channel.

---

## Open items before build
1. Confirm the active-row override loop location (verify-first note above) — the model rides on it.
2. Column wording: `Required` + `Status`? (Status cell shows e.g. `1/1 ✅ Met` or `2/3 ⚠️ Not Met`.)
