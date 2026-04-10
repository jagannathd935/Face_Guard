from app.blueprints.auth import bp as auth_bp
from app.blueprints.sessions import bp as sessions_bp
from app.blueprints.face import bp as face_bp
from app.blueprints.attendance import bp as attendance_bp
from app.blueprints.export_routes import bp as export_bp
from app.blueprints.pages import bp as pages_bp
from app.blueprints.admin import bp as admin_bp

__all__ = [
    "auth_bp",
    "sessions_bp",
    "face_bp",
    "attendance_bp",
    "export_bp",
    "pages_bp",
    "admin_bp",
]
