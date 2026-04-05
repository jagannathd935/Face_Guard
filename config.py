import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DATABASE_PATH = os.path.join(INSTANCE_DIR, "faceguard.db")
FACE_MODEL_DIR = os.path.join(INSTANCE_DIR, "face_models")


def env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "")
    if not v:
        return default
    return v.lower() in ("1", "true", "yes", "on")


# face_recognition HOG on full-HD is extremely slow; registration uses LBPH by default.
USE_FR_ON_REGISTER = env_bool("FACEGUARD_FR_ON_REGISTER", False)

SECRET_KEY = os.environ.get("FACEGUARD_SECRET_KEY", "dev-change-me-in-production")
SESSION_CODE_TTL_MINUTES = int(os.environ.get("FACEGUARD_SESSION_TTL", "10"))
FACE_MATCH_TOLERANCE = float(os.environ.get("FACEGUARD_FACE_TOLERANCE", "0.55"))
# LBPH: lower distance = better match (typical same-person < 70–90)
LBPH_MATCH_MAX_DISTANCE = float(os.environ.get("FACEGUARD_LBPH_MAX_DIST", "85"))
LIVENESS_TOKEN_SECONDS = 90
