from __future__ import annotations

import base64

import cv2
import numpy as np


def b64_to_bgr_image(b64_str: str) -> np.ndarray | None:
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    try:
        raw = base64.b64decode(b64_str)
    except Exception:
        return None
    arr = np.asarray(bytearray(raw), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


_cascade = None


def _cascade():
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _cascade


def largest_face_gray(bgr: np.ndarray) -> np.ndarray | None:
    if bgr is None or bgr.size == 0:
        return None
    h, w = bgr.shape[:2]
    max_w = 640
    if w > max_w:
        s = max_w / float(w)
        bgr = cv2.resize(bgr, (max_w, int(h * s)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = _cascade().detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    roi = gray[y : y + h, x : x + w]
    return cv2.resize(roi, (200, 200), interpolation=cv2.INTER_AREA)
