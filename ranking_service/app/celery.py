import os

from celery import Celery

from ranking_service.infra.tracing import setup_tracing

setup_tracing(service_name=os.getenv("OTEL_SERVICE_NAME", "ranking-service-celery"))

celery_app = Celery(
    "ranking_service",
    broker="redis://valkey:6379/0",
    include=[
        "ranking_service.app.tasks.recalculate_ratings",
        "ranking_service.app.tasks.prefetch_ranked_queue",
    ],
)

celery_app.conf.timezone = "UTC"
celery_app.conf.broker_url = "redis://valkey:6379/0"

# Make this the default app for shared_task
celery_app.set_default()
