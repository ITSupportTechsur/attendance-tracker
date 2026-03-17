import streamlit as st
import pandas as pd
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

# ─── Password Gate ────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🏢 Attendance Tracker")
    pwd = st.text_input("Enter password", type="password")
    if st.button("Sign in"):
        if pwd == "TechSur!23$":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

st.title("🏢 Attendance Tracker")
st.caption(f"Only counts badge events at **{OFFICE_ADDRESS}**. Weekdays only.")

# ─── Azure AD Sidebar ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Azure AD — Manager Sync")

    if not AZURE_AVAILABLE:
        st.warning("Install `msal` and `requests` to enable Azure AD sync.")
    else:
        import os
        _default_tenant = st.session_state.get("az_tenant", os.environ.get("AZURE_TENANT_ID", ""))
        _default_client = st.session_state.get("az_client", os.environ.get("AZURE_CLIENT_ID", ""))
        _default_secret = st.session_state.get("az_secret", os.environ.get("AZURE_CLIENT_SECRET", ""))

        tenant_id     = st.text_input("Tenant ID",     value=_default_tenant, type="default")
        client_id     = st.text_input("Client ID",     value=_default_client, type="default")
        client_secret = st.text_input("Client Secret", value=_default_secret, type="password")

        if st.button("🔄 Sync from Azure AD", use_container_width=True):
            if not (tenant_id and client_id and client_secret):
                st.error("Fill in all three fields.")
            else:
                with st.spinner("Authenticating…"):
                    try:
                        app = msal.ConfidentialClientApplication(
                            client_id,
                            authority=f"https://login.microsoftonline.com/{tenant_id}",
                            client_credential=client_secret,
                        )
                        result = app.acquire_token_for_client(
                            scopes=["https://graph.microsoft.com/.default"]
                        )
                        if "access_token" not in result:
                            st.error(f"Auth failed: {result.get('error_description', result.get('error'))}")
                        else:
                            token = result["access_token"]
                            headers = {"Authorization": f"Bearer {token}"}
                            # Fetch all users with manager expanded — paginate
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
                                    st.error(f"Graph error: {data['error'].get('message')}")
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
                            manager_df = pd.DataFrame(rows)
                            st.session_state["manager_df"] = manager_df
                            st.session_state["az_tenant"] = tenant_id
                            st.session_state["az_client"] = client_id
                            st.session_state["az_secret"] = client_secret
                            st.success(f"Synced {len(manager_df)} employees from Azure AD.")
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.divider()
    st.subheader("Or upload manager CSV")
    st.caption("CSV must have columns: **Employee**, **Manager**, **Manager Email**")
    mgr_file = st.file_uploader("Manager CSV", type=["csv"], key="mgr_upload")
    if mgr_file:
        try:
            uploaded_mgr = pd.read_csv(mgr_file)
            required = {"Employee", "Manager", "Manager Email"}
            if not required.issubset(set(uploaded_mgr.columns)):
                st.error(f"CSV must have columns: {', '.join(required)}")
            else:
                st.session_state["manager_df"] = uploaded_mgr
                st.success(f"Loaded {len(uploaded_mgr)} rows.")
        except Exception as e:
            st.error(f"Could not read CSV: {e}")

    if "manager_df" in st.session_state:
        st.success(f"Manager data loaded: {len(st.session_state['manager_df'])} employees")
        if st.button("Clear manager data"):
            del st.session_state["manager_df"]
            st.rerun()


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

    manager_filter = st.selectbox(
        "Filter to a specific manager (or see all below)",
        ["All Managers"] + all_managers,
    )

    managers_to_show = all_managers if manager_filter == "All Managers" else [manager_filter]

    for mgr in managers_to_show:
        team = unique_days[unique_days["Manager"] == mgr].copy()
        if team.empty:
            continue

        mgr_email = team["Manager Email"].iloc[0] if "Manager Email" in team.columns else ""
        label = f"{mgr}  ({mgr_email})" if mgr_email else mgr
        avg_pct = team["Attendance %"].mean()
        team_count = len(team)

        with st.expander(f"👤 **{label}** — {team_count} direct report(s) — avg {avg_pct:.1f}%", expanded=(manager_filter != "All Managers")):
            styled_team = (
                team[["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]]
                .rename(columns={"_name": "Employee"})
                .style.applymap(color_pct, subset=["Attendance %"])
            )
            st.dataframe(styled_team, use_container_width=True, height=min(50 + team_count * 38, 400))

            chart_team = team.rename(columns={"_name": "Employee"})
            st.plotly_chart(make_bar_chart(chart_team, title=f"{mgr}'s Team"), use_container_width=True)

            # Per-manager CSV export
            export_team = team[["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]].rename(
                columns={"_name": "Employee"}
            )
            safe_name = mgr.replace(" ", "_").replace("/", "-")
            st.download_button(
                f"⬇ Download {mgr}'s report",
                export_team.to_csv(index=False).encode("utf-8"),
                f"attendance_{safe_name}_{start_date}_{end_date}.csv",
                "text/csv",
                key=f"dl_{mgr}",
            )

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
export_cols = ["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]
rename_export = {"_name": "Employee"}
if has_managers:
    export_cols += ["Manager", "Manager Email"]

export_df = unique_days[export_cols].rename(columns=rename_export)
csv = export_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇ Download Full CSV", csv, "attendance_report.csv", "text/csv")
