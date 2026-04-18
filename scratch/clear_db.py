from app import create_app
from app.db import db

app = create_app()
with app.app_context():
    print("Dropping all tables...")
    db.drop_all()
    print("Re-creating all tables with a clean schema...")
    db.create_all()
    print("Database cleared successfully.")
