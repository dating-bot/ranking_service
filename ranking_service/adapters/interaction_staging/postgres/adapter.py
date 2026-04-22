from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import final, override

from sqlalchemy.ext.asyncio import AsyncSession

from ranking_service.domain import InteractionStaging
from ranking_service.infra.postgres import AsyncSessionFactory
from ranking_service.protocols.interaction_staging.repository import InteractionStagingRepositoryProtocol


@final
class PostgresInteractionStagingRepositoryAdapter(InteractionStagingRepositoryProtocol[AsyncSession]):
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

    async def insert_staging(
        self, session: AsyncSession, request: InteractionStagingRepositoryProtocol.InsertStagingRequest
    ) -> InteractionStaging:
        raise NotImplementedError
