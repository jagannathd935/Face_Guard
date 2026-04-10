import random
import string
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request, session

from app.blueprints.auth import login_required
from app.db import get_db
from config import SESSION_CODE_TTL_MINUTES


bp = Blueprint("sessions", __name__)


def _network_prefix_for_request():
    ip = request.remote_addr or ""
    parts = ip.split(".")
    if len(parts) >= 3:
        return ".".join(parts[:3])
    return ip or "unknown"


def _generate_code():
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=6))


@bp.route("/subjects", methods=["GET"])
@login_required("teacher")
def get_subjects():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, code FROM subjects WHERE teacher_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    return jsonify({"subjects": [dict(r) for r in rows]})


@bp.route("/subjects/<int:sub_id>/sessions", methods=["GET"])
@login_required("teacher")
def get_subject_sessions(sub_id):
    db = get_db()
    rows = db.execute(
        "SELECT id, code, strftime('%Y-%m-%d %H:%M', created_at) as created_at FROM class_sessions WHERE subject_id = ? ORDER BY id DESC",
        (sub_id,),
    ).fetchall()
    return jsonify({"sessions": [dict(r) for r in rows]})


@bp.route("/subjects/<int:sub_id>/at-risk", methods=["GET"])
@login_required("teacher")
def get_at_risk_students(sub_id):
    db = get_db()
    sbj = db.execute("SELECT id FROM subjects WHERE id = ? AND teacher_id = ?", (sub_id, session["user_id"])).fetchone()
    if not sbj:
        return jsonify({"error": "Unauthorized"}), 403
        
    query = """
    WITH subject_sessions AS (
        SELECT id FROM class_sessions WHERE subject_id = ?
    ),
    enrolled_students AS (
        SELECT DISTINCT student_id FROM session_joins WHERE session_id IN subject_sessions
    )
    SELECT 
        e.student_id, 
        u.username, 
        p.full_name,
        p.roll_number,
        (SELECT COUNT(*) FROM attendance a WHERE a.student_id = e.student_id AND a.session_id IN subject_sessions) as attended,
        (SELECT COUNT(*) FROM subject_sessions) as total_sessions
    FROM enrolled_students e
    JOIN users u ON u.id = e.student_id
    LEFT JOIN student_profiles p ON p.user_id = e.student_id
    """
    rows = db.execute(query, (sub_id,)).fetchall()
    
    at_risk = []
    for r in rows:
        total = r["total_sessions"]
        if total == 0:
            continue
            
        attended = r["attended"]
        pct = (attended / total) * 100
        
        # Flag if attendance is below 75%
        if pct < 75.0:
            at_risk.append({
                "username": r["username"],
                "name": r["full_name"] or r["username"],
                "roll": r["roll_number"] or "N/A",
                "attended": attended,
                "total": total,
                "percentage": round(pct, 1)
            })
            
    # Sort worst attendance first
    at_risk.sort(key=lambda x: x["percentage"])
    return jsonify({"at_risk": at_risk})


@bp.route("/subjects", methods=["POST"])
@login_required("teacher")
def create_subject():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip().upper()
    
    if not name or not code:
        return jsonify({"error": "Subject name and code required"}), 400
        
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO subjects (name, code, teacher_id) VALUES (?, ?, ?)",
            (name, code, session["user_id"])
        )
        db.commit()
        return jsonify({"ok": True, "id": cur.lastrowid, "name": name, "code": code})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/sessions", methods=["POST"])
@login_required("teacher")
def create_session():
    data = request.get_json(silent=True) or {}
    subject_id = data.get("subject_id")
    lat = data.get("lat")
    lng = data.get("lng")
    
    if not subject_id:
        return jsonify({"error": "subject_id is required"}), 400
        
    db = get_db()
    teacher_id = session["user_id"]
    
    # Verify subject belongs to teacher
    sbj = db.execute("SELECT id FROM subjects WHERE id = ? AND teacher_id = ?", (subject_id, teacher_id)).fetchone()
    if not sbj:
        return jsonify({"error": "Invalid subject"}), 403

    prefix = _network_prefix_for_request()
    expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_CODE_TTL_MINUTES)
    expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")

    for _ in range(20):
        code = _generate_code()
        try:
            cur = db.execute(
                """
                INSERT INTO class_sessions (code, teacher_id, subject_id, network_prefix, lat, lng, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (code, teacher_id, subject_id, prefix, lat, lng, expires_str),
            )
            db.commit()
            return jsonify(
                {
                    "ok": True,
                    "session_id": cur.lastrowid,
                    "code": code,
                    "expires_at": expires_str,
                    "network_prefix": prefix,
                }
            )
        except Exception:
            db.rollback()
    return jsonify({"error": "Could not generate unique code"}), 500


@bp.route("/sessions/join", methods=["POST"])
@login_required("student")
def join_session():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "code required"}), 400
    db = get_db()
    row = db.execute(
        """
        SELECT id, teacher_id, network_prefix, expires_at
        FROM class_sessions WHERE code = ?
        """,
        (code,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Invalid session code"}), 404
    try:
        exp = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        exp = exp.replace(tzinfo=timezone.utc)
    except ValueError:
        exp = None
    if exp and datetime.now(timezone.utc) > exp:
        return jsonify({"error": "Session expired"}), 410

    student_id = session["user_id"]
    db.execute(
        """
        INSERT OR IGNORE INTO session_joins (session_id, student_id)
        VALUES (?, ?)
        """,
        (row["id"], student_id),
    )
    db.commit()
    return jsonify(
        {
            "ok": True,
            "session_id": row["id"],
            "code": code,
            "network_prefix_expected": row["network_prefix"],
        }
    )


@bp.route("/sessions/mine", methods=["GET"])
@login_required("teacher")
def list_teacher_sessions():
    db = get_db()
    rows = db.execute(
        """
        SELECT c.id, c.code, c.expires_at, c.created_at, s.name as subject_name, COUNT(a.id) as attendance_count
        FROM class_sessions c
        JOIN subjects s ON c.subject_id = s.id
        LEFT JOIN attendance a ON a.session_id = c.id
        WHERE c.teacher_id = ?
        GROUP BY c.id
        ORDER BY c.id DESC
        LIMIT 50
        """,
        (session["user_id"],),
    ).fetchall()
    return jsonify({"sessions": [dict(r) for r in rows]})
