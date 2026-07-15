from flask import Flask
from .models import db

def init_app(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
        # Optionally seed initial data here or via separate script

def get_db():
    return db