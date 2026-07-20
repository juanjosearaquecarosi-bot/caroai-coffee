"""WSGI entry point for gunicorn (Render / Railway / production).

Usage:
    gunicorn wsgi:app
"""
from app import create_app

app = create_app()
