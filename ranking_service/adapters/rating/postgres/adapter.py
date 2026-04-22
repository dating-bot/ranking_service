from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import final, override

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from ranking_service.adapters.postgres_models.models import (
    BehavioralRatingORM,
    CombinedRatingORM,
    PrimaryRatingORM,
)
from ranking_service.domain import BehavioralRating, CombinedRating, PrimaryRating, RankedCandidate
from ranking_service.infra.postgres import AsyncSessionFactory
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol


@final
class PostgresRatingRepositoryAdapter(RatingRepositoryProtocol[AsyncSession]):
    def __init__(self, *, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory

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
            sa
            .insert(PrimaryRatingORM)
            .values(
                telegram_id=request.telegram_id,
                score=request.score,
                rank_percentile=request.rank_percentile,
                latitude=request.latitude,
                longitude=request.longitude,
            )
            .on_conflict_do_update(
                index_elements=["telegram_id"],
                set_={
                    "score": request.score,
                    "rank_percentile": request.rank_percentile,
                    "latitude": request.latitude,
                    "longitude": request.longitude,
                    "updated_at": datetime.now(UTC),
                },
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
    async def upsert_behavioral(
        self, session: AsyncSession, request: RatingRepositoryProtocol.UpsertBehavioralRatingRequest
    ) -> BehavioralRating:
        result = await session.execute(
            sa
            .insert(BehavioralRatingORM)
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
    async def upsert_combined_rating(
        self, session: AsyncSession, request: RatingRepositoryProtocol.UpsertCombinedRatingRequest
    ) -> CombinedRating:
        result = await session.execute(
            sa
            .insert(CombinedRatingORM)
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
        user_lat: float,
        user_lon: float,
        radius_km: float = 50.0,
        limit: int = 100,
        exclude_ids: list[int] | None = None,
    ) -> list[RankedCandidate]:
        distance_m = radius_km * 1000
        boost_sql = sa.text(
            """
            CASE
                WHEN pr.latitude IS NOT NULL AND pr.longitude IS NOT NULL
                AND ST_DWithin(
                    ST_MakePoint(pr.longitude, pr.latitude)::geography,
                    ST_MakePoint(:user_lon, :user_lat)::geography,
                    :distance
                ) THEN 1.2
                ELSE 1.0
            END
            """
        )

        query = (
            sa
            .select(
                CombinedRatingORM.telegram_id,
                (
                    CombinedRatingORM.combined_score
                    * boost_sql.bindparams(user_lat=user_lat, user_lon=user_lon, distance=distance_m)
                ).label("boosted_score"),
            )
            .join(PrimaryRatingORM, CombinedRatingORM.telegram_id == PrimaryRatingORM.telegram_id)
            .where(CombinedRatingORM.status == "active")
        )

        if exclude_ids:
            query = query.where(CombinedRatingORM.telegram_id.not_in(exclude_ids))

        query = query.order_by(sa.desc("boosted_score")).limit(limit)

        result = await session.execute(query, {"user_lat": user_lat, "user_lon": user_lon, "distance": distance_m})

        candidates = []
        for rank, row in enumerate(result.all(), start=1):
            boost = row.boosted_score / row.combined_score if row.combined_score > 0 else 1.0
            reason = "nearby_boost" if boost > 1.0 else "top_score"
            candidates.append(
                RankedCandidate(
                    telegram_id=row.telegram_id,
                    combined_score=row.boosted_score,
                    rank=rank,
                    reason=reason,
                )
            )
        return candidates
