import random
import string
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request, session
from sqlalchemy import select, func, text
from app.blueprints.auth import login_required
from app.db import db
from app.db_models import User, Subject, ClassSession, SessionJoin, Attendance, StudentProfile
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
    rows = db.session.execute(
        select(Subject.id, Subject.name, Subject.code)
        .filter_by(teacher_id=session["user_id"])
        .order_by(Subject.id.desc())
    ).all()
    return jsonify({"subjects": [{"id": r.id, "name": r.name, "code": r.code} for r in rows]})

@bp.route("/subjects/<int:sub_id>/sessions", methods=["GET"])
@login_required("teacher")
def get_subject_sessions(sub_id):
    # Fix P2: IDOR data leak - verify teacher owns the subject
    sbj = db.session.execute(select(Subject).filter_by(id=sub_id, teacher_id=session["user_id"])).scalar_one_or_none()
    if not sbj:
        return jsonify({"error": "Unauthorized"}), 403

    rows = db.session.execute(
        select(ClassSession.id, ClassSession.code, ClassSession.created_at)
        .filter_by(subject_id=sub_id)
        .order_by(ClassSession.id.desc())
    ).all()
    return jsonify({"sessions": [{
        "id": r.id, 
        "code": r.code, 
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")
    } for r in rows]})

@bp.route("/subjects/<int:sub_id>/at-risk", methods=["GET"])
@login_required("teacher")
def get_at_risk_students(sub_id):
    # Verify subject belongs to teacher
    sbj = db.session.execute(select(Subject).filter_by(id=sub_id, teacher_id=session["user_id"])).scalar_one_or_none()
    if not sbj:
        return jsonify({"error": "Unauthorized"}), 403
        
    # Complexity: CTE/Joins for risk analysis. Using raw SQL with text() for this specific heavy lifting.
    query = text("""
    WITH subject_sessions AS (
        SELECT id FROM class_sessions WHERE subject_id = :sub_id
    ),
    enrolled_students AS (
        SELECT DISTINCT student_id FROM session_joins WHERE session_id IN (SELECT id FROM subject_sessions)
    )
    SELECT 
        e.student_id, 
        u.username, 
        p.full_name,
        p.roll_number,
        (SELECT COUNT(*) FROM attendance a WHERE a.student_id = e.student_id AND a.session_id IN (SELECT id FROM subject_sessions)) as attended,
        (SELECT COUNT(*) FROM subject_sessions) as total_sessions
    FROM enrolled_students e
    JOIN users u ON u.id = e.student_id
    LEFT JOIN student_profiles p ON p.user_id = e.student_id
    """)
    
    rows = db.session.execute(query, {"sub_id": sub_id}).all()
    
    at_risk = []
    for r in rows:
        total = r.total_sessions
        if total == 0: continue
            
        attended = r.attended
        pct = (attended / total) * 100
        
        if pct < 75.0:
            at_risk.append({
                "username": r.username,
                "name": r.full_name or r.username,
                "roll": r.roll_number or "N/A",
                "attended": attended,
                "total": total,
                "percentage": round(pct, 1)
            })
            
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
        
    try:
        sub = Subject(name=name, code=code, teacher_id=session["user_id"])
        db.session.add(sub)
        db.session.commit()
        return jsonify({"ok": True, "id": sub.id, "name": name, "code": code})
    except Exception as e:
        db.session.rollback()
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
        
    teacher_id = session["user_id"]
    sbj = db.session.execute(select(Subject).filter_by(id=subject_id, teacher_id=teacher_id)).scalar_one_or_none()
    if not sbj:
        return jsonify({"error": "Invalid subject"}), 403

    prefix = _network_prefix_for_request()
    expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_CODE_TTL_MINUTES)

    for _ in range(20):
        code = _generate_code()
        try:
            new_session = ClassSession(
                code=code, teacher_id=teacher_id, subject_id=subject_id,
                network_prefix=prefix, lat=lat, lng=lng, expires_at=expires
            )
            db.session.add(new_session)
            db.session.commit()
            return jsonify({
                "ok": True,
                "session_id": new_session.id,
                "code": code,
                "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S"),
                "network_prefix": prefix,
            })
        except Exception:
            db.session.rollback()
    return jsonify({"error": "Could not generate unique code"}), 500

@bp.route("/sessions/join", methods=["POST"])
@login_required("student")
def join_session():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "code required"}), 400
    
    sess = db.session.execute(
        select(ClassSession, User.org_code)
        .join(User, User.id == ClassSession.teacher_id)
        .filter(ClassSession.code == code)
    ).first()

    if not sess:
        return jsonify({"error": "Invalid session code"}), 404
    
    # Fix P1: Cross-organization attendance access
    if sess.org_code != session.get("org_code"):
        return jsonify({"error": "Unauthorized: Session belongs to another organization"}), 403
        
    class_sess = sess.ClassSession
    if class_sess.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return jsonify({"error": "Session expired"}), 410

    student_id = session["user_id"]
    try:
        # Check if already joined
        existing = db.session.get(SessionJoin, (class_sess.id, student_id))
        if not existing:
            join = SessionJoin(session_id=class_sess.id, student_id=student_id)
            db.session.add(join)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Fix P2: False success on DB errors while joining session
        return jsonify({"error": "Failed to join session: database error"}), 500

    return jsonify({
        "ok": True,
        "session_id": class_sess.id,
        "code": code,
        "network_prefix_expected": class_sess.network_prefix,
    })

@bp.route("/sessions/mine", methods=["GET"])
@login_required("teacher")
def list_teacher_sessions():
    # Complex query with Join and Count
    query = (
        select(
            ClassSession.id, ClassSession.code, ClassSession.expires_at, 
            ClassSession.created_at, Subject.name.label("subject_name"),
            func.count(Attendance.id).label("attendance_count")
        )
        .join(Subject, ClassSession.subject_id == Subject.id)
        .outerjoin(Attendance, ClassSession.id == Attendance.session_id)
        .filter(ClassSession.teacher_id == session["user_id"])
        .group_by(ClassSession.id, Subject.name, ClassSession.code, ClassSession.expires_at, ClassSession.created_at)
        .order_by(ClassSession.id.desc())
        .limit(50)
    )
    rows = db.session.execute(query).all()
    return jsonify({"sessions": [{
        "id": r.id, "code": r.code, "expires_at": r.expires_at.strftime("%Y-%m-%d %H:%M"),
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        "subject_name": r.subject_name, "attendance_count": r.attendance_count
    } for r in rows]})
