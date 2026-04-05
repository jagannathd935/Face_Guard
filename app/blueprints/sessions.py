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


@bp.route("/sessions", methods=["POST"])
@login_required("teacher")
def create_session():
    db = get_db()
    teacher_id = session["user_id"]
    prefix = _network_prefix_for_request()
    expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_CODE_TTL_MINUTES)
    expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")

    for _ in range(20):
        code = _generate_code()
        try:
            cur = db.execute(
                """
                INSERT INTO class_sessions (code, teacher_id, network_prefix, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (code, teacher_id, prefix, expires_str),
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
        SELECT id, code, expires_at, created_at
        FROM class_sessions
        WHERE teacher_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (session["user_id"],),
    ).fetchall()
    return jsonify({"sessions": [dict(r) for r in rows]})
