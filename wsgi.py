"""Gunicorn entrypoint for production deployment."""
from app import app

if __name__ == "__main__":
    # Run via gunicorn in production: gunicorn -w 2 -b 127.0.0.1:5071 wsgi:app
    pass
