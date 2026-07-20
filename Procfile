release: python migrate_db.py && python seed_data.py
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile -
