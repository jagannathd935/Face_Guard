import functools

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db

bp = Blueprint("auth", __name__)


def login_required(role=None):
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            uid = session.get("user_id")
            if not uid:
                return jsonify({"error": "Not logged in"}), 401
            if role:
                db = get_db()
                row = db.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
                if not row or row["role"] != role:
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

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, role, org_code) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), role, org_code),
        )
        db.commit()
    except Exception:
        db.rollback()
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

    db = get_db()
    row = db.execute(
        "SELECT id, password_hash, role, org_code FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    if requested_role and row["role"] != requested_role:
        session.clear()
        return jsonify({"error": f"This account is registered as {row['role']}"}), 403

    session.clear()
    session["user_id"] = row["id"]
    session["role"] = row["role"]
    session["org_code"] = row["org_code"]
    session["username"] = username
    return jsonify({"ok": True, "user_id": row["id"], "role": row["role"], "org_code": row["org_code"], "username": username})


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.route("/me", methods=["GET"])
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"logged_in": False})
    return jsonify(
        {
            "logged_in": True,
            "user_id": uid,
            "username": session.get("username"),
            "role": session.get("role"),
            "org_code": session.get("org_code"),
        }
    )


@bp.route("/profile/setup", methods=["POST"])
@login_required()
def setup_profile():
    data = request.get_json(silent=True) or {}
    uid = session.get("user_id")
    role = session.get("role")
    full_name = data.get("full_name")

    if not full_name:
        return jsonify({"error": "Full name is required"}), 400

    security_question = data.get("security_question", "").strip()
    security_answer = data.get("security_answer", "").strip().lower()
    if not security_question or not security_answer:
        return jsonify({"error": "Security question and answer are required"}), 400

    db = get_db()

    try:
        db.execute(
            "UPDATE users SET security_question = ?, security_answer_hash = ? WHERE id = ?",
            (security_question, generate_password_hash(security_answer), uid)
        )
        if role == "student":
            roll_number = data.get("roll_number", "")
            department = data.get("department", "")
            batch_year = data.get("batch_year", "")
            db.execute(
                "INSERT INTO student_profiles (user_id, full_name, roll_number, department, batch_year) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, roll_number=excluded.roll_number, department=excluded.department, batch_year=excluded.batch_year",
                (uid, full_name, roll_number, department, batch_year)
            )
        elif role == "teacher":
            employee_id = data.get("employee_id", "")
            department = data.get("department", "")
            designation = data.get("designation", "")
            db.execute(
                "INSERT INTO teacher_profiles (user_id, full_name, employee_id, department, designation) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, employee_id=excluded.employee_id, department=excluded.department, designation=excluded.designation",
                (uid, full_name, employee_id, department, designation)
            )
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True})


@bp.route("/profile/me", methods=["GET"])
@login_required()
def get_profile():
    uid = session.get("user_id")
    role = session.get("role")
    db = get_db()

    profile = None
    if role == "student":
        row = db.execute("SELECT * FROM student_profiles WHERE user_id = ?", (uid,)).fetchone()
        if row:
            profile = dict(row)
            profile.pop("user_id", None)
    elif role == "teacher":
        row = db.execute("SELECT * FROM teacher_profiles WHERE user_id = ?", (uid,)).fetchone()
        if row:
            profile = dict(row)
            profile.pop("user_id", None)

    if not profile:
        return jsonify({"ok": True, "has_profile": False})

    return jsonify({"ok": True, "has_profile": True, "profile": profile})


@bp.route("/recover-account", methods=["POST"])
def recover_account():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"error": "Username required"}), 400

    db = get_db()
    row = db.execute("SELECT id, security_question FROM users WHERE username = ?", (username,)).fetchone()
    if not row or not row["security_question"]:
        return jsonify({"error": "No security question set for this user."}), 404

    return jsonify({"ok": True, "user_id": row["id"], "security_question": row["security_question"]})


@bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    answer = (data.get("security_answer") or "").strip().lower()
    new_password = data.get("new_password") or ""

    if not user_id or not answer or not new_password:
        return jsonify({"error": "Missing required fields"}), 400

    db = get_db()
    row = db.execute("SELECT security_answer_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or not check_password_hash(row["security_answer_hash"], answer):
        return jsonify({"error": "Incorrect security answer."}), 401

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), user_id))
    db.commit()

    return jsonify({"ok": True})
