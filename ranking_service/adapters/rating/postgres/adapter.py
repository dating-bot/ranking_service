from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import final, override

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ranking_service.adapters.postgres_models.models import (
    BehavioralRatingORM,
    CombinedRatingORM,
    PrimaryRatingORM,
)
from ranking_service.domain import BehavioralRating, CombinedRating, PrimaryRating, RankedCandidate
from ranking_service.infra.postgres import AsyncSessionFactory
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol

BOOST_MULTIPLIER = 3.0


@final
class PostgresRatingRepositoryAdapter(RatingRepositoryProtocol[AsyncSession]):
    def __init__(
        self,
        *,
        session_factory: AsyncSessionFactory,
        session_factory_replica: AsyncSessionFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._session_factory_replica = session_factory_replica or session_factory

    @override
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[AsyncSession]:
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @override
    async def insert_primary_rating(
        self, session: AsyncSession, request: RatingRepositoryProtocol.InsertPrimaryRatingRequest
    ) -> PrimaryRating:
        result = await session.execute(
            sa
            .insert(PrimaryRatingORM)
            .values(
                telegram_id=request.telegram_id,
                score=request.score,
                rank_percentile=request.rank_percentile,
            )
            .returning(
                PrimaryRatingORM.id,
                PrimaryRatingORM.telegram_id,
                PrimaryRatingORM.score,
                PrimaryRatingORM.rank_percentile,
                PrimaryRatingORM.updated_at,
            )
        )
        row = result.mappings().one()
        return PrimaryRating(
            id=row["id"],
            telegram_id=row["telegram_id"],
            score=row["score"],
            rank_percentile=row["rank_percentile"],
            updated_at=row["updated_at"],
        )

    @override
    async def upsert_primary(
        self, session: AsyncSession, request: RatingRepositoryProtocol.UpsertPrimaryRatingRequest
    ) -> PrimaryRating:
        result = await session.execute(
            pg_insert(PrimaryRatingORM)
            .values(
                telegram_id=request.telegram_id,
                score=request.score,
                rank_percentile=request.rank_percentile,
                latitude=request.latitude,
                longitude=request.longitude,
                age=request.age,
                gender=request.gender,
                boost_expires_at=request.boost_expires_at,
            )
            .on_conflict_do_update(
                index_elements=["telegram_id"],
                set_={
                    "score": request.score,
                    "rank_percentile": request.rank_percentile,
                    "latitude": request.latitude,
                    "longitude": request.longitude,
                    "age": request.age,
                    "gender": request.gender,
                    "boost_expires_at": request.boost_expires_at,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(
                PrimaryRatingORM.id,
                PrimaryRatingORM.telegram_id,
                PrimaryRatingORM.score,
                PrimaryRatingORM.rank_percentile,
                PrimaryRatingORM.age,
                PrimaryRatingORM.gender,
                PrimaryRatingORM.boost_expires_at,
                PrimaryRatingORM.updated_at,
            )
        )
        row = result.mappings().one()
        return PrimaryRating(
            id=row["id"],
            telegram_id=row["telegram_id"],
            score=row["score"],
            rank_percentile=row["rank_percentile"],
            age=row["age"],
            gender=row["gender"],
            boost_expires_at=row["boost_expires_at"],
            updated_at=row["updated_at"],
        )

    @override
    async def upsert_behavioral(
        self, session: AsyncSession, request: RatingRepositoryProtocol.UpsertBehavioralRatingRequest
    ) -> BehavioralRating:
        result = await session.execute(
            pg_insert(BehavioralRatingORM)
            .values(
                telegram_id=request.telegram_id,
                engagement_score=request.engagement_score,
                response_rate=request.response_rate,
                avg_response_time_seconds=request.avg_response_time_seconds,
            )
            .on_conflict_do_update(
                index_elements=["telegram_id"],
                set_={
                    "engagement_score": request.engagement_score,
                    "response_rate": request.response_rate,
                    "avg_response_time_seconds": request.avg_response_time_seconds,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(
                BehavioralRatingORM.id,
                BehavioralRatingORM.telegram_id,
                BehavioralRatingORM.engagement_score,
                BehavioralRatingORM.response_rate,
                BehavioralRatingORM.avg_response_time_seconds,
                BehavioralRatingORM.updated_at,
            )
        )
        row = result.mappings().one()
        return BehavioralRating(
            id=row["id"],
            telegram_id=row["telegram_id"],
            engagement_score=row["engagement_score"],
            response_rate=row["response_rate"],
            avg_response_time_seconds=row["avg_response_time_seconds"],
            updated_at=row["updated_at"],
        )

    @override
    async def get_behavioral_rating(self, session: AsyncSession, telegram_id: int) -> BehavioralRating | None:
        result = await session.execute(
            sa.select(BehavioralRatingORM).where(BehavioralRatingORM.telegram_id == telegram_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return row.to_domain()

    @override
    async def upsert_combined_rating(
        self, session: AsyncSession, request: RatingRepositoryProtocol.UpsertCombinedRatingRequest
    ) -> CombinedRating:
        result = await session.execute(
            pg_insert(CombinedRatingORM)
            .values(
                telegram_id=request.telegram_id,
                primary_score=request.primary_score,
                behavioral_score=request.behavioral_score,
                combined_score=request.combined_score,
            )
            .on_conflict_do_update(
                index_elements=["telegram_id"],
                set_={
                    "primary_score": request.primary_score,
                    "behavioral_score": request.behavioral_score,
                    "combined_score": request.combined_score,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(
                CombinedRatingORM.id,
                CombinedRatingORM.telegram_id,
                CombinedRatingORM.primary_score,
                CombinedRatingORM.behavioral_score,
                CombinedRatingORM.combined_score,
                CombinedRatingORM.status,
                CombinedRatingORM.created_at,
                CombinedRatingORM.updated_at,
            )
        )
        row = result.mappings().one()
        return CombinedRating(
            id=row["id"],
            telegram_id=row["telegram_id"],
            primary_score=row["primary_score"],
            behavioral_score=row["behavioral_score"],
            combined_score=row["combined_score"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @override
    async def get_combined_rating(self, session: AsyncSession, telegram_id: int) -> CombinedRating | None:
        result = await session.execute(sa.select(CombinedRatingORM).where(CombinedRatingORM.telegram_id == telegram_id))
        row = result.first()
        if row is None:
            return None
        return row.to_domain()

    @override
    async def list_top_candidates(
        self, session: AsyncSession, *, limit: int = 100, exclude_ids: list[int] | None = None
    ) -> list[RankedCandidate]:
        query = (
            sa
            .select(
                CombinedRatingORM.telegram_id,
                CombinedRatingORM.combined_score,
            )
            .where(CombinedRatingORM.status == "active")
            .order_by(CombinedRatingORM.combined_score.desc())
            .limit(limit)
        )
        if exclude_ids:
            query = query.where(CombinedRatingORM.telegram_id.not_in(exclude_ids))

        result = await session.execute(query)
        candidates = []
        for rank, row in enumerate(result.all(), start=1):
            candidates.append(
                RankedCandidate(
                    telegram_id=row.telegram_id,
                    combined_score=row.combined_score,
                    rank=rank,
                    reason="top_score",
                )
            )
        return candidates

    @override
    async def get_ranked_candidates(
        self,
        session: AsyncSession,
        *,
        viewer_id: int,
        user_lat: float,
        user_lon: float,
        gender_pref: str | None,
        age_min: int,
        age_max: int,
        radius_km: float = 50.0,
        limit: int = 100,
        exclude_ids: list[int] | None = None,
    ) -> list[RankedCandidate]:
        distance_m = radius_km * 1000

        dwithin_filter = sa.text("""
            ST_DWithin(
                ST_MakePoint(primary_ratings.longitude, primary_ratings.latitude)::geography,
                ST_MakePoint(:user_lon, :user_lat)::geography,
                :distance
            )
        """)

        score_multiplier = sa.text("""
            CASE
                WHEN primary_ratings.boost_expires_at IS NOT NULL
                     AND primary_ratings.boost_expires_at > NOW()
                     AND ST_DWithin(
                         ST_MakePoint(primary_ratings.longitude, primary_ratings.latitude)::geography,
                         ST_MakePoint(:user_lon, :user_lat)::geography,
                         :distance
                     )
                THEN 3.0 * 1.2
                WHEN primary_ratings.boost_expires_at IS NOT NULL
                     AND primary_ratings.boost_expires_at > NOW()
                THEN 3.0
                WHEN ST_DWithin(
                         ST_MakePoint(primary_ratings.longitude, primary_ratings.latitude)::geography,
                         ST_MakePoint(:user_lon, :user_lat)::geography,
                         :distance
                     )
                THEN 1.2
                ELSE 1.0
            END
        """)

        all_exclude_ids = set(exclude_ids) if exclude_ids else set()
        all_exclude_ids.add(viewer_id)

        filters: list[object] = [
            CombinedRatingORM.status == "active",
            dwithin_filter.bindparams(user_lat=user_lat, user_lon=user_lon, distance=distance_m),
            PrimaryRatingORM.age >= age_min,
            PrimaryRatingORM.age <= age_max,
        ]
        if gender_pref not in (None, "", "any"):
            filters.append(PrimaryRatingORM.gender == gender_pref)

        query = (
            sa
            .select(
                CombinedRatingORM.telegram_id,
                CombinedRatingORM.combined_score,
                (
                    CombinedRatingORM.combined_score
                    * score_multiplier.bindparams(user_lat=user_lat, user_lon=user_lon, distance=distance_m)
                ).label("boosted_score"),
            )
            .join(PrimaryRatingORM, CombinedRatingORM.telegram_id == PrimaryRatingORM.telegram_id)
            .where(*filters)
        )

        if all_exclude_ids:
            query = query.where(CombinedRatingORM.telegram_id.not_in(list(all_exclude_ids)))

        query = query.order_by(sa.desc("boosted_score")).limit(limit)

        result = await session.execute(query, {"user_lat": user_lat, "user_lon": user_lon, "distance": distance_m})

        candidates = []
        for rank, row in enumerate(result.all(), start=1):
            boost = row.boosted_score / row.combined_score if row.combined_score > 0 else 1.0
            if boost >= BOOST_MULTIPLIER:
                reason = "boosted+nearby"
            elif boost > 1.0:
                reason = "nearby_boost"
            else:
                reason = "top_score"
            candidates.append(
                RankedCandidate(
                    telegram_id=row.telegram_id,
                    combined_score=row.boosted_score,
                    rank=rank,
                    reason=reason,
                )
            )
        return candidates

    @override
    async def list_profiles_for_shard(
        self, session: AsyncSession, *, shard: int, total_shards: int
    ) -> list[RatingRepositoryProtocol.ProfileRatingData]:
        query = (
            sa
            .select(
                PrimaryRatingORM.telegram_id,
                PrimaryRatingORM.score.label("primary_score"),
                sa.coalesce(BehavioralRatingORM.engagement_score, 0.0).label("behavioral_score"),
            )
            .outerjoin(
                BehavioralRatingORM,
                PrimaryRatingORM.telegram_id == BehavioralRatingORM.telegram_id,
            )
            .where(PrimaryRatingORM.telegram_id % total_shards == shard)
        )

        result = await session.execute(query)
        return [
            RatingRepositoryProtocol.ProfileRatingData(
                telegram_id=row.telegram_id,
                primary_score=row.primary_score,
                behavioral_score=row.behavioral_score,
            )
            for row in result.all()
        ]
