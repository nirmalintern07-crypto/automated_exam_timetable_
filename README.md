# ExamFlow – capacity-aware edition

Open the ExamScheduler folder in VS Code. Run each PowerShell command separately:

    py -V:3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe -m streamlit run app.py

Use Upload Dataset > Restore sample dataset to try a small multi-room example. PDF and six CSV imports remain supported. Download templates from the upload page. Required room columns: RoomID, Capacity (positive integer). Optional: Status (Available or Unavailable; omit column for all available), UnavailableSlots (semicolon-separated slot IDs; blank means no restrictions). Capacity is exam seating capacity, not ordinary classroom capacity. One invigilator per occupied room, no room sharing between subjects in a session. The GA uses a greedy room allocation heuristic, not an exact solver; a feasible schedule is not guaranteed. Reports with issues are drafts. StudentID is the roll number. Seat numbers are assigned per room and session, not physical desk maps. Student PDF contains all students; distribute securely.
