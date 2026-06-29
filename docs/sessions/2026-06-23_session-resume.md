# Session resume — holiday denom (shipped) + in-office requirement (planned)

**Dates:** 2026-06-22 → 2026-06-23 · **Repo:** Attendance-Tracker only.

## TL;DR — three threads
1. **Federal-holiday denominator** — ✅ BUILT, MERGED, DEPLOYED.
2. **Teams heads-up to resource managers** — ✏️ DRAFTED, owner to post (their call: "I'll paste it myself"). Not yet confirmed posted.
3. **In-office 3-day requirement** — 📋 PLANNED ONLY, awaiting 4 owner decisions + go-ahead.

---

## 1. Federal-holiday denominator (DONE)
A week with an observed U.S. federal holiday is scored out of (weekdays − holidays), not a flat 5.
- New `holiday_calendar.py` (wraps `holidays==0.99`, observed-aware), imported by both `weekly_report.py` + `attendance_app.py`.
- Merged: **PR #3 → `main` (`82af22a`)**. Azure deploy succeeded on re-run (first attempt = flaky "site failed to start" cold-start timeout, NOT code; `gh run rerun` fixes it every time). App live HTTP 200.
- All 11 federal holidays (HR-confirmed incl. Columbus + Veterans); Black Friday NOT counted. Going-forward only — today's Jun 15–19 report already shipped at denom 5 (Juneteenth preserved). **First holiday-adjusted report = Mon Jul 6** (Jun 29–Jul 3, observed Independence Day Fri Jul 3).
- Tests: 37 pass (`test_holiday_calendar.py`, `test_holiday_denominator.py` + existing).
- Detail: `docs/sessions/2026-06-22_federal-holiday-denominator.md`.

## 2. Teams announcement (owner to post)
Draft message ready (in the conversation) announcing the holiday change to the 21 resource managers. Webhook (`TEAMS_CHAT_WEBHOOK_URL`) is a GitHub secret, not available locally, so owner posts it manually into the "TechSur @ Resource Managers" chat. **Send before Jul 6.**

## 3. In-office 3-day requirement (PLANNED — NOT built)
Score attendance against a 3-day/week in-office requirement: "3 of 3 = 100%."
- **Full plan:** `docs/plans/2026-06-23_in-office-requirement-3day.md`. **Memory:** `in_office_requirement_plan.md`.
- **Locked:** 3 days/week default · cap 100% · keep CUSTOM_SCHEDULES as overrides.
- **Small logic** (default denom → `min(3, total_weekdays)`; custom loops unchanged). **Big part = relabeling** HTML/Excel/email/Teams/Streamlit ("Total Weekdays"→"Required"; "Working days"→"Expected business days").
- **Critic blockers:** `test_report_format.py` is a 2nd copy of the renderer (mirror all labels); at-risk `<60%` band now under-flags (2-of-3=66.7% > 60%); pre-existing Streamlit label/threshold mismatch (app:895-897 say 80/50, code uses 60/40).
- **4 decisions BLOCKING execution:** (1) column wording; (2) move at-risk threshold?; (3) hardcode 3 vs env var; (4) add "In-office requirement: 3 days/week" to email/Teams?

---

## How to resume
```bash
cd /Users/yousseffrangieh/Desktop/VCode/Attendance-Tracker
git checkout main && git pull          # has the holiday change (82af22a)
# venv for tests (homebrew python lacks pandas/pytest):
python3 -m venv .venv-test && .venv-test/bin/pip install -r requirements.txt pytest holidays
.venv-test/bin/python -m pytest -q     # 37 pass
# read the pending plan:
cat docs/plans/2026-06-23_in-office-requirement-3day.md
```
- **gh CLI active account is `ITSupportTechsur`** (TechSur) — I switched it from `TechAiSol` to push/merge; switch back with `gh auth switch --user TechAiSol` if desired. Only `ITSupportTechsur` has push rights to the repo.

## What's NEXT (priority)
1. **Owner answers the 4 in-office-requirement decisions** → then execute that plan on a branch (same flow: branch → tests → PR → merge → re-run deploy if it flakes).
2. **Owner posts the Teams heads-up** to managers before Jul 6.
3. (Standing) **November EST shift** — bump all FOUR Azure Logic Apps +1h.
