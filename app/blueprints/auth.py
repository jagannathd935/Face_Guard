import functools
from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import select, update
from app.db import db
from app.db_models import User, StudentProfile, TeacherProfile

bp = Blueprint("auth", __name__)

def login_required(role=None):
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            uid = session.get("user_id")
            if not uid:
                return jsonify({"error": "Not logged in"}), 401
            if role:
                user = db.session.get(User, uid)
                if not user or user.role != role:
                    return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator

def current_user_id():
    return session.get("user_id")

@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip().lower()
    org_code = (data.get("org_code") or "").strip().upper()

    if not username or not password or not org_code:
        return jsonify({"error": "username, password, and organization code required"}), 400
    if role not in ("teacher", "student", "admin"):
        return jsonify({"error": "invalid role"}), 400

    try:
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            org_code=org_code
        )
        db.session.add(new_user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Username already exists"}), 409
    return jsonify({"ok": True, "username": username, "role": role})

@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    requested_role = (data.get("role") or "").strip().lower()

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    user = db.session.execute(select(User).filter_by(username=username)).scalar_one_or_none()
    
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    if requested_role and user.role != requested_role:
        session.clear()
        return jsonify({"error": f"This account is registered as {user.role}"}), 403

    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    session["org_code"] = user.org_code
    session["username"] = username
    return jsonify({"ok": True, "user_id": user.id, "role": user.role, "org_code": user.org_code, "username": username})

@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@bp.route("/me", methods=["GET"])
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in": True,
        "user_id": uid,
        "username": session.get("username"),
        "role": session.get("role"),
        "org_code": session.get("org_code"),
    })

@bp.route("/profile/setup", methods=["POST"])
@login_required()
def setup_profile():
    data = request.get_json(silent=True) or {}
    uid = session.get("user_id")
    role = session.get("role")
    full_name = data.get("full_name")

    if not full_name:
        return jsonify({"error": "Full name is required"}), 400

    sec_q = data.get("security_question", "").strip()
    sec_a = data.get("security_answer", "").strip().lower()
    if not sec_q or not sec_a:
        return jsonify({"error": "Security question and answer required"}), 400

    try:
        user = db.session.get(User, uid)
        user.security_question = sec_q
        user.security_answer_hash = generate_password_hash(sec_a)

        if role == "student":
            roll = data.get("roll_number", "")
            dept = data.get("department", "")
            batch = data.get("batch_year", "")
            profile = db.session.get(StudentProfile, uid)
            if not profile:
                profile = StudentProfile(user_id=uid, full_name=full_name, roll_number=roll, department=dept, batch_year=batch)
                db.session.add(profile)
            else:
                profile.full_name = full_name
                profile.roll_number = roll
                profile.department = dept
                profile.batch_year = batch
        elif role == "teacher":
            emp_id = data.get("employee_id", "")
            dept = data.get("department", "")
            desig = data.get("designation", "")
            profile = db.session.get(TeacherProfile, uid)
            if not profile:
                profile = TeacherProfile(user_id=uid, full_name=full_name, employee_id=emp_id, department=dept, designation=desig)
                db.session.add(profile)
            else:
                profile.full_name = full_name
                profile.employee_id = emp_id
                profile.department = dept
                profile.designation = desig
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True})

@bp.route("/profile/me", methods=["GET"])
@login_required()
def get_profile():
    uid = session.get("user_id")
    role = session.get("role")
    profile = None
    if role == "student":
        row = db.session.get(StudentProfile, uid)
    elif role == "teacher":
        row = db.session.get(TeacherProfile, uid)
    else:
        row = None

    if not row:
        return jsonify({"ok": True, "has_profile": False})

    # Manual dict conversion for compatibility
    res = {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != "user_id"}
    return jsonify({"ok": True, "has_profile": True, "profile": res})

@bp.route("/recover-account", methods=["POST"])
def recover_account():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"error": "Username required"}), 400

    user = db.session.execute(select(User).filter_by(username=username)).scalar_one_or_none()
    if not user or not user.security_question:
        return jsonify({"error": "No security question set."}), 404

    return jsonify({"ok": True, "user_id": user.id, "security_question": user.security_question})

@bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    answer = (data.get("security_answer") or "").strip().lower()
    new_pass = data.get("new_password") or ""

    if not user_id or not answer or not new_pass:
        return jsonify({"error": "Missing required fields"}), 400

    user = db.session.get(User, user_id)
    # Fix P2: Password reset can 500 for users without security answer hash
    if not user or not user.security_answer_hash or not check_password_hash(user.security_answer_hash, answer):
        return jsonify({"error": "Incorrect security answer."}), 401

    user.password_hash = generate_password_hash(new_pass)
    db.session.commit()
    return jsonify({"ok": True})
