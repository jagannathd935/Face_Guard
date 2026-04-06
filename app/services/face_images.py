from __future__ import annotations

import base64
import os

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions

# Path to the downloaded model
_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models", "blaze_face_short_range.tflite"))


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


def _detect_faces(bgr: np.ndarray):
    """Run MediaPipe FaceDetector (Tasks API) on a BGR image."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=_MODEL_PATH),
        min_detection_confidence=0.5,
    )
    with FaceDetector.create_from_options(options) as detector:
        result = detector.detect(mp_image)
    return result.detections


def largest_face_gray(bgr: np.ndarray) -> np.ndarray | None:
    if bgr is None or bgr.size == 0:
        return None

    h, w = bgr.shape[:2]
    max_w = 640
    if w > max_w:
        s = max_w / float(w)
        bgr = cv2.resize(bgr, (max_w, int(h * s)), interpolation=cv2.INTER_AREA)
        h, w = bgr.shape[:2]

    detections = _detect_faces(bgr)

    if not detections:
        return None

    # Pick the largest face
    best = None
    max_area = 0
    for det in detections:
        bbox = det.bounding_box
        area = bbox.width * bbox.height
        if area > max_area:
            max_area = area
            best = bbox

    if best is None:
        return None

    # Add 15% padding around the face
    pad_w = int(best.width * 0.15)
    pad_h = int(best.height * 0.15)

    xmin = max(0, best.origin_x - pad_w)
    ymin = max(0, best.origin_y - pad_h)
    xmax = min(w, best.origin_x + best.width + pad_w)
    ymax = min(h, best.origin_y + best.height + pad_h)

    if xmax <= xmin or ymax <= ymin:
        return None

    roi = bgr[ymin:ymax, xmin:xmax]
    if roi.size == 0:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    return cv2.resize(gray, (200, 200), interpolation=cv2.INTER_AREA)
