import streamlit as st
import pandas as pd
import io
from datetime import timedelta, date
import plotly.graph_objects as go

# Optional Azure AD imports
try:
    import msal
    import requests as http_requests
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

st.set_page_config(page_title="Attendance Tracker", page_icon="🏢", layout="wide")

OFFICE_ADDRESS = "11190 Sunrise Valley Drive"


st.title("🏢 Attendance Tracker")
st.caption(f"Only counts badge events at **{OFFICE_ADDRESS}**. Weekdays only.")

# ─── Auto-sync Azure AD once per session ─────────────────────────────────────
def _sync_azure_ad():
    import os
    tenant_id     = os.environ.get("AZURE_TENANT_ID", "")
    client_id     = os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    if not (AZURE_AVAILABLE and tenant_id and client_id and client_secret):
        return
    try:
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            return
        token   = result["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        url = (
            "https://graph.microsoft.com/v1.0/users"
            "?$select=displayName,mail,userPrincipalName"
            "&$expand=manager($select=displayName,mail)"
            "&$top=999"
        )
        users = []
        while url:
            resp = http_requests.get(url, headers=headers)
            data = resp.json()
            if "error" in data:
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
        st.session_state["manager_df"] = pd.DataFrame(rows)
    except Exception:
        pass

if "manager_df" not in st.session_state:
    _sync_azure_ad()


# ─── File Upload ─────────────────────────────────────────────────────────────
uploaded = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx", "xls"])

if not uploaded:
    st.info("Upload an Excel file above to get started.")
    st.stop()

# ─── Load & Auto-detect columns ──────────────────────────────────────────────
@st.cache_data
def load_data(file):
    return pd.read_excel(file)

df_raw = load_data(uploaded)

with st.expander("📋 Raw data preview", expanded=False):
    st.dataframe(df_raw.head(20), use_container_width=True)

def find_col(df, keywords):
    for col in df.columns:
        if any(k.lower() in col.lower() for k in keywords):
            return col
    return None

datetime_col  = find_col(df_raw, ["date", "time", "datetime", "timestamp"])
firstname_col = find_col(df_raw, ["first"])
lastname_col  = find_col(df_raw, ["last"])
name_col      = find_col(df_raw, ["name", "employee", "person", "user"])
address_col   = find_col(df_raw, ["address", "from", "location", "site", "building", "door", "reader"])

# ─── Column Mapping UI ───────────────────────────────────────────────────────
st.subheader("Column Mapping")
all_cols = list(df_raw.columns)

col1, col2, col3, col4 = st.columns(4)

with col1:
    datetime_col = st.selectbox("Date/Time column", all_cols,
        index=all_cols.index(datetime_col) if datetime_col else 0)

with col2:
    use_split = firstname_col is not None and lastname_col is not None
    name_mode = st.radio("Name format", ["First + Last (separate cols)", "Single name column"],
        index=0 if use_split else 1)

with col3:
    if name_mode == "First + Last (separate cols)":
        firstname_col = st.selectbox("First Name col", all_cols,
            index=all_cols.index(firstname_col) if firstname_col else 0)
        lastname_col  = st.selectbox("Last Name col",  all_cols,
            index=all_cols.index(lastname_col)  if lastname_col  else 0)
    else:
        name_col = st.selectbox("Name column", all_cols,
            index=all_cols.index(name_col) if name_col else 0)

with col4:
    addr_options = ["(None — no address filter)"] + all_cols
    addr_default_idx = (
        addr_options.index(address_col) if address_col and address_col in addr_options else 0
    )
    selected_addr_col = st.selectbox(
        f"Address / Location column",
        addr_options,
        index=addr_default_idx,
        help=f"Only rows where this column equals '{OFFICE_ADDRESS}' will be counted.",
    )
    apply_addr_filter = selected_addr_col != "(None — no address filter)"

# ─── Build working dataframe ─────────────────────────────────────────────────
df = df_raw.copy()
df["_dt"] = pd.to_datetime(df[datetime_col], errors="coerce")
df = df.dropna(subset=["_dt"])
df["_date"] = df["_dt"].dt.date

if name_mode == "First + Last (separate cols)":
    df["_name"] = (df[firstname_col].fillna("") + " " + df[lastname_col].fillna("")).str.strip()
else:
    df["_name"] = df[name_col].fillna("").str.strip()

df = df[df["_name"] != ""]

# ─── Address Filter ───────────────────────────────────────────────────────────
if apply_addr_filter:
    before = len(df)
    df = df[df[selected_addr_col].astype(str).str.strip() == OFFICE_ADDRESS]
    after = len(df)
    excluded = before - after
    if excluded > 0:
        st.info(
            f"Address filter active — excluded **{excluded:,}** rows not from "
            f"*{OFFICE_ADDRESS}* (kept {after:,} of {before:,})."
        )
    if df.empty:
        st.error(
            f"No records match address '{OFFICE_ADDRESS}'. "
            "Check that you selected the right column, or disable the address filter."
        )
        st.stop()

# ─── Date Range Filter ───────────────────────────────────────────────────────
st.subheader("Date Range")
data_min = df["_date"].min()
data_max = df["_date"].max()

col_a, col_b = st.columns(2)
with col_a:
    start_date = st.date_input("From", value=data_min, min_value=data_min, max_value=data_max)
with col_b:
    end_date = st.date_input("To", value=data_max, min_value=data_min, max_value=data_max)

if start_date > end_date:
    st.error("Start date must be before end date.")
    st.stop()

# ─── Weekday calculation ─────────────────────────────────────────────────────
def count_weekdays(start, end):
    total = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            total += 1
        cur += timedelta(days=1)
    return total

total_weekdays = count_weekdays(start_date, end_date)

mask = (df["_date"] >= start_date) & (df["_date"] <= end_date)
df_filtered = df[mask]
df_weekdays = df_filtered[pd.to_datetime(df_filtered["_date"]).dt.dayofweek < 5]

# ─── Attendance Stats ─────────────────────────────────────────────────────────
unique_days = (
    df_weekdays.drop_duplicates(subset=["_name", "_date"])
    .groupby("_name")["_date"]
    .count()
    .reset_index()
    .rename(columns={"_date": "Days Present"})
)

unique_days["Total Weekdays"] = total_weekdays
unique_days["Attendance %"] = (unique_days["Days Present"] / total_weekdays * 100).round(1)
unique_days["Days Absent"]  = total_weekdays - unique_days["Days Present"]
unique_days = unique_days.sort_values("Attendance %", ascending=False).reset_index(drop=True)
unique_days.index += 1

# ─── Merge manager data if available ─────────────────────────────────────────
manager_df = st.session_state.get("manager_df")
has_managers = manager_df is not None and not manager_df.empty

if has_managers:
    # Fuzzy-friendly merge: lowercase strip both sides
    mgr_lookup = manager_df.copy()
    mgr_lookup["_key"] = mgr_lookup["Employee"].str.strip().str.lower()
    unique_days["_key"] = unique_days["_name"].str.strip().str.lower()
    unique_days = unique_days.merge(
        mgr_lookup[["_key", "Manager", "Manager Email"]],
        on="_key", how="left"
    ).drop(columns=["_key"])
    unique_days["Manager"] = unique_days["Manager"].fillna("Unknown / Not Mapped")
    unique_days["Manager Email"] = unique_days["Manager Email"].fillna("")

# ─── Summary Cards ────────────────────────────────────────────────────────────
st.subheader("Summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Employees",   len(unique_days))
m2.metric("Weekdays in Range", total_weekdays)
m3.metric("Avg Attendance %",  f"{unique_days['Attendance %'].mean():.1f}%")
m4.metric("Date Range",        f"{start_date} → {end_date}")

# ─── Helpers ─────────────────────────────────────────────────────────────────
def color_pct(val):
    if val >= 80:
        return "background-color: #1a6b3c; color: #a8f0c6; font-weight: bold"
    elif val >= 50:
        return "background-color: #7a5c00; color: #ffd966; font-weight: bold"
    else:
        return "background-color: #7a1a1a; color: #f4a0a0; font-weight: bold"

def bar_color(pct):
    if pct >= 80: return "#2ecc71"
    elif pct >= 50: return "#f39c12"
    else: return "#e74c3c"

def make_bar_chart(df_in, title=""):
    fig = go.Figure(go.Bar(
        x=df_in["Employee"],
        y=df_in["Attendance %"],
        marker_color=df_in["Attendance %"].apply(bar_color),
        text=df_in["Attendance %"].astype(str) + "%",
        textposition="outside",
        textfont=dict(color="white", size=11),
    ))
    fig.update_layout(
        title=title,
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="white",
        xaxis=dict(tickangle=-45, tickfont=dict(color="white")),
        yaxis=dict(range=[0, 115], gridcolor="#333", tickfont=dict(color="white")),
        height=500,
        margin=dict(t=40),
    )
    return fig

# ─── Excel Export Helper ──────────────────────────────────────────────────────
def _safe_sheet_name(name):
    """Truncate to 31 chars and strip characters Excel forbids in sheet names."""
    return (name[:31]
            .replace("/", "-").replace("\\", "-")
            .replace("*", "").replace("[", "").replace("]", "")
            .replace(":", "").replace("?", ""))

def _team_sheet(df_team, writer, sheet_name):
    """Write a sorted team DataFrame to an Excel sheet."""
    sheet_df = (
        df_team[["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]]
        .sort_values("Attendance %", ascending=True)   # at-risk first
        .rename(columns={"_name": "Employee"})
        .reset_index(drop=True)
    )
    sheet_df.index += 1
    sheet_df.to_excel(writer, sheet_name=sheet_name, index=True, index_label="#")

def make_manager_excel(data_df, single_manager=None):
    """
    Full workbook layout (single_manager=None):
      Sheet 1 — All Employees  (everyone, sorted by manager then attendance)
      Sheets 2…N — one sheet per manager (alphabetical), employees sorted worst→best
      Last sheet — No Manager  (if any employees have no manager assigned)

    When single_manager is provided, returns a single-sheet workbook for that manager.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        if single_manager:
            team = data_df[data_df["Manager"] == single_manager].copy()
            _team_sheet(team, writer, _safe_sheet_name(single_manager))

        else:
            # ── Sheet 1: All Employees ────────────────────────────────────────
            cols = ["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]
            if "Manager" in data_df.columns:
                cols += ["Manager"]
            summary = (
                data_df[cols]
                .sort_values(
                    (["Manager", "Attendance %"] if "Manager" in cols else ["Attendance %"]),
                    ascending=True,
                )
                .rename(columns={"_name": "Employee"})
                .reset_index(drop=True)
            )
            summary.index += 1
            summary.to_excel(writer, sheet_name="All Employees", index=True, index_label="#")

            # ── One sheet per manager (alphabetical) ─────────────────────────
            if "Manager" in data_df.columns:
                named_managers = sorted([
                    m for m in data_df["Manager"].dropna().unique()
                    if m not in ("No Manager", "Unknown / Not Mapped")
                ])
                for mgr in named_managers:
                    team = data_df[data_df["Manager"] == mgr].copy()
                    if team.empty:
                        continue
                    _team_sheet(team, writer, _safe_sheet_name(mgr))

                # ── No Manager sheet ──────────────────────────────────────────
                no_mgr = data_df[data_df["Manager"].isin(["No Manager", "Unknown / Not Mapped", None]) |
                                 data_df["Manager"].isna()].copy()
                if not no_mgr.empty:
                    _team_sheet(no_mgr, writer, "No Manager")

    return output.getvalue()


# ─── View Mode Toggle ─────────────────────────────────────────────────────────
view_options = ["Overall Report"]
if has_managers:
    view_options += ["By Manager"]

view_mode = st.radio("View", view_options, horizontal=True)

# ─── Overall Report ───────────────────────────────────────────────────────────
if view_mode == "Overall Report":
    st.subheader("Attendance per Employee")

    display_cols = ["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]
    rename_map = {"_name": "Employee"}
    if has_managers:
        display_cols += ["Manager"]
        rename_map["Manager"] = "Manager"

    styled = (
        unique_days[display_cols]
        .rename(columns=rename_map)
        .style.applymap(color_pct, subset=["Attendance %"])
    )
    st.dataframe(styled, use_container_width=True, height=500)

    st.subheader("Attendance % Chart")
    chart_df = unique_days.rename(columns={"_name": "Employee"})
    st.plotly_chart(make_bar_chart(chart_df), use_container_width=True)

# ─── By Manager Report ────────────────────────────────────────────────────────
elif view_mode == "By Manager":
    all_managers = sorted(unique_days["Manager"].dropna().unique().tolist())

    # ── Download all managers in one Excel ────────────────────────────────────
    all_excel = make_manager_excel(unique_days)
    st.download_button(
        "⬇ Download All Manager Reports (Excel)",
        all_excel,
        f"all_manager_reports_{start_date}_{end_date}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_all_managers",
        help="One sheet per manager + a summary sheet — ready to split and send",
    )
    st.divider()

    jump_to = st.selectbox("Jump to a manager", ["— Show all —"] + all_managers)
    managers_to_show = all_managers if jump_to == "— Show all —" else [jump_to]

    for mgr in managers_to_show:
        team = (
            unique_days[unique_days["Manager"] == mgr]
            .sort_values("Attendance %", ascending=True)   # at-risk employees first
            .copy()
        )
        if team.empty:
            continue

        mgr_email = team["Manager Email"].iloc[0] if "Manager Email" in team.columns else ""
        team_count = len(team)
        avg_pct    = team["Attendance %"].mean()
        green_count  = (team["Attendance %"] >= 80).sum()
        yellow_count = ((team["Attendance %"] >= 50) & (team["Attendance %"] < 80)).sum()
        red_count    = (team["Attendance %"] < 50).sum()

        # ── Manager header banner ──────────────────────────────────────────────
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(90deg,#1a2a3a,#0e1a2a);
                border-left: 5px solid #3a8fd4;
                border-radius: 8px;
                padding: 16px 20px;
                margin: 24px 0 8px 0;
            ">
                <div style="font-size:20px; font-weight:700; color:#e8f4fd;">
                    👤 {mgr}
                </div>
                {"<div style='font-size:13px; color:#8ab4cc; margin-top:4px;'>📧 " + mgr_email + "</div>" if mgr_email else ""}
                <div style="font-size:13px; color:#8ab4cc; margin-top:2px;">
                    Period: {start_date.strftime("%b %d, %Y")} — {end_date.strftime("%b %d, %Y")} &nbsp;|&nbsp; {total_weekdays} working days
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Team summary stats ─────────────────────────────────────────────────
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("Direct Reports",  team_count)
        s2.metric("Team Avg",        f"{avg_pct:.1f}%")
        s3.metric("On Track (≥80%)", green_count,  delta=None)
        s4.metric("At Risk (50–79%)", yellow_count, delta=None)
        s5.metric("Critical (<50%)", red_count,    delta=None)

        # ── Attendance table ───────────────────────────────────────────────────
        display_team = (
            team[["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]]
            .rename(columns={"_name": "Employee"})
            .reset_index(drop=True)
        )
        display_team.index += 1

        styled_team = display_team.style.applymap(color_pct, subset=["Attendance %"])
        st.dataframe(styled_team, use_container_width=True, height=min(80 + team_count * 38, 450))

        # ── Bar chart ─────────────────────────────────────────────────────────
        chart_team = team.rename(columns={"_name": "Employee"})
        st.plotly_chart(
            make_bar_chart(chart_team, title=f"{mgr} — Team Attendance"),
            use_container_width=True,
            key=f"chart_{mgr}",
        )

        # ── Download ──────────────────────────────────────────────────────────
        safe_name = mgr.replace(" ", "_").replace("/", "-")
        mgr_excel = make_manager_excel(unique_days, single_manager=mgr)
        st.download_button(
            f"⬇ Download {mgr}'s report (Excel)",
            mgr_excel,
            f"attendance_{safe_name}_{start_date}_{end_date}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_{mgr}",
        )

        st.divider()

# ─── Individual Lookup ────────────────────────────────────────────────────────
st.subheader("🔍 Look up a specific employee")
names = sorted(unique_days["_name"].tolist())
selected = st.selectbox("Select employee", names)

if selected:
    row = unique_days[unique_days["_name"] == selected].iloc[0]
    emp_days = df_weekdays[df_weekdays["_name"] == selected]["_date"].drop_duplicates().sort_values()

    cols = st.columns(4 if has_managers else 3)
    cols[0].metric("Days Present",  int(row["Days Present"]))
    cols[1].metric("Days Absent",   int(row["Days Absent"]))
    cols[2].metric("Attendance %",  f"{row['Attendance %']}%")
    if has_managers:
        cols[3].metric("Manager", row.get("Manager", "—"))

    with st.expander("Show days they came in"):
        for d in emp_days:
            st.write(f"• {d.strftime('%A, %B %d %Y')}")

# ─── Export ───────────────────────────────────────────────────────────────────
st.subheader("Export")
full_excel = make_manager_excel(unique_days)
st.download_button(
    "⬇ Download Full Report (Excel — all employees + one sheet per manager)",
    full_excel,
    f"attendance_report_{start_date}_{end_date}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    key="dl_full_excel",
)
