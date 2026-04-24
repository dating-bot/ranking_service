import asyncio
import json

import grpclib.client
import structlog
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from external_clients.profile_api.v1.profile_grpc import ProfileServiceStub
from external_clients.profile_api.v1.profile_pb2 import GetPreferencesRequest, GetProfileRequest
from ranking_service.adapters.interaction_staging.postgres.adapter import PostgresInteractionStagingRepositoryAdapter
from ranking_service.adapters.rating.postgres.adapter import PostgresRatingRepositoryAdapter
from ranking_service.app.celery import celery_app
from ranking_service.infra.config import GlobalConfig
from ranking_service.infra.valkey import ValkeyClient
from ranking_service.usecases.sync_profile_to_ranking import map_gender_pref_to_domain

log = structlog.stdlib.get_logger("ranking_service.tasks.prefetch_ranked_queue")

RANKED_QUEUE_KEY_PREFIX = "ranking:queue"
RANKED_QUEUE_TTL = 3600


async def _prefetch_for_viewer(viewer_id: int, limit: int = 10) -> int:
    config = GlobalConfig.load()
    engine = create_async_engine(config.postgres.url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    profile_channel = grpclib.client.Channel(host=config.profile_service.host, port=config.profile_service.port)

    try:
        rating_repo = PostgresRatingRepositoryAdapter(session_factory=session_factory)
        interaction_repo = PostgresInteractionStagingRepositoryAdapter(session_factory=session_factory)
        profile_stub = ProfileServiceStub(profile_channel)

        queue_key = f"{RANKED_QUEUE_KEY_PREFIX}:{viewer_id}"

        async with rating_repo.context() as session:
            exclude_ids = await interaction_repo.list_target_ids_for_actor(session, viewer_id)
            all_exclude_ids = list(set(exclude_ids) | {viewer_id})
            viewer_profile = await profile_stub.GetProfile(GetProfileRequest(telegram_id=viewer_id))
            viewer_prefs = await profile_stub.GetPreferences(GetPreferencesRequest(telegram_id=viewer_id))

            candidates: list = []
            if viewer_profile.found and viewer_profile.HasField("latitude") and viewer_profile.HasField("longitude"):
                candidates = await rating_repo.get_ranked_candidates(
                    session,
                    viewer_id=viewer_id,
                    user_lat=viewer_profile.latitude,
                    user_lon=viewer_profile.longitude,
                    gender_pref=map_gender_pref_to_domain(viewer_prefs.gender_pref) if viewer_prefs.found else None,
                    age_min=viewer_prefs.age_min if viewer_prefs.found and viewer_prefs.age_min else 18,
                    age_max=viewer_prefs.age_max if viewer_prefs.found and viewer_prefs.age_max else 100,
                    radius_km=float(viewer_prefs.max_distance_km)
                    if viewer_prefs.found and viewer_prefs.max_distance_km
                    else 50.0,
                    limit=limit,
                    exclude_ids=exclude_ids,
                )

            if not candidates:
                log.debug(
                    "no geo-filtered candidates, falling back to top candidates",
                    viewer_id=viewer_id,
                )
                candidates = await rating_repo.list_top_candidates(
                    session, limit=limit, exclude_ids=all_exclude_ids
                )

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
        profile_channel.close()
        await engine.dispose()


@shared_task(bind=True, app=celery_app)
def prefetch_ranked_queue(self, viewer_id: int, limit: int = 10) -> dict[str, int]:
    count = asyncio.run(_prefetch_for_viewer(viewer_id, limit))
    return {"viewer_id": viewer_id, "candidates_pushed": count}
