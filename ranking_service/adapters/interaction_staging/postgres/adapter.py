from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import final, override

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from ranking_service.adapters.postgres_models.models import InteractionStagingORM
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

    @override
    async def insert_staging(
        self, session: AsyncSession, request: InteractionStagingRepositoryProtocol.InsertStagingRequest
    ) -> InteractionStaging:
        result = await session.execute(
            sa
            .insert(InteractionStagingORM)
            .values(
                actor_telegram_id=request.actor_telegram_id,
                target_telegram_id=request.target_telegram_id,
            )
            .returning(
                InteractionStagingORM.id,
                InteractionStagingORM.actor_telegram_id,
                InteractionStagingORM.target_telegram_id,
                InteractionStagingORM.created_at,
            )
        )
        row = result.mappings().one()
        return InteractionStaging(
            id=row["id"],
            actor_telegram_id=row["actor_telegram_id"],
            target_telegram_id=row["target_telegram_id"],
            created_at=row["created_at"],
        )

    @override
    async def list_target_ids_for_actor(self, session: AsyncSession, actor_telegram_id: int) -> list[int]:
        result = await session.execute(
            sa
            .select(InteractionStagingORM.target_telegram_id)
            .where(InteractionStagingORM.actor_telegram_id == actor_telegram_id)
            .distinct()
        )
        return [row.target_telegram_id for row in result.all()]
