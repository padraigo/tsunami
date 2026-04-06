"""Celery application instance."""

from celery import Celery

from tsunami.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "tsunami",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
    )
    app.autodiscover_tasks(["tsunami.workers"])
    return app


celery_app = create_celery_app()
