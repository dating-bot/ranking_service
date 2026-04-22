from celery import Celery

celery_app = Celery(
    "ranking_service",
    broker="redis://localhost:6379/0",
    include=[
        "ranking_service.app.tasks.recalculate_ratings",
        "ranking_service.app.tasks.prefetch_ranked_queue",
    ],
)

celery_app.conf.beat_schedule = {
    "recalculate_ratings": {
        "task": "ranking_service.app.tasks.recalculate_ratings.recalculate_ratings_batch",
        "schedule": 900.0,
    },
}

celery_app.conf.timezone = "UTC"
