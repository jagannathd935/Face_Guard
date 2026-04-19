import os
import time
import math
from datetime import datetime, timezone
from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import select, and_
from app.blueprints.auth import login_required
from app.db import db
from app.db_models import User, ClassSession, SessionJoin, FaceProfile, Attendance, Subject
from app.services import face_fr_optional, liveness_mp
from app.services.face_lbph import load_model, lbph_distance
from app.services.face_structure import calculate_facial_ratios, compare_structures
import json
from config import FACE_MATCH_TOLERANCE, LBPH_MATCH_MAX_DISTANCE, LIVENESS_TOKEN_SECONDS

bp = Blueprint("attendance", __name__)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 # meters
    phi_1, phi_2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi/2.0)**2 + math.cos(phi_1)*math.cos(phi_2)*math.sin(d_lam/2.0)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _network_prefix_for_request():
    ip = request.remote_addr or ""
    parts = ip.split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else (ip or "unknown")

@bp.route("/liveness/verify-blink", methods=["POST"])
@login_required("student")
def verify_blink():
    data = request.get_json(silent=True) or {}
    frames = data.get("frames")
    if not frames or not isinstance(frames, list) or len(frames) < 6:
        return jsonify({"error": "Provide at least 6 base64 frames"}), 400
    bgrs = []
    for b64 in frames[:40]:
        img = b64_to_bgr_image(b64)
        if img is not None: bgrs.append(img)
    if not liveness_mp.detect_blink_in_frames(bgrs):
        return jsonify({"ok": False, "blink_detected": False}), 400
    session["liveness_verified_at"] = time.time()
    return jsonify({"ok": True, "blink_detected": True})

@bp.route("/liveness/verify-pose", methods=["POST"])
@login_required("student")
def verify_pose():
    data = request.get_json(silent=True) or {}
    expected = (data.get("expected") or "").lower()
    b64 = data.get("image")
    if expected not in ("left", "right") or not b64:
        return jsonify({"error": "expected (left|right) and image required"}), 400
    img = b64_to_bgr_image(b64)
    hint = liveness_mp.head_pose_hint(img)
    if hint == expected:
        session["liveness_verified_at"] = time.time()
        return jsonify({"ok": True, "detected": hint})
    return jsonify({"ok": False, "detected": hint})

def _verify_face_profile(prof, live_gray, live_bgr) -> tuple[bool, str, float | None]:
    model_dir = current_app.config["FACE_MODEL_DIR"]
    lbph_ok, fr_ok, dist_out = None, None, None

    if prof.lbph_model_relpath:
        rec = load_model(os.path.join(model_dir, prof.lbph_model_relpath))
        if rec is None: return False, "Face model missing on server", None
        dist_out = lbph_distance(rec, live_gray)
        if dist_out is None: return False, "Could not score face (LBPH)", None
        lbph_ok = dist_out <= LBPH_MATCH_MAX_DISTANCE

    if prof.fr_encoding_json and face_fr_optional.HAS_FACE_RECOGNITION:
        unk = face_fr_optional.encoding_from_bgr(live_bgr)
        if unk is None: return False, "No face detected for embedding check", dist_out
        match, fdist = face_fr_optional.match_encoding(unk, face_fr_optional.json_to_encoding(prof.fr_encoding_json), FACE_MATCH_TOLERANCE)
        dist_out = fdist if dist_out is None else dist_out
        fr_ok = match

    if lbph_ok is None and fr_ok is None: return False, "No usable face verifier", None
    if lbph_ok is not None and fr_ok is not None: return (lbph_ok and fr_ok), "Face mismatch", dist_out
    if lbph_ok is not None: return lbph_ok, "Face mismatch (LBPH)", dist_out
    return fr_ok, "Face mismatch (embedding)", dist_out

def _verify_aiml_structure(prof, live_bgr) -> tuple[bool, str]:
    if not prof.structure_json:
        return True, "" # Skip if no saved structure
    
    saved = json.loads(prof.structure_json)
    live = calculate_facial_ratios(live_bgr)
    if not live:
        return False, "Could not analyze face structure. Ensure face is clear."
    
    match, diff = compare_structures(saved, live)
    if not match:
        return False, f"Structural mismatch (AI). Face does not match registered profile."
    
    return True, ""

@bp.route("/attendance/mark", methods=["POST"])
@login_required("student")
def mark_attendance():
    data = request.get_json(silent=True) or {}
    code = (data.get("session_code") or "").strip().upper()
    image_b64 = data.get("image")
    if not code or not image_b64:
        return jsonify({"error": "session_code and image required"}), 400

    ts = session.get("liveness_verified_at")
    if not ts or (time.time() - ts) > LIVENESS_TOKEN_SECONDS:
        return jsonify({"error": "Liveness not verified; blink again"}), 403

    student_id = session["user_id"]
    sess_row = db.session.execute(
        select(ClassSession, User.org_code)
        .join(User, User.id == ClassSession.teacher_id)
        .filter(ClassSession.code == code)
    ).first()

    if not sess_row: return jsonify({"error": "Invalid session code"}), 404
    
    # Fix P1: Cross-organization attendance access
    if sess_row.org_code != session.get("org_code"):
        return jsonify({"error": "Unauthorized format organization"}), 403

    sess = sess_row.ClassSession
    if sess.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return jsonify({"error": "Session expired"}), 410

    # Geofence
    if sess.lat is not None and sess.lng is not None:
        s_lat, s_lng = data.get("lat"), data.get("lng")
        if s_lat is None or s_lng is None:
            return jsonify({"error": "GPS location required"}), 403
        dist = haversine(sess.lat, sess.lng, s_lat, s_lng)
        # 150 meters threshold to account for indoor GPS drift
        if dist > 150: return jsonify({"error": f"Too far ({int(dist)}m)"}), 403

    # Network
    s_prefix = _network_prefix_for_request()
    if sess.network_prefix and s_prefix != sess.network_prefix:
        return jsonify({"error": "Network mismatch", "expected": sess.network_prefix, "your": s_prefix}), 403

    # Joined?
    if not db.session.get(SessionJoin, (sess.id, student_id)):
        return jsonify({"error": "Join session first"}), 403

    # Face Profile
    prof = db.session.get(FaceProfile, student_id)
    if not prof or (not prof.lbph_model_relpath and not prof.fr_encoding_json):
        return jsonify({"error": "Register face first"}), 403

    img = b64_to_bgr_image(image_b64)
    gray = largest_face_gray(img) if img is not None else None
    if gray is None: return jsonify({"error": "No face detected"}), 400

    ok_face, reason, dist = _verify_face_profile(prof, gray, img)
    if not ok_face:
        return jsonify({"ok": False, "error": reason, "distance": dist}), 400

    # AIML Structural Verification
    ok_struct, struct_reason = _verify_aiml_structure(prof, img)
    if not ok_struct:
        return jsonify({"ok": False, "error": struct_reason}), 400

    try:
        att = Attendance(session_id=sess.id, student_id=student_id)
        db.session.add(att)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"ok": True, "duplicate": True, "message": "Already marked"}), 200

    session.pop("liveness_verified_at", None)
    return jsonify({"ok": True, "duplicate": False, "distance": dist})

@bp.route("/attendance/session/<int:sid>", methods=["GET"])
@login_required("teacher")
def list_attendance(sid):
    sess = db.session.execute(select(ClassSession).filter_by(id=sid, teacher_id=session["user_id"])).scalar_one_or_none()
    if not sess: return jsonify({"error": "Not found"}), 404
    
    rows = db.session.execute(
        select(Attendance.student_id, User.username, Attendance.marked_at)
        .join(User, User.id == Attendance.student_id)
        .filter(Attendance.session_id == sid)
        .order_by(Attendance.marked_at)
    ).all()
    
    return jsonify({"records": [{
        "student_id": r.student_id, "username": r.username, 
        "marked_at": r.marked_at.strftime("%Y-%m-%d %H:%M:%S")
    } for r in rows]})

@bp.route("/attendance/mine", methods=["GET"])
@login_required("student")
def my_attendance():
    uid = session["user_id"]
    rows = db.session.execute(
        select(Attendance.marked_at, ClassSession.code, Subject.name.label("subject_name"))
        .join(ClassSession, ClassSession.id == Attendance.session_id)
        .join(Subject, Subject.id == ClassSession.subject_id)
        .filter(Attendance.student_id == uid)
        .order_by(Attendance.marked_at.desc())
        .limit(50)
    ).all()
    
    return jsonify({"records": [{
        "marked_at": r.marked_at.strftime("%Y-%m-%d %H:%M"),
        "session_code": r.code,
        "subject": r.subject_name
    } for r in rows]})
