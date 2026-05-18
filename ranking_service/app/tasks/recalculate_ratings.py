import asyncio

import grpclib.client
import structlog
from celery import group, shared_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from external_clients.profile_api.v1.profile_grpc import ProfileServiceStub
from ranking_service.adapters.profile_insights.postgres.adapter import PostgresProfileInsightsAdapter
from ranking_service.adapters.rating.postgres.adapter import PostgresRatingRepositoryAdapter
from ranking_service.app.celery import celery_app
from ranking_service.infra.config import GlobalConfig
from ranking_service.usecases.calc_combined.usecase import CalcCombinedScore
from ranking_service.usecases.calc_primary.usecase import CalcPrimaryScore
from ranking_service.usecases.sync_profile_to_ranking import SyncProfileToRanking

log = structlog.stdlib.get_logger("ranking_service.tasks.recalculate_ratings")

DEFAULT_TOTAL_SHARDS = 10


async def _process_shard(shard: int, total_shards: int) -> int:
    config = GlobalConfig.load()
    engine = create_async_engine(config.postgres.url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    profile_engine = create_async_engine(config.profile_postgres.url)
    profile_session_factory = async_sessionmaker(profile_engine, class_=AsyncSession, expire_on_commit=False)
    profile_channel = grpclib.client.Channel(host=config.profile_service.host, port=config.profile_service.port)

    try:
        rating_repo = PostgresRatingRepositoryAdapter(session_factory=session_factory)
        profile_insights = PostgresProfileInsightsAdapter(session_factory=profile_session_factory)
        calc_primary = CalcPrimaryScore[AsyncSession](rating_repository=rating_repo)
        calc_combined = CalcCombinedScore[AsyncSession](rating_repository=rating_repo)
        sync_profile = SyncProfileToRanking[AsyncSession](
            profile_stub=ProfileServiceStub(profile_channel),
            rating_repository=rating_repo,
            profile_insights=profile_insights,
            calc_primary_score=calc_primary,
            calc_combined_score=calc_combined,
        )

        processed = 0
        async with rating_repo.context() as session:
            profiles = await rating_repo.list_profiles_for_shard(session, shard=shard, total_shards=total_shards)

        for profile in profiles:
            try:
                synced = await sync_profile.execute(
                    SyncProfileToRanking.Request(
                        telegram_id=profile.telegram_id,
                        trace_id=f"recalculate:{shard}:{profile.telegram_id}",
                    )
                )
                if synced:
                    processed += 1
            except Exception as e:
                log.exception(
                    "failed to recalculate ratings via sync path",
                    telegram_id=profile.telegram_id,
                    shard=shard,
                    err=e,
                )

        log.info("shard processed", shard=shard, total=processed)
        return processed
    finally:
        profile_channel.close()
        await profile_engine.dispose()
        await engine.dispose()


@shared_task(bind=True, app=celery_app)
def recalculate_ratings(_self, shard: int, total: int = DEFAULT_TOTAL_SHARDS) -> dict[str, int]:
    processed = asyncio.run(_process_shard(shard, total))
    log.info("recalculate_ratings completed", shard=shard, processed=processed)
    return {"shard": shard, "processed": processed}


@shared_task(bind=True, app=celery_app)
def recalculate_ratings_batch(_self) -> dict[str, object]:
    total_shards = DEFAULT_TOTAL_SHARDS
    group_tasks = [recalculate_ratings.s(shard=i, total=total_shards) for i in range(total_shards)]
    result = group(group_tasks).apply_async()
    log.info("recalculate_ratings_batch dispatched", total_shards=total_shards)
    return {"total_shards": total_shards, "group_id": str(result.id)}
