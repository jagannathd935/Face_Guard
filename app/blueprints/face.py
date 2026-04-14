import os

from flask import Blueprint, current_app, jsonify, request, session

from app.blueprints.auth import login_required
from app.db import get_db
from config import USE_FR_ON_REGISTER
from app.services import face_fr_optional
from app.services.face_images import b64_to_bgr_image, largest_face_gray, _create_face_detector
from app.services.face_lbph import save_model, train_lbph

bp = Blueprint("face", __name__)


@bp.route("/face/register", methods=["POST"])
@login_required("student")
def register_face():
    data = request.get_json(silent=True) or {}
    images = data.get("images")
    if not images or not isinstance(images, list):
        return jsonify({"error": "images array (base64) required"}), 400

    gray_faces = []
    fr_encodings = []
    with _create_face_detector() as detector:
        for b64 in images[:6]:
            img = b64_to_bgr_image(b64)
            if img is None:
                continue
            g = largest_face_gray(img, detector=detector)
            if g is not None:
                gray_faces.append(g)
            if USE_FR_ON_REGISTER and face_fr_optional.HAS_FACE_RECOGNITION:
                enc = face_fr_optional.encoding_from_bgr(img)
                if enc is not None:
                    fr_encodings.append(enc)

    if len(gray_faces) < 1 and len(fr_encodings) < 1:
        return jsonify({"error": "No face detected in provided images"}), 400

    uid = session["user_id"]
    model_dir = current_app.config["FACE_MODEL_DIR"]
    rel_name = f"{uid}.yml"
    abs_model = os.path.join(model_dir, rel_name)

    fr_json = None
    if face_fr_optional.HAS_FACE_RECOGNITION and fr_encodings:
        avg = face_fr_optional.average_encodings(fr_encodings)
        if avg is not None:
            fr_json = face_fr_optional.encoding_to_json(avg)

    lbph_rel = None
    if gray_faces:
        rec = train_lbph(gray_faces)
        save_model(rec, abs_model)
        lbph_rel = rel_name

    if not lbph_rel and not fr_json:
        return jsonify({"error": "Could not build face profile"}), 400

    db = get_db()
    try:
        row = db.execute("SELECT user_id, fr_encoding_json, lbph_model_relpath FROM face_profiles WHERE user_id = ?", (uid,)).fetchone()
        if row:
            db.execute(
                """
                UPDATE face_profiles
                SET fr_encoding_json = ?, lbph_model_relpath = ?, updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (fr_json if fr_json else row["fr_encoding_json"], lbph_rel if lbph_rel else row["lbph_model_relpath"], uid)
            )
        else:
            db.execute(
                """
                INSERT INTO face_profiles (user_id, fr_encoding_json, lbph_model_relpath, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (uid, fr_json, lbph_rel)
            )
        db.commit()
    except Exception as e:
        db.rollback()
        import logging
        logging.error(f"Failed to upsert face profile for user {uid}: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500

    return jsonify(
        {
            "ok": True,
            "lbph_samples": len(gray_faces),
            "fr_samples": len(fr_encodings),
            "face_recognition_lib": face_fr_optional.HAS_FACE_RECOGNITION,
        }
    )


@bp.route("/face/status", methods=["GET"])
@login_required("student")
def face_status():
    db = get_db()
    row = db.execute(
        """
        SELECT fr_encoding_json, lbph_model_relpath FROM face_profiles
        WHERE user_id = ?
        """,
        (session["user_id"],),
    ).fetchone()
    ok = row and (row["lbph_model_relpath"] or row["fr_encoding_json"])
    return jsonify({"registered": bool(ok)})
