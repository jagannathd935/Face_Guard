from flask import Blueprint, jsonify, request, session
from app.blueprints.auth import login_required
from app.db import get_db

bp = Blueprint("admin", __name__)

@bp.route("/users", methods=["GET"])
@login_required("admin")
def list_users():
    db = get_db()
    org_code = session.get("org_code")
    users = db.execute("SELECT id, username, role, created_at FROM users WHERE org_code = ? ORDER BY id DESC", (org_code,)).fetchall()
    return jsonify({"users": [dict(u) for u in users]})

@bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required("admin")
def delete_user(user_id):
    db = get_db()
    admin_id = session.get("user_id")
    org_code = session.get("org_code")
    
    # Ensure target user is in the same organization
    target = db.execute("SELECT username, org_code FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target or target["org_code"] != org_code:
        return jsonify({"error": "User isolated or not found"}), 403
        
    target_username = target["username"]

    try:
        # Write Immutable Audit Log BEFORE deleting
        db.execute(
            "INSERT INTO audit_logs (admin_id, org_code, action_type, target) VALUES (?, ?, ?, ?)",
            (admin_id, org_code, "DELETE_USER", target_username)
        )

        # Cascading Hard Delete
        db.execute("DELETE FROM face_profiles WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM student_profiles WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM teacher_profiles WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM class_sessions WHERE teacher_id = ?", (user_id,))
        db.execute("DELETE FROM session_joins WHERE student_id = ?", (user_id,))
        db.execute("DELETE FROM attendance WHERE student_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"ok": True})

@bp.route("/audit-logs", methods=["GET"])
@login_required("admin")
def get_audit_logs():
    db = get_db()
    org_code = session.get("org_code")
    logs = db.execute(
        '''SELECT a.id, u.username as admin_name, a.action_type, a.target, a.created_at 
           FROM audit_logs a JOIN users u ON a.admin_id = u.id 
           WHERE a.org_code = ? ORDER BY a.id DESC LIMIT 100''', 
        (org_code,)
    ).fetchall()
    return jsonify({"logs": [dict(l) for l in logs]})
