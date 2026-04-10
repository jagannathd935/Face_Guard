import io

import pandas as pd
from flask import Blueprint, Response, jsonify, request, session
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from app.blueprints.auth import login_required
from app.db import get_db

bp = Blueprint("export", __name__)


@bp.route("/export/attendance", methods=["GET"])
@login_required("teacher")
def export_attendance():
    sid = request.args.get("session_id", type=int)
    fmt = (request.args.get("format") or "xlsx").lower()
    if not sid:
        return jsonify({"error": "session_id required"}), 400
    db = get_db()
    sess = db.execute(
        "SELECT id, code FROM class_sessions WHERE id = ? AND teacher_id = ?",
        (sid, session["user_id"]),
    ).fetchone()
    if not sess:
        return jsonify({"error": "Not found"}), 404
    rows = db.execute(
        """
        SELECT u.username AS student, a.marked_at
        FROM attendance a
        JOIN users u ON u.id = a.student_id
        WHERE a.session_id = ?
        ORDER BY a.marked_at
        """,
        (sid,),
    ).fetchall()
    data = [{"student": r["student"], "marked_at": r["marked_at"]} for r in rows]
    if fmt == "xlsx":
        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame(columns=["student", "marked_at"])
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Attendance")
        buf.seek(0)
        return Response(
            buf.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=attendance_{sess['code']}.xlsx"
            },
        )
    if fmt == "pdf":
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [
            Paragraph(f"<b>FaceGuard Attendance</b> — Session {sess['code']}", styles["Title"]),
            Spacer(1, 12),
        ]
        table_data = [["Student", "Marked at"]] + [[r["student"], r["marked_at"]] for r in rows]
        t = Table(table_data, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
                ]
            )
        )
        story.append(t)
        doc.build(story)
        buf.seek(0)
        return Response(
            buf.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=attendance_{sess['code']}.pdf"},
        )
    return jsonify({"error": "format must be xlsx or pdf"}), 400

@bp.route("/export/subject", methods=["GET"])
@login_required("teacher")
def export_subject():
    sub_id = request.args.get("subject_id", type=int)
    if not sub_id:
        return jsonify({"error": "subject_id required"}), 400
        
    db = get_db()
    sbj = db.execute("SELECT name, code FROM subjects WHERE id = ? AND teacher_id = ?", (sub_id, session["user_id"])).fetchone()
    if not sbj:
        return jsonify({"error": "Subject not found or unauthorized"}), 403
        
    sessions = db.execute("SELECT id, code, strftime('%m-%d', created_at) as date FROM class_sessions WHERE subject_id = ? ORDER BY id", (sub_id,)).fetchall()
    if not sessions:
        return jsonify({"error": "No sessions for this subject yet"}), 400
        
    session_ids = [s["id"] for s in sessions]
    s_ids_str = ",".join("?" for _ in session_ids)
    
    rows = db.execute(f"""
        SELECT a.session_id, u.username, p.full_name, p.roll_number
        FROM attendance a
        JOIN users u ON u.id = a.student_id
        LEFT JOIN student_profiles p ON p.user_id = u.id
        WHERE a.session_id IN ({s_ids_str})
    """, session_ids).fetchall()
    
    data = []
    for r in rows:
        data.append({
            "session_id": r["session_id"],
            "Username": r["username"],
            "Student Name": r["full_name"] or r["username"],
            "Roll No.": r["roll_number"] or "N/A"
        })
    
    df = pd.DataFrame(data)
    if df.empty:
        return jsonify({"error": "No attendance records found for this subject."}), 400
        
    mapping = {s["id"]: f"{s['code']} ({s['date']})" for s in sessions}
    df['Session'] = df['session_id'].map(mapping)
    df['Status'] = "Present"
    
    pivot = df.pivot_table(index=['Student Name', 'Username', 'Roll No.'], columns='Session', values='Status', aggfunc='first', fill_value="Absent")
    pivot.reset_index(inplace=True)
    
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pivot.to_excel(w, index=False, sheet_name="Master Analytics")
    buf.seek(0)
    
    safe_name = sbj['name'].replace(" ", "_")
    return Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=MasterAnalytics_{safe_name}.xlsx"
        },
    )
