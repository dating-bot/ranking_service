import asyncio

import structlog
from celery import Group, shared_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ranking_service.adapters.rating.postgres.adapter import PostgresRatingRepositoryAdapter
from ranking_service.infra.config import GlobalConfig
from ranking_service.usecases.calc_combined.usecase import CalcCombinedScore

log = structlog.stdlib.get_logger("ranking_service.tasks.recalculate_ratings")

DEFAULT_TOTAL_SHARDS = 10


async def _process_shard(shard: int, total_shards: int) -> int:
    config = GlobalConfig.load()
    engine = create_async_engine(config.postgres.url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        rating_repo = PostgresRatingRepositoryAdapter(session_factory=session_factory)
        calc_combined = CalcCombinedScore[AsyncSession](rating_repository=rating_repo)

        processed = 0
        async with rating_repo.context() as session:
            profiles = await rating_repo.list_profiles_for_shard(session, shard=shard, total_shards=total_shards)

        for profile in profiles:
            try:
                await calc_combined.execute(
                    CalcCombinedScore.Request(
                        telegram_id=profile.telegram_id,
                        primary_score=profile.primary_score,
                        behavioral_score=profile.behavioral_score,
                        referral_score=0.0,
                        semantic_bonus=0.0,
                    )
                )
                processed += 1
            except Exception as e:
                log.exception(
                    "failed to recalculate combined score",
                    telegram_id=profile.telegram_id,
                    shard=shard,
                    err=e,
                )

        log.info("shard processed", shard=shard, total=processed)
        return processed
    finally:
        await engine.dispose()


@shared_task
def recalculate_ratings(shard: int, total: int = DEFAULT_TOTAL_SHARDS) -> dict[str, int]:
    processed = asyncio.run(_process_shard(shard, total))
    log.info("recalculate_ratings completed", shard=shard, processed=processed)
    return {"shard": shard, "processed": processed}


@shared_task
def recalculate_ratings_batch() -> dict[str, object]:
    total_shards = DEFAULT_TOTAL_SHARDS
    group_tasks = [recalculate_ratings.s(shard=i, total=total_shards) for i in range(total_shards)]
    result = Group(group_tasks).apply_async()
    log.info("recalculate_ratings_batch dispatched", total_shards=total_shards)
    return {"total_shards": total_shards, "group_id": str(result.id)}
