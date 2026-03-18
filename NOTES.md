# Attendance Tracker — Project Notes

## What This Does
Reads Datawatch access log exports (Excel) from Techsur and calculates:
- How many **unique days** each employee came in (1 entry per day regardless of how many badge swipes)
- **Attendance %** based on weekdays (Mon–Fri) in the selected date range
- Bar chart + color-coded table + individual employee lookup

---

## Source Data
- File: `Export (4).xlsx` (from Datawatch system)
- Sheet: `ACHistory`
- 2,269 raw entries → 547 unique person-days → 52 employees
- Date range in original file: Feb 2 – Mar 5, 2026 (24 weekdays)
- Key columns:
  - D: First Name
  - E: Last Name
  - F: Date Time (timestamp of each badge event)
  - K: Event Message (e.g. "Access Granted At WEST LOBBY DR")

---

## Files
| File | Purpose |
|---|---|
| `attendance_app.py` | Main Streamlit web app — upload Excel, get attendance report |
| `deduplicate_access_logs.py` | One-off script, outputs `Export_Unique_Days.xlsx` |
| `requirements.txt` | Python dependencies for deployment |
| `.streamlit/config.toml` | Streamlit server config for deployment |

---

## How to Run Locally
```bash
# First time only — create the virtual environment
python3 -m venv /Users/yousseffrangieh/Downloads/attendance_env
/Users/yousseffrangieh/Downloads/attendance_env/bin/pip install streamlit pandas plotly openpyxl

# Run the app
/Users/yousseffrangieh/Downloads/attendance_env/bin/streamlit run attendance_app.py --server.headless true
# Then open: http://localhost:8501
```

---

## Calculation Logic
- **Days Present** = unique dates the employee badged in, **weekdays only (Mon–Fri)**
- **Total Weekdays** = count of Mon–Fri days in the selected date range
- **Attendance %** = Days Present / Total Weekdays × 100
- Weekend badge-ins are intentionally excluded from the count (bug found: Rupinder Yadav came in on Sunday Feb 15 — fixed)

---

## Deployment Plan — Streamlit Community Cloud (Option C)
1. Create a **private GitHub repo** named `attendance-tracker`
2. Upload these 3 items to the repo:
   - `attendance_app.py`
   - `requirements.txt`
   - `.streamlit/config.toml`
3. Go to **share.streamlit.io** → sign in with GitHub → New App
4. Select the repo, set main file to `attendance_app.py`, deploy
5. Share the URL with HR (e.g. `https://yourname-attendance-tracker.streamlit.app`)

### Other Options Considered
- **Option A — Azure App Service**: Microsoft cloud, ~$10–15/month, no Docker needed, stays internal, deploy from GitHub
- **Option B — Azure Container Apps**: Requires Docker — skipped
- **Option C — Streamlit Community Cloud**: Free, fastest, public internet (chosen)

---

## Sample Results (Feb 2 – Mar 5, 2026)
| Employee | Days Present | Attendance % |
|---|---|---|
| Madhur Gupta | 22 | 91.7% |
| Vishal Luthra | 22 | 91.7% |
| Craig Park 2 | 21 | 87.5% |
| Mitchell Crespo | 20 | 83.3% |
| Shailendra Gohil | 20 | 83.3% |
| Sridhar Kesiraju | 20 | 83.3% |
| ... | ... | ... |
| Rupinder Yadav | 1 | 4.2% |
| Jennifer Falcone | 1 | 4.2% |
| Michael Gray | 1 | 4.2% |
| Trish Regan | 1 | 4.2% |
