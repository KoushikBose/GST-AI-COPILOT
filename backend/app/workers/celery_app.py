"""Celery application for background processing.

Used for work that must not block a request/response cycle: bulk invoice
processing, scheduled compliance scans, and report generation.

Single-invoice extraction runs as a FastAPI `BackgroundTask` (see
`app/api/v1/invoices.py::_process_invoice_upload`) so the upload request
returns immediately with a `processing` row and the frontend polls for the
result — good enough for a single-process deployment. Move it onto a
`.delay()` task here for multi-process / durable processing. Knowledge-
document ingestion still runs inline (see `IngestionService`).
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "gst_ai_copilot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    worker_max_tasks_per_child=200,
)

celery_app.conf.beat_schedule = {
    "nightly-compliance-scan": {
        "task": "app.workers.tasks.run_scheduled_compliance_scan",
        "schedule": 24 * 60 * 60,  # once a day; swap for crontab() for a fixed time
    },
}
