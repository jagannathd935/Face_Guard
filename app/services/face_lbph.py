from __future__ import annotations

import os

import cv2
import numpy as np


def train_lbph(gray_faces: list[np.ndarray]) -> cv2.face.LBPHFaceRecognizer:
    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=1, neighbors=8, grid_x=8, grid_y=8, threshold=500.0
    )
    labels = np.zeros(len(gray_faces), dtype=np.int32)
    recognizer.train(gray_faces, labels)
    return recognizer


def save_model(recognizer: cv2.face.LBPHFaceRecognizer, abs_path: str) -> None:
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    recognizer.write(abs_path)


def load_model(abs_path: str) -> cv2.face.LBPHFaceRecognizer | None:
    if not os.path.isfile(abs_path):
        return None
    r = cv2.face.LBPHFaceRecognizer_create()
    r.read(abs_path)
    return r


def lbph_distance(recognizer: cv2.face.LBPHFaceRecognizer, gray_face: np.ndarray) -> float | None:
    if gray_face is None or gray_face.size == 0:
        return None
    _label, dist = recognizer.predict(gray_face)
    return float(dist)
