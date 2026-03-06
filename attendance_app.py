import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import timedelta, date

st.set_page_config(page_title="Attendance Tracker", page_icon="🏢", layout="wide")

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
st.caption("Upload any access log Excel sheet to get attendance stats per employee.")

# ─── File Upload ─────────────────────────────────────────────────────────────
uploaded = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx", "xls"])

if not uploaded:
    st.info("Upload an Excel file above to get started.")
    st.stop()

# ─── Load & Auto-detect columns ──────────────────────────────────────────────
@st.cache_data
def load_data(file):
    df = pd.read_excel(file)
    return df

df_raw = load_data(uploaded)

with st.expander("📋 Raw data preview", expanded=False):
    st.dataframe(df_raw.head(20), use_container_width=True)

# Auto-detect datetime column
def find_col(df, keywords):
    for col in df.columns:
        if any(k.lower() in col.lower() for k in keywords):
            return col
    return None

datetime_col  = find_col(df_raw, ["date", "time", "datetime", "timestamp"])
firstname_col = find_col(df_raw, ["first"])
lastname_col  = find_col(df_raw, ["last"])
name_col      = find_col(df_raw, ["name", "employee", "person", "user"])

# ─── Column Mapping UI ───────────────────────────────────────────────────────
st.subheader("Column Mapping")
col1, col2, col3 = st.columns(3)
all_cols = list(df_raw.columns)

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

# Filter data to selected range — weekdays only for accurate % calculation
mask = (df["_date"] >= start_date) & (df["_date"] <= end_date)
df_filtered = df[mask]

# Weekdays only (Mon–Fri): exclude weekend badge-ins from attendance count
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
unique_days["Days Absent"] = total_weekdays - unique_days["Days Present"]
unique_days = unique_days.sort_values("Attendance %", ascending=False).reset_index(drop=True)
unique_days.index += 1

# ─── Summary Cards ────────────────────────────────────────────────────────────
st.subheader("Summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Employees", len(unique_days))
m2.metric("Weekdays in Range", total_weekdays)
m3.metric("Avg Attendance %", f"{unique_days['Attendance %'].mean():.1f}%")
m4.metric("Date Range", f"{start_date} → {end_date}")

# ─── Table ────────────────────────────────────────────────────────────────────
st.subheader("Attendance per Employee")

def color_pct(val):
    if val >= 80:
        return "background-color: #1a6b3c; color: #a8f0c6; font-weight: bold"
    elif val >= 50:
        return "background-color: #7a5c00; color: #ffd966; font-weight: bold"
    else:
        return "background-color: #7a1a1a; color: #f4a0a0; font-weight: bold"

styled = unique_days[["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]].rename(
    columns={"_name": "Employee"}
).style.applymap(color_pct, subset=["Attendance %"])

st.dataframe(styled, use_container_width=True, height=500)

# ─── Chart ────────────────────────────────────────────────────────────────────
st.subheader("Attendance % Chart")

chart_df = unique_days.rename(columns={"_name": "Employee"}).copy()

def bar_color(pct):
    if pct >= 80:
        return "#2ecc71"
    elif pct >= 50:
        return "#f39c12"
    else:
        return "#e74c3c"

chart_df["Color"] = chart_df["Attendance %"].apply(bar_color)

import plotly.graph_objects as go
fig = go.Figure(go.Bar(
    x=chart_df["Employee"],
    y=chart_df["Attendance %"],
    marker_color=chart_df["Color"],
    text=chart_df["Attendance %"].astype(str) + "%",
    textposition="outside",
    textfont=dict(color="white", size=11),
))
fig.update_layout(
    plot_bgcolor="#0e1117",
    paper_bgcolor="#0e1117",
    font_color="white",
    xaxis=dict(tickangle=-45, tickfont=dict(color="white")),
    yaxis=dict(range=[0, 115], gridcolor="#333", tickfont=dict(color="white")),
    height=500,
    margin=dict(t=20),
)
st.plotly_chart(fig, use_container_width=True)

# ─── Individual Lookup ────────────────────────────────────────────────────────
st.subheader("🔍 Look up a specific employee")
names = sorted(unique_days["_name"].tolist())
selected = st.selectbox("Select employee", names)

if selected:
    row = unique_days[unique_days["_name"] == selected].iloc[0]
    emp_days = df_weekdays[df_weekdays["_name"] == selected]["_date"].drop_duplicates().sort_values()

    c1, c2, c3 = st.columns(3)
    c1.metric("Days Present", int(row["Days Present"]))
    c2.metric("Days Absent", int(row["Days Absent"]))
    c3.metric("Attendance %", f"{row['Attendance %']}%")

    with st.expander("Show days they came in"):
        for d in emp_days:
            st.write(f"• {d.strftime('%A, %B %d %Y')}")

# ─── Export ───────────────────────────────────────────────────────────────────
st.subheader("Export")
export_df = unique_days[["_name", "Days Present", "Days Absent", "Total Weekdays", "Attendance %"]].rename(
    columns={"_name": "Employee"}
)
csv = export_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇ Download CSV", csv, "attendance_report.csv", "text/csv")
