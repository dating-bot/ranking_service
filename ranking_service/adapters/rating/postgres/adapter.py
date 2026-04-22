from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import final, override

from sqlalchemy.ext.asyncio import AsyncSession

from ranking_service.domain import CombinedRating, PrimaryRating
from ranking_service.infra.postgres import AsyncSessionFactory
from ranking_service.protocols.rating.repository import RankedCandidate, RatingRepositoryProtocol


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

    async def insert_primary_rating(
        self, session: AsyncSession, request: RatingRepositoryProtocol.InsertPrimaryRatingRequest
    ) -> PrimaryRating:
        raise NotImplementedError

    async def upsert_combined_rating(
        self, session: AsyncSession, request: RatingRepositoryProtocol.UpsertCombinedRatingRequest
    ) -> CombinedRating:
        raise NotImplementedError

    async def get_combined_rating(self, session: AsyncSession, telegram_id: int) -> CombinedRating | None:
        raise NotImplementedError

    async def list_top_candidates(
        self, session: AsyncSession, *, limit: int = 100, exclude_ids: list[int] | None = None
    ) -> list[RankedCandidate]:
        raise NotImplementedError
