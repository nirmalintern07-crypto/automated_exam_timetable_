"""ExamFlow — polished Streamlit interface for the existing exam scheduler."""
from pathlib import Path
from io import BytesIO
import html
import pandas as pd
import streamlit as st
from scheduler import REQUIRED, validate_inputs, generate_schedule, available_rooms, seating_table
from pdf_io import parse_input_pdf, make_template_pdf, make_report_pdf, audience_pdf

st.set_page_config(page_title="ExamFlow | Smart Exam Scheduler", page_icon="🎓", layout="wide", initial_sidebar_state="expanded")
BASE = Path(__file__).parent

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"], [data-testid="stApp"] {font-family:'DM Sans',sans-serif;}
[data-testid="stAppViewContainer"] {background:linear-gradient(145deg,#f3f7fc 0%,#f9fbff 58%,#edf7f5 100%);color:#13233a;}
[data-testid="stSidebar"] {background:#101f39;}
[data-testid="stSidebar"] * {color:#e6efff !important;}
[data-testid="stSidebar"] [role="radiogroup"] label {border-radius:11px;padding:9px 11px;margin:3px 0;}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {background:#203553;}
.block-container {padding-top:2rem;max-width:1350px;}
h1,h2,h3 {color:#10223d;letter-spacing:-.035em;}
h1 {font-weight:800 !important;}
[data-testid="stMetric"] {background:white;border:1px solid #e2eaf2;border-radius:16px;padding:22px;border-top:3px solid #0d9488;box-shadow:0 5px 20px rgba(21,42,75,.035);}
[data-testid="stMetricLabel"] {color:#687b92;}
[data-testid="stMetricValue"] {color:#132a48;font-weight:800;}
.stButton>button[kind="primary"], .stDownloadButton>button[kind="primary"] {background:#087f76;border:0;color:white;border-radius:11px;font-weight:700;padding:.65rem 1.1rem;}
.stButton>button, .stDownloadButton>button {border-radius:11px;font-weight:650;}
[data-testid="stFileUploader"] {background:white;border:1px dashed #92bdb7;border-radius:15px;padding:12px;}
[data-testid="stExpander"], [data-testid="stDataFrame"] {border-radius:13px;overflow:hidden;}
.hero {border:1px solid #29465c;background:linear-gradient(112deg,#112544 0%,#163956 65%,#087f76 140%);color:white;border-radius:22px;padding:30px 34px;margin-bottom:24px;box-shadow:0 15px 35px rgba(18,39,66,.12);}
.hero .eyebrow {color:#70e2cd;font-size:12px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;}
.hero h1 {color:white !important;font-size:2.15rem;margin:.35rem 0 .5rem;}
.hero p {color:#d5e4f3;margin:0;font-size:15px;}
.step-card {background:white;border:1px solid #e0eaf2;border-radius:16px;padding:20px;min-height:140px;box-shadow:0 4px 15px rgba(25,52,81,.03);}
.step-card .step {color:#07877c;font-size:12px;font-weight:800;letter-spacing:.08em;}
.step-card h3 {font-size:18px;margin:8px 0;}
.step-card p {color:#63758b;font-size:13px;margin:0;}
.tag {display:inline-block;background:#dff6ef;color:#07695f;border-radius:30px;padding:5px 11px;font-size:12px;font-weight:800;}
.small-note {color:#718299;font-size:13px;}
</style>""", unsafe_allow_html=True)

@st.cache_data
def sample_data():
    return {name: pd.read_csv((BASE / "data" if (BASE / "data").is_dir() else BASE) / f"{name}.csv", dtype=str) for name in REQUIRED}

if "data" not in st.session_state: st.session_state.data = {k: pd.DataFrame(columns=v) for k,v in REQUIRED.items()}
if "schedule" not in st.session_state: st.session_state.schedule = None
if "history" not in st.session_state: st.session_state.history = None
if "issues" not in st.session_state: st.session_state.issues = None
if "source" not in st.session_state: st.session_state.source = "No dataset uploaded"

PAGES = ["🏠 Dashboard", "📤 Upload Dataset", "⚡ Generate Schedule", "🏫 Allocations", "📄 Reports"]
with st.sidebar:
    st.markdown("## 🎓 ExamFlow")
    st.caption("SMART EXAMINATION MANAGEMENT")
    st.divider()
    page = st.radio("WORKSPACE", PAGES, label_visibility="collapsed")
    st.divider()
    st.markdown("**Current dataset**")
    st.caption(st.session_state.source)
    st.markdown("🟢 **Ready**" if st.session_state.schedule is not None else "🟡 **Awaiting schedule**")
    st.caption("PDF or CSV in · Optimized schedule out")

def hero(eyebrow, title, subtitle):
    st.markdown(f'<div class="hero"><div class="eyebrow">{html.escape(eyebrow)}</div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>', unsafe_allow_html=True)

def card(num, title, description):
    st.markdown(f'<div class="step-card"><div class="step">STEP {num}</div><h3>{html.escape(title)}</h3><p>{html.escape(description)}</p></div>', unsafe_allow_html=True)

def csv_bytes(df): return df.to_csv(index=False).encode("utf-8")
def excel_bytes(df):
    b = BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as writer: df.to_excel(writer, index=False, sheet_name="Exam Timetable")
    return b.getvalue()

def reset_schedule():
    st.session_state.schedule = None
    st.session_state.history = None
    st.session_state.issues = None

if page == PAGES[0]:
    hero("Overview", "Your examination command center", "Create, validate and export examination schedules in a few simple steps.")
    d = st.session_state.data
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("👥 Students", f"{len(d['students']):,}")
    c2.metric("📚 Subjects", f"{len(d['subjects']):,}")
    c3.metric("🏫 Rooms", f"{len(d['rooms']):,}")
    c4.metric("🧑‍🏫 Invigilators", f"{len(d['invigilators']):,}")
    a,b = st.columns(2)
    a.metric("Registrations", f"{len(d['registrations']):,}")
    b.metric("Exam slots", f"{len(d['slots']):,}")
    x,y = st.columns(2)
    available = [available_rooms(d, slot) for slot in d['slots']['SlotID']]
    x.metric("Peak available classrooms", max((len(r) for r in available), default=0))
    y.metric("Peak available seats per session", max((sum(c for _,c in r) for r in available), default=0))
    st.caption(f"Active dataset: {st.session_state.source}")
    st.markdown("### Your three-step workflow")
    a,b,c = st.columns(3)
    with a: card("01", "Upload PDF or CSV", "Import all six examination tables.")
    with b: card("02", "Generate timetable", "Run the genetic algorithm and allocate rooms and staff.")
    with c: card("03", "Download report", "Export your final timetable as a polished PDF, CSV or Excel.")
    st.markdown("### Scheduling status")
    if st.session_state.schedule is None:
        st.info("Upload a dataset to begin." if d["students"].empty else "Dataset loaded. Choose Generate Schedule to begin.")
    else:
        schedule = st.session_state.schedule
        issues = st.session_state.issues or []
        left,right = st.columns([1,3])
        left.metric("Scheduled exams", schedule.SubjectID.nunique())
        (right.warning if issues else right.success)("All implemented checks passed." if not issues else f"Schedule generated with {len(issues)} validation issue(s).")
        st.dataframe(schedule.head(15), use_container_width=True, hide_index=True)

elif page == PAGES[1]:
    hero("Data import", "Bring your examination data", "Choose a structured PDF or six CSV files. Your dashboard updates after successful validation.")
    mode = st.radio("Input format", ["PDF", "CSV"], horizontal=True)
    if mode == "PDF":
        st.caption("Use a selectable-text PDF following the template; scanned PDFs are not supported.")
        st.download_button("Download PDF template", make_template_pdf(sample_data()), "exam_input_template.pdf", "application/pdf")
        upload = st.file_uploader("Examination PDF", type=["pdf"])
        ready = upload is not None
    else:
        import zipfile
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            for name, frame in sample_data().items(): z.writestr(name+".csv", csv_bytes(frame))
        st.download_button("Download six CSV templates (ZIP)", archive.getvalue(), "csv_templates.zip", "application/zip")
        uploads = {name: st.file_uploader(name.title()+" CSV", type=["csv"], key="csv_"+name) for name in REQUIRED}
        ready = all(v is not None for v in uploads.values())
    if st.button("Validate and load dataset", type="primary", disabled=not ready):
        try:
            loaded = parse_input_pdf(BytesIO(upload.getvalue())) if mode == "PDF" else {k: pd.read_csv(BytesIO(v.getvalue()), dtype=str) for k,v in uploads.items()}
            problems = validate_inputs(loaded)
            if problems:
                st.error("Dataset rejected. Previous active dataset remains unchanged.")
                for problem in problems: st.write(problem)
            else:
                st.session_state.data = loaded
                st.session_state.source = upload.name if mode == "PDF" else "CSV dataset (six files)"
                reset_schedule()
                st.rerun()
        except Exception as exc: st.error(f"Import failed: {exc}")
    st.caption("Optional rooms columns: Status (Available/Unavailable), UnavailableSlots (semicolon-separated SlotIDs).")
    st.info("Active dataset: " + st.session_state.source)
    st.markdown("### Loaded dataset preview")
    for name, df in st.session_state.data.items():
        with st.expander(f"{name.title()} · {len(df):,} records"):
            st.dataframe(df.head(100), use_container_width=True, hide_index=True)
            if len(df)>100: st.caption("Showing the first 100 records for a faster preview.")
    if st.button("↺ Restore sample dataset"):
        st.session_state.data = sample_data()
        st.session_state.source = "Sample dataset"
        st.session_state.pop("last_upload_signature", None)
        reset_schedule()
        st.rerun()

elif page == PAGES[2]:
    hero("Optimization", "Generate your examination timetable", "Run the Genetic Algorithm and automatically assign examination rooms and invigilators.")
    st.markdown("### Optimization settings")
    a,b,c = st.columns(3)
    generations = a.number_input("Maximum generations", min_value=1, max_value=5000, value=120)
    population = b.number_input("Population size", min_value=4, max_value=1000, value=80)
    seed = c.number_input("Random seed", min_value=0, value=42)
    problems = validate_inputs(st.session_state.data)
    if problems:
        st.error("Please correct these input issues before generating:")
        for p in problems: st.write("•", p)
    elif st.button("⚡ Generate optimized timetable", type="primary", use_container_width=True):
        try:
            with st.spinner("Optimizing timetable and assigning resources..."):
                schedule, history, issues = generate_schedule(st.session_state.data, int(population), int(generations), int(seed))
            st.session_state.schedule, st.session_state.history, st.session_state.issues = schedule, history, issues
        except Exception as exc: st.error(f"Scheduling failed: {exc}")
    if st.session_state.schedule is not None:
        issues = st.session_state.issues or []
        a,b,c = st.columns(3)
        a.metric("Best fitness", f"{st.session_state.history.iloc[-1].Fitness:.4f}")
        b.metric("Scheduled exams", st.session_state.schedule.SubjectID.nunique())
        c.metric("Validation issues", len(issues))
        if issues:
            st.warning("Some constraints are not satisfied. Review the issues before using this schedule.")
            with st.expander("View validation issues", expanded=True):
                for issue in issues: st.write("•", issue)
        else: st.success("All implemented scheduling constraints passed validation.")
        st.markdown("### Timetable preview")
        st.dataframe(st.session_state.schedule, use_container_width=True, hide_index=True)
        st.markdown("### Fitness across generations")
        st.line_chart(st.session_state.history.set_index("Generation")["Fitness"])

elif page == PAGES[3]:
    hero("Resource planning", "Room & invigilator allocations", "Inspect room assignments, staff duties and scheduling conflicts.")
    if st.session_state.schedule is None:
        st.info("Generate a timetable first to view allocations.")
    else:
        df = st.session_state.schedule
        a,b,c = st.columns(3)
        a.metric("Scheduled exams", df.SubjectID.nunique())
        b.metric("Rooms assigned", df["RoomID"].dropna().astype(str).loc[lambda x: x.str.strip().ne("")].nunique())
        c.metric("Invigilators assigned", df["InvigilatorID"].dropna().astype(str).loc[lambda x: x.str.strip().ne("")].nunique())
        x,y,z = st.columns(3)
        x.metric("Allocated seats", int(df.AllocatedStudents.sum()))
        y.metric("Unallocated registrations", int(df.UnallocatedStudents.sum()))
        capacity = int(df.RoomCapacity.sum())
        z.metric("Assigned room utilization", f"{100*df.AllocatedStudents.sum()/capacity:.1f}%" if capacity else "0%")
        room_tab,staff_tab,seat_tab,checks_tab = st.tabs(["🏫 Room allocation", "🧑‍🏫 Invigilator duties", "Student seating", "🛡️ Validation"])
        with seat_tab:
            seats = seating_table(df, st.session_state.data)
            query = st.text_input("Search roll number")
            st.dataframe(seats[seats.StudentID.str.contains(query, case=False, regex=False)], hide_index=True, use_container_width=True)
            st.download_button("Download seating CSV", csv_bytes(seats), "student_seating.csv", "text/csv")
        with room_tab:
            cols = [x for x in ["SubjectID","SubjectName","Date","Session","RoomID","RoomCapacity","AllocatedStudents","UnallocatedStudents"] if x in df]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
        with staff_tab:
            cols = [x for x in ["SubjectID","SubjectName","Date","Session","StartTime","EndTime","RoomID","InvigilatorID"] if x in df]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
        with checks_tab:
            if st.session_state.issues:
                st.warning(f"{len(st.session_state.issues)} validation issue(s) detected.")
                for issue in st.session_state.issues: st.write("•", issue)
            else: st.success("No issues detected by the existing scheduler's validation checks.")

elif page == PAGES[4]:
    hero("Export center", "Your reports, ready to share", "Download the generated timetable and validation results in your preferred format.")
    if st.session_state.schedule is None:
        st.info("Generate a timetable before downloading reports.")
    else:
        df = st.session_state.schedule
        st.markdown("### Complete examination report")
        try:
            report = make_report_pdf(df, st.session_state.history, st.session_state.issues)
            st.download_button("📄 Download complete PDF report", report, file_name="exam_schedule_report.pdf", mime="application/pdf", type="primary", use_container_width=True)
        except Exception as exc: st.error(f"PDF report could not be generated: {exc}")
        st.markdown("### Audience-specific printable timetables")
        if st.session_state.issues: st.warning("Draft only: resolve validation issues before distributing reports.")
        for audience, label in [("students", "Student examination timetable"), ("teachers", "Teacher invigilation duties")]:
            st.download_button(label + " (PDF)", audience_pdf(df, st.session_state.data, audience, st.session_state.issues), audience+"_timetable.pdf", "application/pdf", use_container_width=True)
        a,b = st.columns(2)
        a.download_button("⬇️ Download CSV", csv_bytes(df), "final_exam_timetable.csv", "text/csv", use_container_width=True)
        b.download_button("⬇️ Download Excel", excel_bytes(df), "final_exam_timetable.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        st.markdown("### Report preview")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📈 Download fitness history (CSV)", csv_bytes(st.session_state.history), "fitness_history.csv", "text/csv")
        if st.session_state.issues: st.warning(f"Report contains {len(st.session_state.issues)} validation issue(s).")
        else: st.success("Report contains no issues detected by the implemented validation rules.")
