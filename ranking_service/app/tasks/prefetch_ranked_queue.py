import asyncio
import json

import structlog
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ranking_service.adapters.rating.postgres.adapter import PostgresRatingRepositoryAdapter
from ranking_service.infra.config import GlobalConfig
from ranking_service.infra.valkey import ValkeyClient

log = structlog.stdlib.get_logger("ranking_service.tasks.prefetch_ranked_queue")

RANKED_QUEUE_KEY_PREFIX = "ranking:queue"
RANKED_QUEUE_TTL = 3600


async def _prefetch_for_viewer(viewer_id: int, limit: int = 10) -> int:
    config = GlobalConfig.load()
    engine = create_async_engine(config.postgres.url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        rating_repo = PostgresRatingRepositoryAdapter(session_factory=session_factory)

        queue_key = f"{RANKED_QUEUE_KEY_PREFIX}:{viewer_id}"

        async with rating_repo.context() as session:
            candidates = await rating_repo.list_top_candidates(session, limit=limit)

        valkey_client = ValkeyClient(config.valkey, db=config.valkey.db_rankings)
        await valkey_client.initialize()
        try:
            await valkey_client.client.delete(queue_key)

            for candidate in reversed(candidates):
                data = json.dumps({
                    "telegram_id": candidate.telegram_id,
                    "combined_score": candidate.combined_score,
                    "rank": candidate.rank,
                    "reason": candidate.reason,
                })
                _ = await valkey_client.client.lpush(queue_key, data)

            if candidates:
                await valkey_client.client.expire(queue_key, RANKED_QUEUE_TTL)

            log.info(
                "prefetch_ranked_queue completed",
                viewer_id=viewer_id,
                candidates_pushed=len(candidates),
            )
            return len(candidates)
        finally:
            await valkey_client.close()
    finally:
        await engine.dispose()


@shared_task
def prefetch_ranked_queue(viewer_id: int, limit: int = 10) -> dict[str, int]:
    count = asyncio.run(_prefetch_for_viewer(viewer_id, limit))
    return {"viewer_id": viewer_id, "candidates_pushed": count}
