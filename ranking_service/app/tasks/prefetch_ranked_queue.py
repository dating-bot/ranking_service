import asyncio
import json
import uuid

import grpclib.client
import structlog
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from external_clients.profile_api.v1.profile_grpc import ProfileServiceStub
from external_clients.profile_api.v1.profile_pb2 import GetPreferencesRequest, GetProfileRequest
from ranking_service.adapters.interaction_staging.postgres.adapter import PostgresInteractionStagingRepositoryAdapter
from ranking_service.adapters.profile_insights.postgres.adapter import PostgresProfileInsightsAdapter
from ranking_service.adapters.rating.postgres.adapter import PostgresRatingRepositoryAdapter
from ranking_service.app.celery import celery_app
from ranking_service.domain import RankedCandidate
from ranking_service.infra.config import GlobalConfig
from ranking_service.infra.valkey import ValkeyClient
from ranking_service.protocols import ProfileInsightsProtocol
from ranking_service.usecases.calc_combined.usecase import COMBINED_WEIGHT_SEMANTIC
from ranking_service.usecases.sync_profile_to_ranking import map_gender_pref_to_domain

log = structlog.stdlib.get_logger("ranking_service.tasks.prefetch_ranked_queue")

RANKED_QUEUE_KEY_PREFIX = "ranking:queue"
RANKED_QUEUE_TTL = 3600
PREFETCH_LOCK_PREFIX = "ranking:prefetch:lock"
PREFETCH_LOCK_TTL = 30


async def _release_lock(client, lock_key: str, lock_value: str) -> None:
    _ = await client.eval(
        """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        end
        return 0
        """,
        1,
        lock_key,
        lock_value,
    )


async def _prefetch_for_viewer(viewer_id: int, limit: int = 10) -> int:  # noqa: PLR0915
    config = GlobalConfig.load()
    queue_key = f"{RANKED_QUEUE_KEY_PREFIX}:{viewer_id}"
    lock_key = f"{PREFETCH_LOCK_PREFIX}:{viewer_id}"
    lock_value = str(uuid.uuid4())
    valkey_client = ValkeyClient(config.valkey, db=config.valkey.db_rankings)
    await valkey_client.initialize()

    lock_acquired = await valkey_client.client.set(lock_key, lock_value, nx=True, ex=PREFETCH_LOCK_TTL)
    if not lock_acquired:
        log.debug("prefetch skipped due to lock", viewer_id=viewer_id)
        await valkey_client.close()
        return 0

    engine = create_async_engine(config.postgres.url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    profile_engine = create_async_engine(config.profile_postgres.url)
    profile_session_factory = async_sessionmaker(profile_engine, class_=AsyncSession, expire_on_commit=False)
    profile_channel = grpclib.client.Channel(host=config.profile_service.host, port=config.profile_service.port)

    try:
        rating_repo = PostgresRatingRepositoryAdapter(session_factory=session_factory)
        profile_insights = PostgresProfileInsightsAdapter(session_factory=profile_session_factory)
        interaction_repo = PostgresInteractionStagingRepositoryAdapter(session_factory=session_factory)
        profile_stub = ProfileServiceStub(profile_channel)

        async with rating_repo.context() as session:
            exclude_ids = await interaction_repo.list_target_ids_for_actor(session, viewer_id)
            all_exclude_ids = list(set(exclude_ids) | {viewer_id})
            viewer_profile = await profile_stub.GetProfile(GetProfileRequest(telegram_id=viewer_id))
            viewer_prefs = await profile_stub.GetPreferences(GetPreferencesRequest(telegram_id=viewer_id))

            candidates: list = []
            if viewer_profile.found and viewer_profile.HasField("latitude") and viewer_profile.HasField("longitude"):
                base_radius_km = (
                    float(viewer_prefs.max_distance_km)
                    if viewer_prefs.found and viewer_prefs.max_distance_km
                    else 50.0
                )
                for radius_km in (base_radius_km, max(base_radius_km, 200.0), 20_000.0):
                    candidates = await rating_repo.get_ranked_candidates(
                        session,
                        viewer_id=viewer_id,
                        user_lat=viewer_profile.latitude,
                        user_lon=viewer_profile.longitude,
                        gender_pref=map_gender_pref_to_domain(viewer_prefs.gender_pref) if viewer_prefs.found else None,
                        age_min=viewer_prefs.age_min if viewer_prefs.found and viewer_prefs.age_min else 18,
                        age_max=viewer_prefs.age_max if viewer_prefs.found and viewer_prefs.age_max else 100,
                        radius_km=radius_km,
                        limit=max(limit * 5, 50),
                        exclude_ids=exclude_ids,
                    )
                    if candidates:
                        break

            if not candidates:
                log.debug(
                    "no geo-filtered candidates, falling back to top candidates",
                    viewer_id=viewer_id,
                )
                candidates = await rating_repo.list_top_candidates(
                    session,
                    limit=max(limit * 5, 50),
                    exclude_ids=all_exclude_ids,
                )
        try:
            candidates = await _rerank_with_semantic(
                profile_insights=profile_insights,
                viewer_id=viewer_id,
                candidates=candidates,
                limit=limit,
            )
        except Exception:
            # Degrade gracefully: semantic insights are optional for candidate delivery.
            log.exception(
                "semantic rerank failed, falling back to base ranking",
                viewer_id=viewer_id,
            )
            candidates = candidates[:limit]
            for rank, candidate in enumerate(candidates, start=1):
                candidate.rank = rank
        if not candidates:
            await valkey_client.client.delete(queue_key)
            log.info(
                "prefetch_ranked_queue completed with empty candidate set",
                viewer_id=viewer_id,
            )
            return 0

        tmp_queue_key = f"{queue_key}:tmp:{uuid.uuid4().hex}"
        for candidate in candidates:
            data = json.dumps({
                "telegram_id": candidate.telegram_id,
                "combined_score": candidate.combined_score,
                "rank": candidate.rank,
                "reason": candidate.reason,
            })
            _ = await valkey_client.client.rpush(tmp_queue_key, data)
        await valkey_client.client.expire(tmp_queue_key, RANKED_QUEUE_TTL)
        await valkey_client.client.rename(tmp_queue_key, queue_key)
        await valkey_client.client.expire(queue_key, RANKED_QUEUE_TTL)

        log.info(
            "prefetch_ranked_queue completed",
            viewer_id=viewer_id,
            candidates_pushed=len(candidates),
        )
        return len(candidates)
    finally:
        try:
            await _release_lock(valkey_client.client, lock_key, lock_value)
        finally:
            await valkey_client.close()
        profile_channel.close()
        await profile_engine.dispose()
        await engine.dispose()


async def _rerank_with_semantic(
    *,
    profile_insights: ProfileInsightsProtocol,
    viewer_id: int,
    candidates: list[RankedCandidate],
    limit: int,
) -> list[RankedCandidate]:
    if not candidates:
        return []

    candidate_ids = [item.telegram_id for item in candidates]
    bonuses = await profile_insights.get_semantic_bonuses(
        viewer_telegram_id=viewer_id,
        candidate_telegram_ids=candidate_ids,
    )

    adjusted: list[tuple[float, RankedCandidate]] = []
    for candidate in candidates:
        semantic_bonus = bonuses.get(candidate.telegram_id, 0.0)
        semantic_contribution = COMBINED_WEIGHT_SEMANTIC * semantic_bonus * 100.0
        adjusted_score = candidate.combined_score + semantic_contribution
        reason = candidate.reason if semantic_bonus == 0.0 else f"{candidate.reason}+semantic"
        adjusted.append(
            (
                adjusted_score,
                RankedCandidate(
                    telegram_id=candidate.telegram_id,
                    combined_score=adjusted_score,
                    rank=0,
                    reason=reason,
                ),
            )
        )

    adjusted.sort(key=lambda item: item[0], reverse=True)
    top = [item[1] for item in adjusted[:limit]]
    for rank, candidate in enumerate(top, start=1):
        candidate.rank = rank
    return top


@shared_task(bind=True, app=celery_app)
def prefetch_ranked_queue(_self, viewer_id: int, limit: int = 10) -> dict[str, int]:
    count = asyncio.run(_prefetch_for_viewer(viewer_id, limit))
    return {"viewer_id": viewer_id, "candidates_pushed": count}
