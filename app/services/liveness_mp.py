from __future__ import annotations

import os

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions

# Path to the downloaded model
_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models", "face_landmarker.task"))


def _get_landmarks(bgr: np.ndarray):
    """Run FaceLandmarker (Tasks API) and return landmarks for the first face."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_MODEL_PATH),
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    with FaceLandmarker.create_from_options(options) as landmarker:
        result = landmarker.detect(mp_image)

    if not result.face_landmarks:
        return None
    return result.face_landmarks[0]


def _lm_point(lm, w: int, h: int):
    return np.array([lm.x * w, lm.y * h], dtype=np.float64)


# Six points per eye (order matches common EAR geometry)
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]


def _ear_from_points(pts: list[np.ndarray]) -> float:
    if len(pts) < 6:
        return 0.0
    a = np.linalg.norm(pts[1] - pts[5])
    b = np.linalg.norm(pts[2] - pts[4])
    c = np.linalg.norm(pts[0] - pts[3])
    if c < 1e-6:
        return 0.0
    return (a + b) / (2.0 * c)


def ear_for_bgr(bgr: np.ndarray) -> float | None:
    if bgr is None or bgr.size == 0:
        return None
    h, w = bgr.shape[:2]
    landmarks = _get_landmarks(bgr)
    if landmarks is None:
        return None
    le = [_lm_point(landmarks[i], w, h) for i in LEFT_EYE]
    re = [_lm_point(landmarks[i], w, h) for i in RIGHT_EYE]
    return float((_ear_from_points(le) + _ear_from_points(re)) / 2.0)


def detect_blink_in_frames(bgr_frames: list[np.ndarray], ear_open=0.22, ear_closed=0.19) -> bool:
    ears = []
    for f in bgr_frames:
        e = ear_for_bgr(f)
        if e is not None:
            ears.append(e)
    if len(ears) < 4:
        return False
    saw_low = False
    for i, e in enumerate(ears):
        if e < ear_closed:
            saw_low = True
        if saw_low and e >= ear_open and i > 0 and ears[i - 1] < ear_open:
            return True
    return False


def head_pose_hint(bgr: np.ndarray) -> str | None:
    """Nose vs cheek: rough left/right turn for optional pose challenge."""
    if bgr is None or bgr.size == 0:
        return None
    h, w = bgr.shape[:2]
    landmarks = _get_landmarks(bgr)
    if landmarks is None:
        return None
    nose = _lm_point(landmarks[1], w, h)
    left_cheek = _lm_point(landmarks[234], w, h)
    right_cheek = _lm_point(landmarks[454], w, h)
    mid_x = (left_cheek[0] + right_cheek[0]) / 2
    if nose[0] < mid_x - w * 0.02:
        return "left"
    if nose[0] > mid_x + w * 0.02:
        return "right"
    return "center"
