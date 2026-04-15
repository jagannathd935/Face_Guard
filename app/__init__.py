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
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["DATABASE"] = DATABASE_PATH
    app.config["FACE_MODEL_DIR"] = FACE_MODEL_DIR

    is_production = os.environ.get("RENDER") == "true" or os.environ.get("FLASK_ENV") == "production"
    app.config["SESSION_COOKIE_SECURE"] = is_production
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax" if not is_production else "None"

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

    from flask import request, jsonify
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(Exception)
    def handle_exception(e):
        if request.path.startswith('/api/'):
            if isinstance(e, HTTPException):
                return jsonify({"error": e.description}), e.code
            import logging
            logging.error(f"API Error: {e}", exc_info=True)
            return jsonify({"error": "Internal Server Error: " + str(e)}), 500

        if isinstance(e, HTTPException):
            return e

        return "Internal Server Error", 500

    return app
