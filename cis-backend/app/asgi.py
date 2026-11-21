"""Uvicorn entrypoint: `uvicorn app.asgi:app --port 8000`."""
from .main import create_app

app = create_app()
