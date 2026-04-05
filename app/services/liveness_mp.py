from __future__ import annotations

import cv2
import numpy as np

# MediaPipe Face Mesh (legacy API; stable for desktop demos)
import mediapipe as mp

_mp_mesh = None


def _mesh():
    global _mp_mesh
    if _mp_mesh is None:
        _mp_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return _mp_mesh


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
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    res = _mesh().process(rgb)
    if not res.multi_face_landmarks:
        return None
    lm = res.multi_face_landmarks[0].landmark
    le = [_lm_point(lm[i], w, h) for i in LEFT_EYE]
    re = [_lm_point(lm[i], w, h) for i in RIGHT_EYE]
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
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    res = _mesh().process(rgb)
    if not res.multi_face_landmarks:
        return None
    lm = res.multi_face_landmarks[0].landmark
    nose = _lm_point(lm[1], w, h)
    left_cheek = _lm_point(lm[234], w, h)
    right_cheek = _lm_point(lm[454], w, h)
    mid_x = (left_cheek[0] + right_cheek[0]) / 2
    if nose[0] < mid_x - w * 0.02:
        return "left"
    if nose[0] > mid_x + w * 0.02:
        return "right"
    return "center"
