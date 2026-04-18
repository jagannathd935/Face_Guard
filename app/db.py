import flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def get_db():
    """
    Returns the database session.
    Note: Blueprints using get_db().execute() will need to be updated 
    to handle the SQLAlchemy Result object instead of psycopg2 cursor.
    """
    return db.session

def init_app(app):
    db.init_app(app)
    migrate.init_app(app, db)
    
    with app.app_context():
        # Ensure models are imported so they are registered
        from app import db_models
        db.create_all()
