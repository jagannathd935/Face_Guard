import io
import pandas as pd
from flask import Blueprint, Response, jsonify, request, session
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import select, and_, text
from app.blueprints.auth import login_required
from app.db import db
from app.db_models import User, ClassSession, Attendance, Subject, StudentProfile

bp = Blueprint("export", __name__)

@bp.route("/export/attendance", methods=["GET"])
@login_required("teacher")
def export_attendance():
    sid = request.args.get("session_id", type=int)
    fmt = (request.args.get("format") or "xlsx").lower()
    if not sid: return jsonify({"error": "session_id required"}), 400
    
    sess = db.session.execute(select(ClassSession).filter_by(id=sid, teacher_id=session["user_id"])).scalar_one_or_none()
    if not sess: return jsonify({"error": "Not found"}), 404
    
    rows = db.session.execute(
        select(User.username.label("student"), Attendance.marked_at)
        .join(User, User.id == Attendance.student_id)
        .filter(Attendance.session_id == sid)
        .order_by(Attendance.marked_at)
    ).all()
    
    data = [{"student": r.student, "marked_at": r.marked_at.strftime("%Y-%m-%d %H:%M:%S")} for r in rows]
    
    if fmt == "xlsx":
        df = pd.DataFrame(data) if data else pd.DataFrame(columns=["student", "marked_at"])
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Attendance")
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=attendance_{sess.code}.xlsx"})
    
    if fmt == "pdf":
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [Paragraph(f"<b>FaceGuard Attendance</b> — Session {sess.code}", styles["Title"]), Spacer(1, 12)]
        table_data = [["Student", "Marked at"]] + [[r["student"], r["marked_at"]] for r in data]
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ]))
        story.append(t)
        doc.build(story)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=attendance_{sess.code}.pdf"})
    
    return jsonify({"error": "invalid format"}), 400

@bp.route("/export/subject", methods=["GET"])
@login_required("teacher")
def export_subject():
    sub_id = request.args.get("subject_id", type=int)
    if not sub_id: return jsonify({"error": "subject_id required"}), 400
    
    sbj = db.session.execute(select(Subject).filter_by(id=sub_id, teacher_id=session["user_id"])).scalar_one_or_none()
    if not sbj: return jsonify({"error": "Unauthorized"}), 403
    
    sessions = db.session.execute(select(ClassSession).filter_by(subject_id=sub_id).order_by(ClassSession.id)).scalars().all()
    if not sessions: return jsonify({"error": "No sessions"}), 400
    
    s_ids = [s.id for s in sessions]
    rows = db.session.execute(
        select(Attendance.session_id, User.username, StudentProfile.full_name, StudentProfile.roll_number)
        .join(User, User.id == Attendance.student_id)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .filter(Attendance.session_id.in_(s_ids))
    ).all()
    
    data = [{
        "session_id": r.session_id, "Username": r.username,
        "Student Name": r.full_name or r.username, "Roll No.": r.roll_number or "N/A"
    } for r in rows]
    
    df = pd.DataFrame(data)
    if df.empty: return jsonify({"error": "No records"}), 400
    
    mapping = {s.id: f"{s.code} ({s.created_at.strftime('%m-%d')})" for s in sessions}
    df['Session'] = df['session_id'].map(mapping)
    df['Status'] = "Present"
    
    pivot = df.pivot_table(index=['Student Name', 'Username', 'Roll No.'], columns='Session', values='Status', aggfunc='first', fill_value="Absent")
    pivot.reset_index(inplace=True)
    
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pivot.to_excel(w, index=False, sheet_name="Analytics")
    buf.seek(0)
    
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=Analytics_{sbj.name.replace(' ','_')}.xlsx"})
