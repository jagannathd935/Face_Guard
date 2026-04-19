from app import create_app
from app.db import db

app = create_app()
with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database has been reset to the original schema.")
