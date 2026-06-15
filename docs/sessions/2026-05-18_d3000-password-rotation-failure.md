# 2026-05-18 — D3000 forced password rotation broke weekly report

**Duration:** ~30 min
**Repo touched:** `ITSupportTechsur/attendance-tracker` (main branch)
**Production impact:** This week's Monday report (2026-05-11 → 2026-05-15) didn't go out at 14:00 UTC. Recovered via manual re-run at ~14:18 UTC.

---

## Starting state

- Monday automated run `26038315833` FAILED at 14:01 UTC.
- No one was notified — failures were silent.
- 21 resource managers expecting a Monday report did not receive one.

## Ending state

- Monday's report re-ran successfully (`26039378487`, 1m22s).
- `DATAWATCH_PASSWORD` GitHub secret rotated to new value.
- Code now sends a failure-alert email to Joe.Ghaleb@techsur.solutions on any crash (commit `bd15db2`).
- Memory updated with Bug 11 + recovery procedure.

---

## Root cause

D3000 (Datawatch DirectAccess) force-rotated the `A.Admin5` service account password.

The Playwright login flow succeeded (username + password accepted), but D3000 redirected to `/Account/ForceChangePassword` instead of the History page. The script then sat for 60s waiting for the "Search By Tenant" button before timing out:

```
After login URL: '.../Account/ForceChangePassword'
playwright._impl._errors.TimeoutError: Page.click: Timeout 60000ms exceeded.
  - waiting for locator("input[value='Search By Tenant'], ...")
```

(See [weekly_report.py:310](../../weekly_report.py#L310) for the click that timed out.)

---

## Changes shipped

### 1. Rotated `DATAWATCH_PASSWORD` GitHub secret
```bash
printf '%s' '<new-password>' | gh secret set DATAWATCH_PASSWORD --repo ITSupportTechsur/attendance-tracker
```
Verified new timestamp `2026-05-18T14:16:49Z`.

### 2. Re-ran this week's report manually
```bash
gh workflow run "Weekly Attendance Report" --repo ITSupportTechsur/attendance-tracker
```
Run `26039378487` completed in 1m22s ✓. 21 managers received the email + Teams card.

### 3. Added `send_failure_alert()` to `weekly_report.py` (commit `bd15db2`)
- Catches any exception from `main()`, emails `ALERT_EMAIL` (defaults to `REPORT_FROM_EMAIL`) with the traceback, re-raises so the GitHub Actions step still fails red.
- Special-cases `ForceChangePassword` in the traceback → prepends a "Likely cause: D3000 forced rotation, update DATAWATCH_PASSWORD" hint.
- Best-effort: alert-send failures are swallowed and logged, never block the re-raise.
- Pushed to `main` — auto-deploy of Streamlit app ran (no functional change, just refresh).

### 4. Updated project memory (Bug 11)
Added recovery procedure to `project_attendance_tracker.md` so future sessions diagnose this in seconds.

---

## Bugs found + fixes

| # | Bug | Fix |
|---|---|---|
| 11 | D3000 force-rotated A.Admin5 password → 60s Playwright timeout | Rotate `DATAWATCH_PASSWORD` secret + added `send_failure_alert()` for diagnostics |

---

## Costs / external dependencies touched

- No new infrastructure; no cost change.
- Microsoft Graph `Mail.Send` permission already provisioned (used by `send_email_report`); the alert path reuses it.
- New (optional) env var `ALERT_EMAIL` — currently unset, falls back to `REPORT_FROM_EMAIL` (Joe.Ghaleb@techsur.solutions).

---

## Auth / credential notes

- The new D3000 password was pasted into the chat transcript by the user. **Recommend rotating it again with IT** since the transcript is logged.
- The secret itself lives in GitHub Actions secrets, not in any file in this repo or in Claude memory.
- D3000 password rotation cadence is **unknown** — ask IT (Datawatch admin) so we can rotate the secret proactively before the next forced expiry.

---

## Memories updated

- `project_attendance_tracker.md` — added Bug 11 (D3000 forced rotation + recovery procedure + new failure-alert mechanism)

---

## How to resume

If this issue recurs (D3000 force-rotates again):

1. Get the new password from IT.
2. Update the GitHub secret:
   ```bash
   cd /Users/yousseffrangieh/Desktop/VCode/Attendance-Tracker
   printf '%s' '<new-password>' | gh secret set DATAWATCH_PASSWORD --repo ITSupportTechsur/attendance-tracker
   ```
3. Re-run the failed workflow:
   ```bash
   gh workflow run "Weekly Attendance Report" --repo ITSupportTechsur/attendance-tracker
   gh run watch --repo ITSupportTechsur/attendance-tracker
   ```
4. Verify a green run in `gh run list --workflow="Weekly Attendance Report"`.

For any *other* failure: you'll get an email at Joe.Ghaleb@techsur.solutions with subject `❌ Weekly Attendance Report FAILED` and the full traceback. The hint section flags `ForceChangePassword`-class failures automatically.

---

## What's NEXT

1. **Rotate the D3000 password again** with IT — current value was pasted into chat (highest priority).
2. **Ask IT for D3000 password rotation interval** so the secret can be rotated proactively before forced expiry.
3. **Optional:** add a similar failure-alert for `deploy-azure.yml` (Streamlit deploy) — currently it can fail silently too.
4. **Optional (non-urgent, before 2026-09-16):** bump `actions/checkout@v4` and `actions/setup-python@v5` to Node 24-compatible versions (deprecation warning seen in today's run).
