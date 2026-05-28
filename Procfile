<<<<<<< HEAD
web: flask --app app.py db upgrade && gunicorn app:app --workers 1 --threads 4 --timeout 75 --max-requests 1000 --max-requests-jitter 100 --bind 0.0.0.0:$PORT
=======
web: gunicorn app:app --workers 1 --threads 4 --timeout 75 --max-requests 1000 --max-requests-jitter 100 --bind 0.0.0.0:$PORT
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
