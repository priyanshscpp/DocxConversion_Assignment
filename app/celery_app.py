"""
Celery Configuration for Asynchronous Task Processing

Celery is used to process DOCX to PDF conversions in the background.
This allows the API to return immediately without waiting for conversions.

Architecture:
- Broker (Redis): Stores task queue
- Backend (Redis): Stores task results
- Workers: Execute tasks (run via: celery -A app.celery_app worker)
"""

from celery import Celery
from app.config import settings

# Create Celery application instance
celery_app = Celery(
    "worker",                    # Application name
    broker=settings.REDIS_URL,   # Message broker (task queue)
    backend=settings.REDIS_URL   # Result backend (task results storage)
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",      # Serialize tasks as JSON
    accept_content=["json"],     # Only accept JSON content
    result_serializer="json",    # Serialize results as JSON
    timezone="UTC",              # Use UTC timezone
    enable_utc=True,             # Enable UTC
    
    # Import task modules
    # These modules contain @celery_app.task decorated functions
    imports=["app.tasks", "app.finalize_task"]
)
