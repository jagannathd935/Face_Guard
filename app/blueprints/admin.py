from flask import Blueprint, jsonify, request, session
from sqlalchemy import select
from app.blueprints.auth import login_required
from app.db import db
from app.db_models import User, AuditLog

bp = Blueprint("admin", __name__)

@bp.route("/users", methods=["GET"])
@login_required("admin")
def list_users():
    org_code = session.get("org_code")
    rows = db.session.execute(
        select(User.id, User.username, User.role, User.created_at)
        .filter_by(org_code=org_code)
        .order_by(User.id.desc())
    ).all()
    return jsonify({"users": [{
        "id": r.id, "username": r.username, "role": r.role, 
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for r in rows]})

@bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required("admin")
def delete_user(user_id):
    admin_id = session.get("user_id")
    org_code = session.get("org_code")
    
    target = db.session.get(User, user_id)
    if not target or target.org_code != org_code:
        return jsonify({"error": "User not found or access denied"}), 403
        
    target_username = target.username

    try:
        log = AuditLog(admin_id=admin_id, org_code=org_code, action_type="DELETE_USER", target=target_username)
        db.session.add(log)
        # Cascades are handled by DB-level foreign keys or ORM definitions
        db.session.delete(target)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
        
    return jsonify({"ok": True})

@bp.route("/audit-logs", methods=["GET"])
@login_required("admin")
def get_audit_logs():
    org_code = session.get("org_code")
    rows = db.session.execute(
        select(AuditLog.id, User.username.label("admin_name"), AuditLog.action_type, AuditLog.target, AuditLog.created_at)
        .join(User, AuditLog.admin_id == User.id)
        .filter(AuditLog.org_code == org_code)
        .order_by(AuditLog.id.desc())
        .limit(100)
    ).all()
    return jsonify({"logs": [{
        "id": r.id, "admin_name": r.admin_name, "action_type": r.action_type, 
        "target": r.target, "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for r in rows]})
