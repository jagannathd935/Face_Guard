from __future__ import annotations

import json

import cv2
import numpy as np

try:
    import face_recognition

    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False


def encoding_from_bgr(bgr):
    if not HAS_FACE_RECOGNITION or bgr is None or bgr.size == 0:
        return None
    h, w = bgr.shape[:2]
    max_dim = 640
    if max(h, w) > max_dim:
        s = max_dim / max(h, w)
        bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(
        rgb, model="hog", number_of_times_to_upsample=0
    )
    if not boxes:
        return None
    encs = face_recognition.face_encodings(rgb, boxes, num_jitters=1)
    return encs[0] if encs else None


def average_encodings(encodings: list) -> np.ndarray | None:
    if not encodings:
        return None
    return np.mean(np.stack(encodings, axis=0), axis=0)


def encoding_to_json(enc: np.ndarray) -> str:
    return json.dumps(enc.astype(float).tolist())


def json_to_encoding(s: str) -> np.ndarray:
    return np.array(json.loads(s), dtype=np.float64)


def match_encoding(unknown: np.ndarray, stored: np.ndarray, tolerance: float) -> tuple[bool, float]:
    if not HAS_FACE_RECOGNITION:
        return False, 999.0
    dist = float(face_recognition.face_distance([stored], unknown)[0])
    return dist <= tolerance, dist
