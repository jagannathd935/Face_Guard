import os

from flask import Flask

from config import BASE_DIR, DATABASE_PATH, FACE_MODEL_DIR, INSTANCE_DIR, SECRET_KEY


def create_app():
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    os.makedirs(FACE_MODEL_DIR, exist_ok=True)

    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    app.config.from_object('config')

    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)

    is_production = os.environ.get("RENDER") == "true" or os.environ.get("FLASK_ENV") == "production"
    app.config["SESSION_COOKIE_SECURE"] = is_production
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax" if not is_production else "Strict" # Enhanced security

    from app import db
    db.init_app(app)

    from app.blueprints import auth_bp, sessions_bp, face_bp, attendance_bp, export_bp, pages_bp, admin_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(sessions_bp, url_prefix="/api")
    app.register_blueprint(face_bp, url_prefix="/api")
    app.register_blueprint(attendance_bp, url_prefix="/api")
    app.register_blueprint(export_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    # Exclude API from CSRF since it's meant to be stateless or handled via custom header if needed.
    # Actually, for AJAX-based session auth, we should handle CSRF. 
    # But since current frontend doesn't have it, I'll keep it for now but the user wants it.
    # I will exempt the pages for now or let the user handle tokens.
    # Actually, the user specifically mentioned CSRF risk. I'll enable it for API too.

    from flask import request, jsonify
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(Exception)
    def handle_exception(e):
        if request.path.startswith('/api/'):
            if isinstance(e, HTTPException):
                return jsonify({"error": e.description}), e.code
            import logging
            logging.error(f"API Error: {e}", exc_info=True)
            # Fix P1: API error info leak
            msg = "Internal Server Error"
            if app.debug:
                msg += ": " + str(e)
            return jsonify({"error": msg}), 500

        if isinstance(e, HTTPException):
            return e

        return "Internal Server Error", 500

    return app

