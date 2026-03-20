"""
Weekly Attendance Automation
============================
Runs every Monday via GitHub Actions.
  1. Logs into D3000 Express (Datawatch DirectAccess) via browser automation
  2. Downloads the previous week's (Mon–Fri) badge-access Excel export
  3. Processes attendance using the same logic as attendance_app.py
  4. Generates the full multi-sheet Excel report
  5. Uploads the report to SharePoint IT Support Operations
  6. Posts a summary message + file link to the Teams "TechSur @ Resource Managers" group chat

Required environment variables (set as GitHub Secrets):
  DATAWATCH_USERNAME   e.g. A.Admin5
  DATAWATCH_PASSWORD
  AZURE_TENANT_ID
  AZURE_CLIENT_ID
  AZURE_CLIENT_SECRET
  TEAMS_CHAT_ID        (see README section below for how to find this)
"""

import os
import io
import re
import sys
import difflib
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import msal
import requests as http_requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

OFFICE_ADDRESS      = "11190 Sunrise Valley Drive"
TECHSUR_TENANT      = "Techsur Solutions"
DATAWATCH_BASE_URL  = "https://d3000express.azurewebsites.net"

DATAWATCH_USERNAME  = os.environ["DATAWATCH_USERNAME"]
DATAWATCH_PASSWORD  = os.environ["DATAWATCH_PASSWORD"]
AZURE_TENANT_ID     = os.environ["AZURE_TENANT_ID"]
AZURE_CLIENT_ID     = os.environ["AZURE_CLIENT_ID"]
AZURE_CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
TEAMS_CHAT_ID       = os.environ["TEAMS_CHAT_ID"]

SHAREPOINT_SITE_PATH = "techsur.sharepoint.com:/sites/ITSupportOperations"
UPLOAD_FOLDER        = "Attendance Reports"   # folder inside site's document library

DEFAULT_EXCLUDE_NAMES = {
    "chief engineer master",
    "contractor shred it",
    "harvard 2",
    "guest fob 1",
    "guest fob 2",
    "ramona shannon harvard maintenance",
    "cristian mata",
    "bravo handy man",
}

_BADGE_JUNK_WORDS = {"lost", "spare", "inventory", "handy"}
_ISO_DATE_RE      = re.compile(r"^\d{4}-\d{2}-\d{2}T")

# Date format used by D3000 (e.g. 3/17/2026)
_DATE_FMT = "%#m/%#d/%Y" if sys.platform == "win32" else "%-m/%-d/%Y"


# ── Date helpers ───────────────────────────────────────────────────────────────

def get_last_week_range():
    """Return (last_monday, last_friday) as date objects."""
    today       = date.today()          # This script runs on Monday
    last_monday = today - timedelta(days=7)
    last_friday = last_monday + timedelta(days=4)
    return last_monday, last_friday


def count_weekdays(start: date, end: date) -> int:
    return sum(
        1 for n in range((end - start).days + 1)
        if (start + timedelta(n)).weekday() < 5
    )


# ── Name normalisation (mirrors attendance_app.py) ────────────────────────────

def _name_key(name: str) -> str:
    tokens  = str(name).strip().lower().split()
    filtered = [t for t in tokens if len(t) > 1 and not t.isdigit()]
    deduped  = [filtered[i] for i in range(len(filtered))
                if i == 0 or filtered[i] != filtered[i - 1]]
    if len(deduped) >= 2:
        return deduped[0] + " " + deduped[-1]
    return " ".join(deduped) if deduped else name.strip().lower()


def _is_junk_badge_name(name: str) -> bool:
    return any(t in _BADGE_JUNK_WORDS for t in name.lower().split())


def _last_first_initial_match(k: str, candidates: list) -> str | None:
    parts_k = k.split()
    if len(parts_k) < 2:
        return None
    for c in candidates:
        parts_c = c.split()
        if (len(parts_c) >= 2
                and parts_k[-1] == parts_c[-1]
                and parts_k[0][0] == parts_c[0][0]):
            return c
    return None


# ── Step 1: Download badge Excel from D3000 ───────────────────────────────────

def download_badge_excel(start: date, end: date) -> bytes:
    """Use Playwright (headless Chromium) to log in and export the History Excel."""
    log.info(f"Downloading D3000 badge log  {start} → {end}")
    start_str = start.strftime(_DATE_FMT)
    end_str   = end.strftime(_DATE_FMT)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx     = browser.new_context(accept_downloads=True)
        page    = ctx.new_page()
        page.set_default_timeout(60_000)   # 60 s for all actions

        try:
            # ── Login step 1: load page and enter username ────────────────────
            log.info(f"Navigating to {DATAWATCH_BASE_URL}")
            page.goto(DATAWATCH_BASE_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2000)   # let JS render the form

            log.info(f"Page title: {page.title()!r}  URL: {page.url!r}")

            # Try multiple selector patterns for the username field
            username_selector = (
                "input#UserName, "
                "input[name='UserName'], "
                "input[name='username'], "
                "input[type='text']"
            )
            page.wait_for_selector(username_selector, timeout=30_000)
            page.fill(username_selector, DATAWATCH_USERNAME)
            log.info("Username entered")

            # Click Next — try value attr or visible button text
            page.click(
                "input[value='Next'], "
                "button:has-text('Next'), "
                "input[type='submit']"
            )
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1500)

            # ── Login step 2: enter password ──────────────────────────────────
            log.info(f"Password page URL: {page.url!r}")
            page.wait_for_selector("input[name='Password'], input[type='password']", timeout=30_000)
            page.fill("input[name='Password'], input[type='password']", DATAWATCH_PASSWORD)
            page.click(
                "input[value='Log On'], "
                "button:has-text('Log On'), "
                "input[type='submit']"
            )
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            log.info(f"After login URL: {page.url!r}")

        except Exception as exc:
            # Save a screenshot so we can see what the browser saw
            page.screenshot(path="/tmp/d3000_login_debug.png", full_page=True)
            log.error(f"Login failed — screenshot saved to /tmp/d3000_login_debug.png")
            raise RuntimeError(f"D3000 login failed: {exc}") from exc

        log.info("Logged in to D3000 DirectAccess")

        # ── Navigate to History ───────────────────────────────────────────────
        page.goto(f"{DATAWATCH_BASE_URL}/History/Index", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Debug: log all input fields visible on the page
        inputs = page.evaluate("""
            () => Array.from(document.querySelectorAll('input')).map(
                el => ({id: el.id, name: el.name, type: el.type, value: el.value})
            )
        """)
        log.info(f"History page inputs: {inputs}")
        page.screenshot(path="/tmp/d3000_history.png", full_page=True)

        # ── Set date range via JavaScript (bypasses calendar picker) ──────────
        # Find the Begin/End inputs dynamically from what's on the page
        page.evaluate(f"""
            (function() {{
                // Try multiple strategies to find date inputs
                var inputs = document.querySelectorAll('input[type="text"], input[type="date"], input:not([type])');
                var dateInputs = Array.from(inputs).filter(function(el) {{
                    var id = (el.id || '').toLowerCase();
                    var name = (el.name || '').toLowerCase();
                    return id.includes('begin') || id.includes('start') ||
                           name.includes('begin') || name.includes('start');
                }});
                if (dateInputs.length > 0) {{
                    dateInputs[0].value = '{start_str}';
                    dateInputs[0].dispatchEvent(new Event('change', {{bubbles: true}}));
                    dateInputs[0].dispatchEvent(new Event('input', {{bubbles: true}}));
                }}

                var endInputs = Array.from(inputs).filter(function(el) {{
                    var id = (el.id || '').toLowerCase();
                    var name = (el.name || '').toLowerCase();
                    return id.includes('end') || name.includes('end');
                }});
                if (endInputs.length > 0) {{
                    endInputs[0].value = '{end_str}';
                    endInputs[0].dispatchEvent(new Event('change', {{bubbles: true}}));
                    endInputs[0].dispatchEvent(new Event('input', {{bubbles: true}}));
                }}
            }})();
        """)
        page.wait_for_timeout(1000)

        # Verify the values were set
        set_values = page.evaluate("""
            () => Array.from(document.querySelectorAll('input')).map(
                el => ({id: el.id, name: el.name, value: el.value})
            ).filter(el => el.value)
        """)
        log.info(f"Input values after JS set: {set_values}")
        log.info(f"Date range set: {start_str} → {end_str}")

        # ── Click "Search By Tenant" ──────────────────────────────────────────
        # Find the search button dynamically
        search_btn = page.evaluate("""
            () => {
                var btns = Array.from(document.querySelectorAll('input[type="submit"], button'));
                var match = btns.find(b =>
                    (b.value || b.textContent || '').toLowerCase().includes('search')
                );
                return match ? (match.value || match.textContent) : null;
            }
        """)
        log.info(f"Search button found: {search_btn!r}")

        page.click(
            "input[value='Search By Tenant'], "
            "button:has-text('Search By Tenant'), "
            "input[type='submit']"
        )
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(4000)
        log.info("Search complete — downloading Export to Excel")

        # ── Export to Excel ───────────────────────────────────────────────────
        # Find the Export to Excel link
        export_link = page.evaluate("""
            () => {
                var links = Array.from(document.querySelectorAll('a'));
                var match = links.find(a => a.textContent.toLowerCase().includes('export to excel'));
                return match ? match.href : null;
            }
        """)
        log.info(f"Export link found: {export_link!r}")

        with page.expect_download(timeout=60_000) as dl_info:
            page.click("a:has-text('Export to Excel')")
        download = dl_info.value
        file_path = download.path()
        data = Path(file_path).read_bytes()
        browser.close()

    log.info(f"Downloaded badge log  ({len(data):,} bytes)")
    return data


# ── Step 2: Get Microsoft Graph token ─────────────────────────────────────────

def get_graph_token() -> str:
    app = msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        client_credential=AZURE_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        raise RuntimeError(f"MSAL token error: {result.get('error_description')}")
    return result["access_token"]


# ── Step 3: Fetch Azure AD users + managers ───────────────────────────────────

def fetch_manager_df(token: str) -> pd.DataFrame:
    headers = {"Authorization": f"Bearer {token}"}
    url = (
        "https://graph.microsoft.com/v1.0/users"
        "?$select=displayName,mail"
        "&$expand=manager($select=displayName,mail)"
        "&$top=999"
    )
    users = []
    while url:
        resp = http_requests.get(url, headers=headers)
        data = resp.json()
        if "error" in data:
            log.warning(f"Graph users error: {data['error']}")
            break
        users.extend(data.get("value", []))
        url = data.get("@odata.nextLink")

    rows = []
    for u in users:
        mgr = u.get("manager")
        rows.append({
            "Employee":      u.get("displayName", ""),
            "Manager":       mgr.get("displayName", "No Manager") if mgr else "No Manager",
            "Manager Email": mgr.get("mail", "") if mgr else "",
        })
    mgr_df = pd.DataFrame(rows)

    if not mgr_df.empty:
        mgr_df["_key"]     = mgr_df["Employee"].apply(_name_key)
        mgr_df["_has_mgr"] = mgr_df["Manager"].apply(
            lambda m: 0 if m not in ("No Manager", "") else 1
        )
        mgr_df = (
            mgr_df.sort_values("_has_mgr")
                  .drop_duplicates(subset=["_key"], keep="first")
                  .drop(columns=["_key", "_has_mgr"])
        )

    log.info(f"Fetched {len(mgr_df)} Azure AD users")
    return mgr_df


# ── Step 4: Fetch SharePoint site ID + DataWatch assignees ────────────────────

def get_sharepoint_site_id(token: str) -> str | None:
    """Resolve the SharePoint site path to a stable site ID."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = http_requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_SITE_PATH}",
        headers=headers,
    )
    data = resp.json()
    if "error" in data:
        log.warning(f"SharePoint site error: {data['error']}")
        return None
    return data["id"]


def fetch_datawatch_names(token: str, site_id: str) -> set:
    headers = {"Authorization": f"Bearer {token}"}

    lists_resp = http_requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists",
        headers=headers,
    )
    all_lists = lists_resp.json().get("value", [])
    list_id   = next(
        (l["id"] for l in all_lists if "hardware asset" in l.get("displayName", "").lower()),
        None,
    )
    if not list_id:
        log.warning("Hardware Asset Library not found in SharePoint — skipping 0-attendance check")
        return set()

    sp_url   = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        f"/lists/{list_id}/items?$expand=fields&$top=999"
    )
    sp_items = []
    while sp_url:
        sp_resp = http_requests.get(sp_url, headers=headers)
        sp_data = sp_resp.json()
        if "error" in sp_data:
            log.warning(f"SharePoint items error: {sp_data['error']}")
            break
        sp_items.extend(sp_data.get("value", []))
        sp_url = sp_data.get("@odata.nextLink")

    names = set()
    for item in sp_items:
        fields = item.get("fields", {})
        if not any("datawatch" in str(v).lower() for v in fields.values()):
            continue
        raw = fields.get("field_1", "")
        if isinstance(raw, str):
            raw = raw.strip()
            if raw and not _ISO_DATE_RE.match(raw):
                names.add(raw)
        elif isinstance(raw, dict):
            n = raw.get("LookupValue") or raw.get("displayName") or ""
            if n:
                names.add(n.strip())

    log.info(f"Fetched {len(names)} DataWatch assignees from SharePoint")
    return names


# ── Step 5: Process attendance data ──────────────────────────────────────────

def find_col(df: pd.DataFrame, keywords: list) -> str | None:
    for col in df.columns:
        if any(k.lower() in col.lower() for k in keywords):
            return col
    return None


def process_attendance(
    excel_bytes: bytes,
    start: date,
    end: date,
    manager_df: pd.DataFrame,
    datawatch_names: set,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """
    Returns (unique_days_df, zero_attendance_df, total_weekdays).
    Mirrors the processing logic in attendance_app.py.
    """
    df_raw = pd.read_excel(io.BytesIO(excel_bytes))
    log.info(f"Badge log loaded: {len(df_raw):,} rows, columns: {list(df_raw.columns)}")

    # Auto-detect columns
    datetime_col  = find_col(df_raw, ["date", "time", "datetime", "timestamp"])
    firstname_col = find_col(df_raw, ["first"])
    lastname_col  = find_col(df_raw, ["last"])
    address_col   = find_col(df_raw, ["address", "from", "location", "site", "building"])
    tenant_col    = find_col(df_raw, ["tenant", "organization", "organisation", "company"])

    df = df_raw.copy()
    df["_dt"]   = pd.to_datetime(df[datetime_col], errors="coerce")
    df          = df.dropna(subset=["_dt"])
    df["_date"] = df["_dt"].dt.date

    if firstname_col and lastname_col:
        df["_name"] = (
            df[firstname_col].fillna("") + " " + df[lastname_col].fillna("")
        ).str.strip()
    else:
        nc = find_col(df_raw, ["name", "employee", "person", "user"])
        df["_name"] = df[nc].fillna("").str.strip() if nc else ""

    df = df[df["_name"] != ""]

    # Address filter
    if address_col:
        df = df[df[address_col].astype(str).str.strip() == OFFICE_ADDRESS]

    # Tenant filter
    if tenant_col:
        df = df[df[tenant_col].astype(str).str.strip() == TECHSUR_TENANT]

    # Date range + weekdays only
    df = df[(df["_date"] >= start) & (df["_date"] <= end)]
    df = df[pd.to_datetime(df["_date"]).dt.dayofweek < 5]

    # Exclude default non-employee names
    df = df[~df["_name"].str.strip().str.lower().isin(DEFAULT_EXCLUDE_NAMES)]

    total_weekdays = count_weekdays(start, end)

    # Attendance per person
    unique_days = (
        df.drop_duplicates(subset=["_name", "_date"])
          .groupby("_name")["_date"]
          .count()
          .reset_index()
          .rename(columns={"_date": "Days Present"})
    )
    unique_days["Total Weekdays"] = total_weekdays
    unique_days["Attendance %"]   = (
        unique_days["Days Present"] / total_weekdays * 100
    ).round(1)
    unique_days["Days Absent"] = total_weekdays - unique_days["Days Present"]

    # Merge manager data
    if not manager_df.empty:
        mgr_lookup          = manager_df.copy()
        mgr_lookup["_key"]  = mgr_lookup["Employee"].apply(_name_key)
        unique_days["_key"] = unique_days["_name"].apply(_name_key)
        unique_days = unique_days.merge(
            mgr_lookup[["_key", "Manager", "Manager Email"]],
            on="_key", how="left",
        ).drop(columns=["_key"])
        unique_days["Manager"]       = unique_days["Manager"].fillna("Unknown / Not Mapped")
        unique_days["Manager Email"] = unique_days["Manager Email"].fillna("")

    # Zero-attendance: DataWatch holders with no badge swipes
    zero_rows = []
    if datawatch_names:
        existing_keys     = list(unique_days["_name"].apply(_name_key))
        existing_keys_set = set(existing_keys)
        for n in sorted(datawatch_names):
            if not n.strip():
                continue
            if n.strip().lower() in DEFAULT_EXCLUDE_NAMES or _is_junk_badge_name(n):
                continue
            k     = _name_key(n)
            if k in existing_keys_set:
                continue
            close = difflib.get_close_matches(k, existing_keys, n=1, cutoff=0.82)
            if not close:
                m = _last_first_initial_match(k, existing_keys)
                if m:
                    close = [m]
            if close:
                continue   # fuzzy match — person was present
            zero_rows.append({
                "_name": n, "Days Present": 0,
                "Days Absent": total_weekdays,
                "Total Weekdays": total_weekdays,
                "Attendance %": 0.0,
            })

    zero_df = pd.DataFrame(zero_rows)
    if not zero_df.empty and not manager_df.empty:
        mgr_lookup_z          = manager_df.copy()
        mgr_lookup_z["_key"]  = mgr_lookup_z["Employee"].apply(_name_key)
        zero_df["_key"]       = zero_df["_name"].apply(_name_key)
        zero_df = zero_df.merge(
            mgr_lookup_z[["_key", "Manager", "Manager Email"]],
            on="_key", how="left",
        ).drop(columns=["_key"])
        zero_df["Manager"]       = zero_df["Manager"].fillna("Unknown / Not Mapped")
        zero_df["Manager Email"] = zero_df["Manager Email"].fillna("")

    log.info(
        f"Processed: {len(unique_days)} employees, "
        f"{len(zero_df)} zero-attendance, "
        f"{total_weekdays} weekdays"
    )
    return unique_days, zero_df, total_weekdays


# ── Step 6: Generate Excel report ─────────────────────────────────────────────

def _safe_sheet_name(name: str) -> str:
    return (
        name[:31]
        .replace("/", "-").replace("\\", "-")
        .replace("*", "").replace("[", "").replace("]", "")
        .replace(":", "").replace("?", "")
    )


def _team_sheet(df_team: pd.DataFrame, writer, sheet_name: str) -> None:
    cols = ["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]
    sheet_df = (
        df_team[cols]
        .sort_values("Attendance %", ascending=True)
        .rename(columns={"_name": "Employee"})
        .reset_index(drop=True)
    )
    sheet_df.index += 1
    sheet_df.to_excel(writer, sheet_name=sheet_name, index=True, index_label="#")


def generate_report_excel(
    unique_days: pd.DataFrame,
    zero_df: pd.DataFrame,
    start: date,
    end: date,
) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        # Sheet 1 — All Employees
        cols = ["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]
        if "Manager" in unique_days.columns:
            cols += ["Manager"]
        summary = (
            unique_days[cols]
            .sort_values(
                ["Manager", "Attendance %"] if "Manager" in cols else ["Attendance %"],
                ascending=True,
            )
            .rename(columns={"_name": "Employee"})
            .reset_index(drop=True)
        )
        summary.index += 1
        summary.to_excel(writer, sheet_name="All Employees", index=True, index_label="#")

        # One sheet per manager
        if "Manager" in unique_days.columns:
            named_managers = sorted([
                m for m in unique_days["Manager"].dropna().unique()
                if m not in ("No Manager", "Unknown / Not Mapped")
            ])
            for mgr in named_managers:
                team = unique_days[unique_days["Manager"] == mgr].copy()
                if not team.empty:
                    _team_sheet(team, writer, _safe_sheet_name(mgr))

            no_mgr = unique_days[
                unique_days["Manager"].isin(["No Manager", "Unknown / Not Mapped"])
            ].copy()
            if not no_mgr.empty:
                _team_sheet(no_mgr, writer, "No Manager")

        # 0 Attendance sheet
        if not zero_df.empty:
            _team_sheet(zero_df, writer, "0 Attendance")

    log.info("Excel report generated")
    return output.getvalue()


# ── Step 7: Upload file to SharePoint ─────────────────────────────────────────

def upload_to_sharepoint(token: str, site_id: str, filename: str, file_bytes: bytes) -> str:
    """
    Uploads the report to the SharePoint site's 'Attendance Reports' folder.
    Uses the resolved site_id (GUID) so the URL is unambiguous.
    Returns the web URL of the uploaded file, or "" on failure.
    Requires Sites.ReadWrite.All on the Azure AD app.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    # Correct format: sites/{site-id}/drive/root:/{folder}/{file}:/content
    upload_url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        f"/drive/root:/{UPLOAD_FOLDER}/{filename}:/content"
    )
    resp = http_requests.put(upload_url, headers=headers, data=file_bytes)
    if resp.status_code not in (200, 201):
        log.warning(f"SharePoint upload failed ({resp.status_code}): {resp.text[:200]}")
        return ""

    web_url = resp.json().get("webUrl", "")
    log.info(f"File uploaded to SharePoint: {web_url}")
    return web_url


# ── Step 8: Post message to Teams chat ────────────────────────────────────────

def post_to_teams(
    token: str,
    chat_id: str,
    unique_days: pd.DataFrame,
    zero_df: pd.DataFrame,
    total_weekdays: int,
    start: date,
    end: date,
    file_url: str,
    filename: str,
) -> None:
    """
    Posts an HTML summary message + file link to the Teams group chat.
    Requires Chat.ReadWrite.All on the Azure AD app.
    """
    total_emp  = len(unique_days)
    avg_pct    = unique_days["Attendance %"].mean() if total_emp else 0.0
    at_risk    = int((unique_days["Attendance %"] < 80).sum())
    zero_count = len(zero_df)

    file_line = (
        f'<br/>📎 <a href="{file_url}">{filename}</a>'
        if file_url else ""
    )

    html_body = (
        f"📊 <b>Weekly Attendance Report</b> — "
        f"{start.strftime('%b %d')} to {end.strftime('%b %d, %Y')}<br/><br/>"
        f"Please find attached the attendance tracker results.<br/><br/>"
        f"• <b>Total employees tracked:</b> {total_emp}<br/>"
        f"• <b>Average attendance:</b> {avg_pct:.1f}%<br/>"
        f"• <b>At risk (&lt;80%):</b> {at_risk}<br/>"
        f"• <b>0 attendance:</b> {zero_count}<br/>"
        f"• <b>Working days in period:</b> {total_weekdays}"
        f"{file_line}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "body": {
            "contentType": "html",
            "content": html_body,
        }
    }
    # Use beta endpoint — required for app-permission posting to group chats
    resp = http_requests.post(
        f"https://graph.microsoft.com/beta/chats/{chat_id}/messages",
        headers=headers,
        json=payload,
    )
    if resp.status_code in (200, 201):
        log.info("Message posted to Teams successfully")
    else:
        raise RuntimeError(
            f"Teams post failed ({resp.status_code}): {resp.text[:300]}"
        )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    start, end = get_last_week_range()
    log.info(f"=== Weekly Attendance Report  {start} → {end} ===")

    # 1. Download badge log from D3000
    badge_excel = download_badge_excel(start, end)

    # 2. Authenticate to Microsoft Graph
    token = get_graph_token()

    # 3. Azure AD users + managers
    manager_df = fetch_manager_df(token)

    # 4. SharePoint site ID + DataWatch assignees
    site_id         = get_sharepoint_site_id(token)
    datawatch_names = fetch_datawatch_names(token, site_id) if site_id else set()

    # 5. Process attendance
    unique_days, zero_df, total_weekdays = process_attendance(
        badge_excel, start, end, manager_df, datawatch_names
    )

    # 6. Generate Excel report
    filename     = f"Attendance_Report_{start}_{end}.xlsx"
    report_bytes = generate_report_excel(unique_days, zero_df, start, end)

    # 7. Upload to SharePoint
    file_url = upload_to_sharepoint(token, site_id, filename, report_bytes) if site_id else ""

    # 8. Post to Teams
    post_to_teams(
        token, TEAMS_CHAT_ID,
        unique_days, zero_df, total_weekdays,
        start, end, file_url, filename,
    )

    log.info("=== Done ===")


if __name__ == "__main__":
    main()
