# Session digest — Met/Not Met compliance model (built + deployed)

**Date:** 2026-06-29 · **Repo:** `ITSupportTechsur/attendance-tracker` (local: `~/Desktop/VCode/Attendance-Tracker`)
**Outcome:** Designed → built → tested → reviewed → merged → **deployed live**.

---

## Why this session happened
A TechSur Teams thread (Resource Managers) surfaced confusion about the attendance report:
- **Pankaj Shishodia:** "Total Weekdays" varies per person; 3-of-3 showing as 60% doesn't reflect the hybrid policy — should the denominator be the in-office requirement?
- **Kumud Trikha (authoritative answer):** expectation is **a minimum of 60% in-office attendance**; some staff do **2 days office + 1 day customer site**; **holidays falling on an in-office day are NOT made up**.
- **Marina Fox:** some staff took offset/comp days for FAA weekend release work.

Owner asked how to enhance the report to reflect this.

## Starting state
- `main` @ `82af22a` (federal-holiday denominator already live — acts as the ceiling here).
- Report had a single **Attendance %** (Days Present ÷ expected_business_days) as the ONLY signal; `CUSTOM_SCHEDULES` **overrode the denominator** so 1-day people (Joe) showed ~100%.
- Tests: **37 passing**. Streamlit manager cards had a label bug (labels said 80/50, code counted 60/40).

## Ending state
- `main` @ `9487f3f` — **MERGED (fast-forward) + DEPLOYED** (Azure run `28391128774` success; live HTTP 200).
- Tests: **46 passing**.
- First automated report on the new model: **Mon Jul 6** (covers Jun 29 – Jul 3).

---

## Decisions made (via owner Q&A) + rationale
1. **Honest % + separate Met/Not Met status** — chosen over "redefine 3 days = 100%". Keeps the % meaning what it always did (no history reset, no at-risk-threshold surgery), matches Kumud's "minimum 60%" wording, and the green **Met** badge gives Pankaj the "they hit it" clarity.
2. **Removed the per-person denominator override** — `Attendance %` is now the SAME honest formula for everyone. Joe (req 1, present 1) reads **20% ✅ Met**, not a fake 100%.
3. **"Excluded/special cases" = the CUSTOM_SCHEDULES people** (Joe, Aashti, etc.), NOT the hard-excludes (guests/contractors/junk/non-AD). They get %+Met like everyone.
4. **No customer-site modelling** — report shows ONLY real office badge data. Aashti is simply Required=2; the 3rd day isn't in our data, so it's never shown/credited/annotated.
5. **No PTO/comp-time/exception mechanism** — out of scope. Managers explain any Not Met in the Teams channel.
6. **`Required` column hidden** (late owner tweak) — computed internally (drives Status), not displayed on any surface.
7. **Met renders as a GREEN badge** (owner confirmed after seeing a plain-text mockup).

## Rule (now live)
```
Required     = min(CUSTOM_SCHEDULES.get(name, IN_OFFICE_REQUIRED_DAYS=3), expected_business_days)  # internal only
Attendance % = Days Present / expected_business_days, capped 100        # honest, same for everyone
Status       = "Met" if Days Present >= Required else "Not Met"
Days Absent  = max(0, Required - Days Present)
```
`CUSTOM_SCHEDULES` (unchanged values): aashti 2, joe 1, shawn 3, david 3, nat 3, tapan 3, gyvonda 2, mary 2.

## File-change summary (commit `9487f3f`, 8 files)
- `holiday_calendar.py` — new shared `IN_OFFICE_REQUIRED_DAYS = 3`.
- `weekly_report.py` — scoring (Required+Status, active + zero rows); Excel/_HTML/email/Teams re-pointed at-risk→`Status=="Not Met"`; Status-driven RAG colour; HTML legend + holiday note; Required NOT displayed.
- `attendance_app.py` — same scoring; `style_by_status` (Styler.apply axis=1) replaces `color_pct`; metrics/tables/individual-lookup updated; manager-card label bug fixed (now Met/Not Met counts); Required hidden; dead `color_pct` removed.
- `test_report_format.py` — preview renderer mirrored; **module-level run guarded by `if __name__=="__main__"`** (was generating+opening files on pytest import).
- `test_holiday_denominator.py` — 3 tests rewritten for the new model.
- `test_compliance_status.py` — NEW: normal 5-day week, 20%-but-Met, customer-site, zero-attendance, cross-module CUSTOM_SCHEDULES parity.
- `docs/plans/2026-06-29_hybrid-compliance-status-model.md` — authoritative spec; `2026-06-23_in-office-requirement-3day.md` marked SUPERSEDED.

## Verification
- `pytest` (in `.venv-test`): **46 passed**.
- Production Excel + HTML smoke-tested; live HTTP 200 post-deploy.
- **Adversarial review workflow** (3 dims × verify): scoring + production surfaces clean; only **2 preview-only findings** (sample Days Absent inconsistency + missing legend) — both fixed. The zero-attendance "separate-frame" concerns were correctly dismissed as intentional pre-existing architecture.

## Costs / deps
- No new external cost. Still ~$13/mo Azure B1. `holidays` lib already present (prior session). No new licenses.

## Memories updated
- `in_office_requirement_plan.md` → MERGED + DEPLOYED status, final decisions (Required hidden, green Met, no customer-site).
- `MEMORY.md` index line updated.

---

## How to resume
```bash
cd ~/Desktop/VCode/Attendance-Tracker
git checkout main && git pull           # main @ 9487f3f (or later)
.venv-test/bin/python -m pytest -q      # expect 46 passed
# Preview the report locally:
.venv-test/bin/python test_report_format.py     # writes + opens sample_report.html/.xlsx
# Live app: https://techsur-attendance-tracker.azurewebsites.net  (expect HTTP 200)
```
Per-person requirement lives in `CUSTOM_SCHEDULES` (top of BOTH `weekly_report.py` and `attendance_app.py` — keep in sync; `test_compliance_status.py` guards parity). Company default = `IN_OFFICE_REQUIRED_DAYS` in `holiday_calendar.py`.

## What's NEXT
1. **Send the Teams message** to Resource Managers (drafted this session — "Status ✅ Met / ⚠️ Not Met" version). Manual paste; the bot can't post.
2. **Watch the Jul 6 automated run** — first report on the new model AND a holiday week (Jul 3 observed). Confirm Status renders and the holiday note appears.
3. If a manager reports an approved schedule (e.g. someone should be 2 days), add them to `CUSTOM_SCHEDULES` in both files + a parity test stays green.
4. (Deferred, not built) per-week PTO/comp-time "Excused" mechanism — only if the owner reverses the "managers handle it in channel" decision.

## Auth / infra notes (no secrets)
- `git push` authenticated fine over HTTPS (token in credential store). `gh auth status` showed "Active account: false" but `gh run list/view/watch` still worked.
- Azure deploy can flake on a cold-start "site failed to start" timeout (seen in prior sessions) → `gh run rerun <id>`. This run passed first try.
- In **November**, bump all four Azure Logic App schedulers +1h for the EST shift (see `project_attendance_tracker.md`).
