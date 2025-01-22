# migrations.py
from app import create_app, db
from app.models import User, Credential

app = create_app()

def init_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Database tables created successfully!")

if __name__ == "__main__":
    init_db()