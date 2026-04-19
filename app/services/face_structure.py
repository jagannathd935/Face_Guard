import cv2
import numpy as np
import json
from app.services.liveness_mp import _get_landmarks, _lm_point

def calculate_facial_ratios(bgr_img):
    """
    Uses MediaPipe AI Landmarks to calculate structural biometric ratios.
    These are independent of lighting and focus on bone/facial structure.
    """
    landmarks = _get_landmarks(bgr_img)
    if not landmarks:
        return None

    try:
        # Key landmark indices (FaceMesh standard)
        l_eye = _lm_point(landmarks, 33)   # Left eye outer
        r_eye = _lm_point(landmarks, 263)  # Right eye outer
        nose_tip = _lm_point(landmarks, 1)   # Nose tip
        mouth_l = _lm_point(landmarks, 61)  # Left mouth corner
        mouth_r = _lm_point(landmarks, 291) # Right mouth corner
        chin = _lm_point(landmarks, 152)    # Chin bottom
        forehead = _lm_point(landmarks, 10) # Forehead top

        def dist(p1, p2):
            return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

        # 1. Inter-ocular Distance (IOD)
        iod = dist(l_eye, r_eye)
        if iod == 0: return None

        # Ratios (normalized by eye distance to be scale-invariant)
        ratios = {
            "eye_to_nose": round(dist(l_eye, nose_tip) / iod, 4),
            "mouth_width": round(dist(mouth_l, mouth_r) / iod, 4),
            "eye_to_mouth": round(dist(l_eye, mouth_l) / iod, 4),
            "face_height": round(dist(forehead, chin) / iod, 4),
            "nose_to_chin": round(dist(nose_tip, chin) / iod, 4)
        }
        return ratios
    except Exception:
        return None

def compare_structures(saved_ratios, live_ratios, threshold=0.15):
    """
    Compares two structural signatures. 
    Threshold 0.15 allows for 15% deviation in facial proportions.
    """
    if not saved_ratios or not live_ratios:
        return False, 1.0

    diffs = []
    for key in saved_ratios:
        if key in live_ratios:
            s_val = saved_ratios[key]
            l_val = live_ratios[key]
            if s_val == 0: continue
            diffs.append(abs(s_val - l_val) / s_val)
    
    if not diffs:
        return False, 1.0

    avg_diff = sum(diffs) / len(diffs)
    return (avg_diff <= threshold), avg_diff
