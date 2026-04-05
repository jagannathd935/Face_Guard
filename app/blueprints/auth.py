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
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if role not in ("teacher", "student"):
        return jsonify({"error": "role must be teacher or student"}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
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
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    db = get_db()
    row = db.execute(
        "SELECT id, password_hash, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    session.clear()
    session["user_id"] = row["id"]
    session["role"] = row["role"]
    session["username"] = username
    return jsonify({"ok": True, "user_id": row["id"], "role": row["role"], "username": username})


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
        }
    )
