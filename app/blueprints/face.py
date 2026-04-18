import os
from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import select
from app.blueprints.auth import login_required
from app.db import db
from app.db_models import FaceProfile
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

    gray_faces, fr_encodings = [], []
    with _create_face_detector() as detector:
        for b64 in images[:6]:
            img = b64_to_bgr_image(b64)
            if img is not None:
                g = largest_face_gray(img, detector=detector)
                if g is not None: gray_faces.append(g)
                if USE_FR_ON_REGISTER and face_fr_optional.HAS_FACE_RECOGNITION:
                    enc = face_fr_optional.encoding_from_bgr(img)
                    if enc is not None: fr_encodings.append(enc)

    if not gray_faces and not fr_encodings:
        return jsonify({"error": "No face detected"}), 400

    uid = session["user_id"]
    model_dir = current_app.config["FACE_MODEL_DIR"]
    rel_name = f"{uid}.yml"
    
    fr_json = None
    if face_fr_optional.HAS_FACE_RECOGNITION and fr_encodings:
        avg = face_fr_optional.average_encodings(fr_encodings)
        if avg is not None: fr_json = face_fr_optional.encoding_to_json(avg)

    lbph_rel = None
    if gray_faces:
        rec = train_lbph(gray_faces)
        save_model(rec, os.path.join(model_dir, rel_name))
        lbph_rel = rel_name

    if not lbph_rel and not fr_json:
        return jsonify({"error": "Could not build profile"}), 400

    try:
        prof = db.session.get(FaceProfile, uid)
        if prof:
            if fr_json: prof.fr_encoding_json = fr_json
            if lbph_rel: prof.lbph_model_relpath = lbph_rel
        else:
            prof = FaceProfile(user_id=uid, fr_encoding_json=fr_json, lbph_model_relpath=lbph_rel)
            db.session.add(prof)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error: {e}"}), 500

    return jsonify({
        "ok": True, "lbph_samples": len(gray_faces), "fr_samples": len(fr_encodings),
        "face_recognition_lib": face_fr_optional.HAS_FACE_RECOGNITION
    })

@bp.route("/face/status", methods=["GET"])
@login_required("student")
def face_status():
    prof = db.session.get(FaceProfile, session["user_id"])
    ok = prof and (prof.lbph_model_relpath or prof.fr_encoding_json)
    return jsonify({"registered": bool(ok)})
