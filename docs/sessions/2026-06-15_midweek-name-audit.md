# Session — Mid-week DataWatch Name Audit

**Date:** 2026-06-15 (Mon) · ~1.5h · Repo: `ITSupportTechsur/attendance-tracker` (main)

## Trigger
Amit Yadav (owner) reviewed the weekly attendance report in Teams and flagged
"fat fingering" + asked "what is your process to ensure data quality?". Examples
he saw: `Spare Mitchel Office`, `Omi Davis` (Unknown/Not Mapped), `Arhun Kesiraju`,
and `Jim Rader` + `James Rader` shown as two rows under the same manager.

## Root-cause answers (for the record)
- **Names come 100% from the D3000/DataWatch badge log** (First+Last stamped on each
  swipe at swipe time; DataWatch does NOT rewrite history → renamed cards keep old
  swipes). Not from AD / Hardware list — those only supply the Manager column.
- **Spare Mitchel Office** = a spare fob (Mitchell lost his, got a temp one labeled
  "spare" to recall later). The junk-word filter (`spare/lost/inventory/handy`) only
  runs in the zero-attendance path, so a spare with ≥1 swipe leaks into the report.
- **Omi Davis** = offboarded last week but still in the system that week → "Unknown /
  Not Mapped" (name matched NO AD record), drops off next week.
- **Jim vs James Rader** = same person; `difflib(jim rader, james rader)=0.80`, just
  under the 0.82 day-count merge cutoff, so they stay two rows. Manager is right on
  both because `_merge_managers` has a last-name+first-initial fallback the day-count
  merge deliberately omits. → the asymmetry: right manager, split days.

## What was built
A **mid-week name-audit** that emails the operator the names to fix in DataWatch
before the week ends (Amit's "build a system so this won't happen").

Starting state: report auto-maps typos to the right manager but nothing tells the
operator to fix the SOURCE; only a Monday pre-flight (split-spellings only) existed.

Ending state: Thursday mid-week audit emails joe.ghaleb 4 buckets of names to fix.

### Files
- `weekly_report.py` — `get_current_week_range()`, `collect_name_audit()` (buckets:
  typos / splits / unmapped / junk_active), `send_name_audit_email()`, `NAME_AUDIT`
  branch in `main()` (returns before report/upload/Teams; mirrors PREFLIGHT).
- `.github/workflows/name-audit.yml` — `cron 0 13 * * 4` (Thu) + workflow_dispatch.
- `test_name_audit.py` — 4 regression tests (all green; canonical-merge tests still pass).

### Key finding (AD↔Hardware reconciliation, run live via `az rest` Graph)
- 522 AD users (10 disabled) × 77 DataWatch cards in the SharePoint Hardware Asset
  Library → **Hardware list is clean**: 0 spelling-diffs, 0 splits, 0 dup cards,
  0 offboarded, 0 no-manager. Only housekeeping (15 "will be deleted after audit",
  9 junk/guest, 1 blank, 1 real-not-in-AD `Aaniya Yadav`).
- **Therefore the typos live in D3000, not SharePoint** → the audit must read the
  badge log (Playwright/GitHub Actions), which is what it does.

## Deploy / verification
- PR #1 squash-merged to `main` → commit `be72ef4`.
- Live `workflow_dispatch` run `27578003700` SUCCEEDED in 1m14s end-to-end:
  D3000 login → badge log (137 rows) → 508 AD users + 59 SP assignees →
  `Name-audit emailed to ***: 1 item(s) (typos=0 splits=0 unmapped=1 junk=0)`.
  (Monday = only today's swipes; real value Thursday with Mon–Wed.)

## Costs / dependencies
- No new paid resources yet. GitHub Actions minutes only (~1.5 min/run).
- `az` CLI is logged into tenant `08f2f4ef…`, sub `3cc05f3f…` — delegated Graph
  token reads Users + the ITSupportOperations SharePoint site (used for the
  local reconciliation; the workflow uses the app's client-credential token).

## Memories updated
- `project_attendance_tracker.md` — added "## Mid-week Name Audit (added 2026-06-15)".

## How to resume
```bash
cd /Users/yousseffrangieh/Desktop/VCode/Attendance-Tracker
git checkout main && git pull --ff-only        # has be72ef4
# run the test suite (needs pandas/openpyxl/msal/playwright):
python3 -m venv /tmp/atv && /tmp/atv/bin/pip install -q pandas openpyxl msal requests playwright
/tmp/atv/bin/python test_name_audit.py
# manual audit run (emails joe.ghaleb this week's findings):
gh workflow run name-audit.yml --ref main
gh run watch $(gh run list --workflow=name-audit.yml -L1 --json databaseId -q '.[0].databaseId') --exit-status
# direct one-off to your own gmail instead of Joe:
gh workflow run name-audit.yml --ref main -f alert_email=ysfrangieh120@gmail.com
# local AD↔Hardware reconciliation (no creds; uses az login):
python3 /tmp/audit_pull.py && python3 /tmp/audit_reconcile.py
```

## Addendum — 3-Source Name Audit (DataWatch ↔ Hardware ↔ Azure AD)
Owner asked to be notified whenever a name is in DataWatch and/or the Hardware list but
doesn't reconcile across all three systems. Built:
- `fetch_datawatch_cardholders()` — scrapes the FULL D3000 cardholder roster
  (`/CardHolder/Index`: tenant=Techsur `de9a0850-…`, PageSize 500, Search `#submit`).
  Reverse-engineered via a throwaway `ROSTER_PROBE` (now removed). ~122 cardholders.
  Cols: Tenant·S/C·Embossed(card#)·First·Last·AL1-5·Valid Thru·Modified.
- `collect_source_audit()` → buckets `not_in_ad` / `in_dw_not_hardware` /
  `in_hardware_not_dw` (key-based, junk/placeholder skipped). `send_source_audit_email()`.
  `SOURCE_AUDIT` mode + `.github/workflows/source-audit.yml` (Thu 13:30 UTC + dispatch).
- `test_source_audit.py` (3 tests, green).
- **Verified live:** run `27581170105` → 508 AD / 59 HW / 122 DW → emailed joe.ghaleb
  **18 items (not_in_ad=3, dw_not_hw=14, hw_not_dw=1)**. The 122-vs-59 gap is real;
  expect a Hardware-list reconciliation pass.
- `_d3000_login()` extracted; `download_badge_excel` left untouched.
- **Bluetooth refinement (2026-06-16):** mobile/HID credentials (site codes 1205/1212)
  have no physical card to inventory. `MOBILE_SITECODES` + roster site codes →
  `in_dw_not_hardware` only flags physical-card holders. Live (run 27619521614):
  62 mobile / 59 physical → buckets `not_in_ad=2, dw_not_hw=0, hw_not_dw=0` (the 14
  prior "gaps" were all Bluetooth-only). Tuning dispatches go to ysfrangieh120@gmail.com.
- **Mistake-proofing (2026-06-16):** site-code rule is conservative + self-surfacing.
  `KNOWN_PHYSICAL_SITECODES={264,272,273,274,278}` + `MOBILE_SITECODES={1205,1212}`; an
  unknown code is treated as physical (never silently skip a real gap) AND surfaced in
  the email as "🆕 Unrecognized site code — classify". Verified: all 7 codes known →
  `unknown_sitecodes={}`. test_source_audit.py now 7 tests.

## What's NEXT (prioritized)
0. ~~**Azure Logic App `attendance-nameaudit-scheduler`** for guaranteed Thursday
   firing~~ **DONE & verified 2026-06-15.** 3rd scheduler in rg-attendance-tracker
   (eastus, Consumption, Enabled): Recurrence Thu 13:00 UTC → POST `name-audit.yml/dispatches`
   `{"ref":"main"}`, same GitHub PAT. Enabling fired one immediate run (Logic App run
   21:43:24 Succeeded → GitHub run `27578365254` Succeeded → emailed joe.ghaleb). Gotcha:
   `--definition @file` needs the file wrapped `{"definition": <body>}` and the read-only
   `evaluatedRecurrence` stripped. Nov: bump all 3 Logic Apps +1h for EST.
1. **Fix the junk-fob leak** (separate from this): apply `_is_junk_badge_name` at the
   MAIN exclude step too (`weekly_report.py:635`, `attendance_app.py:505`), not just the
   zero-attendance path, so spares with activity (Spare Mitchel Office) stop leaking.
3. **Tighten the day-count merge** so nicknames like Jim→James (0.80) collapse into
   one row — fold a non-AD spelling into an exact-AD name on last-name+first-initial,
   guarding owner + in-AD names (Aaniya stays separate). Optional; manager is already right.
4. **Source corrections in DataWatch** (durable fix): rename the misspelled cardholders
   and consolidate duplicate cards (e.g. the two `James Rader` cards 36977 + 34160).
5. In **November**, bump all 3 Logic Apps' recurrence +1h for the EST shift.
