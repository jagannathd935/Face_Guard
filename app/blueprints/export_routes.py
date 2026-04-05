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
