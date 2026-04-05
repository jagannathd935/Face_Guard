import os
import sqlite3
import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, session

from app.blueprints.auth import login_required
from app.db import get_db
from app.services import face_fr_optional, liveness_mp
from app.services.face_images import b64_to_bgr_image, largest_face_gray
from app.services.face_lbph import load_model, lbph_distance
from config import FACE_MATCH_TOLERANCE, LBPH_MATCH_MAX_DISTANCE, LIVENESS_TOKEN_SECONDS

bp = Blueprint("attendance", __name__)


def _network_prefix_for_request():
    ip = request.remote_addr or ""
    parts = ip.split(".")
    if len(parts) >= 3:
        return ".".join(parts[:3])
    return ip or "unknown"


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
        if img is not None:
            bgrs.append(img)
    ok = liveness_mp.detect_blink_in_frames(bgrs)
    if not ok:
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
    ok = hint == expected
    if ok:
        session["liveness_verified_at"] = time.time()
    return jsonify({"ok": ok, "detected": hint})


def _verify_face_profile(prof, live_gray, live_bgr) -> tuple[bool, str, float | None]:
    lbph_path = prof["lbph_model_relpath"]
    fr_json = prof["fr_encoding_json"]
    model_dir = current_app.config["FACE_MODEL_DIR"]

    lbph_ok = None
    fr_ok = None
    dist_out = None

    if lbph_path:
        rec = load_model(os.path.join(model_dir, lbph_path))
        if rec is None:
            return False, "Face model missing on server", None
        d = lbph_distance(rec, live_gray)
        if d is None:
            return False, "Could not score face (LBPH)", None
        dist_out = d
        lbph_ok = d <= LBPH_MATCH_MAX_DISTANCE

    if fr_json and face_fr_optional.HAS_FACE_RECOGNITION:
        unk = face_fr_optional.encoding_from_bgr(live_bgr)
        if unk is None:
            return False, "No face detected for embedding check", dist_out
        stored = face_fr_optional.json_to_encoding(fr_json)
        match, fdist = face_fr_optional.match_encoding(unk, stored, FACE_MATCH_TOLERANCE)
        dist_out = fdist if dist_out is None else dist_out
        fr_ok = match

    if lbph_ok is None and fr_ok is None:
        return False, "No usable face verifier configured", None

    if lbph_ok is not None and fr_ok is not None:
        return (lbph_ok and fr_ok), "Face mismatch", dist_out
    if lbph_ok is not None:
        return lbph_ok, "Face does not match profile (LBPH)", dist_out
    return fr_ok, "Face does not match profile (embedding)", dist_out


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
        return jsonify({"error": "Liveness not verified or expired; blink again"}), 403

    db = get_db()
    student_id = session["user_id"]

    row = db.execute(
        """
        SELECT id, network_prefix, expires_at
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
        return jsonify({"error": "Session data invalid"}), 500
    if datetime.now(timezone.utc) > exp:
        return jsonify({"error": "Session expired"}), 410

    prefix = row["network_prefix"]
    student_prefix = _network_prefix_for_request()
    if prefix and student_prefix != prefix:
        return (
            jsonify(
                {
                    "error": "Network mismatch: join the same Wi‑Fi / subnet as the teacher",
                    "expected_prefix": prefix,
                    "your_prefix": student_prefix,
                }
            ),
            403,
        )

    join = db.execute(
        """
        SELECT 1 FROM session_joins
        WHERE session_id = ? AND student_id = ?
        """,
        (row["id"], student_id),
    ).fetchone()
    if not join:
        return jsonify({"error": "Join the session with the code first"}), 403

    prof = db.execute(
        """
        SELECT fr_encoding_json, lbph_model_relpath FROM face_profiles
        WHERE user_id = ?
        """,
        (student_id,),
    ).fetchone()
    if not prof or (not prof["lbph_model_relpath"] and not prof["fr_encoding_json"]):
        return jsonify({"error": "Register your face first"}), 403

    img = b64_to_bgr_image(image_b64)
    if img is None:
        return jsonify({"error": "Bad image"}), 400
    gray = largest_face_gray(img)
    if gray is None:
        return jsonify({"error": "No face detected"}), 400

    ok_face, reason, dist = _verify_face_profile(prof, gray, img)
    if not ok_face:
        body = {"ok": False, "error": reason}
        if dist is not None:
            body["distance"] = dist
        return jsonify(body), 400

    try:
        db.execute(
            """
            INSERT INTO attendance (session_id, student_id)
            VALUES (?, ?)
            """,
            (row["id"], student_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"ok": True, "duplicate": True, "message": "Already marked"}), 200

    session.pop("liveness_verified_at", None)
    resp = {"ok": True, "duplicate": False}
    if dist is not None:
        resp["distance"] = dist
    return jsonify(resp)


@bp.route("/attendance/session/<int:sid>", methods=["GET"])
@login_required("teacher")
def list_attendance(sid):
    db = get_db()
    owner = db.execute(
        "SELECT id FROM class_sessions WHERE id = ? AND teacher_id = ?",
        (sid, session["user_id"]),
    ).fetchone()
    if not owner:
        return jsonify({"error": "Not found"}), 404
    rows = db.execute(
        """
        SELECT a.student_id, u.username, a.marked_at
        FROM attendance a
        JOIN users u ON u.id = a.student_id
        WHERE a.session_id = ?
        ORDER BY a.marked_at
        """,
        (sid,),
    ).fetchall()
    return jsonify({"records": [dict(r) for r in rows]})
