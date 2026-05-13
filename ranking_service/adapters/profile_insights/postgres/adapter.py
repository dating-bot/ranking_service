from collections.abc import Sequence
from typing import final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from ranking_service.infra.postgres import AsyncSessionFactory
from ranking_service.protocols import ProfileInsightsProtocol


@final
class PostgresProfileInsightsAdapter(ProfileInsightsProtocol):
    def __init__(self, *, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory

    async def get_ai_quality_score(self, telegram_id: int) -> float | None:
        async with self._session_factory() as session:
            value = await _fetch_ai_quality_score(session, telegram_id=telegram_id)
            if value is None:
                return None
            return float(value)

    async def get_profile_is_active(self, telegram_id: int) -> bool:
        async with self._session_factory() as session:
            value = await _fetch_profile_is_active(session, telegram_id=telegram_id)
            return bool(value)

    async def get_semantic_bonuses(
        self,
        *,
        viewer_telegram_id: int,
        candidate_telegram_ids: list[int],
    ) -> dict[int, float]:
        unique_ids = list(set(candidate_telegram_ids))
        if not unique_ids:
            return {}

        async with self._session_factory() as session:
            return await _fetch_semantic_bonuses(
                session,
                viewer_telegram_id=viewer_telegram_id,
                candidate_telegram_ids=unique_ids,
            )


async def _fetch_ai_quality_score(session: AsyncSession, *, telegram_id: int) -> float | None:
    query = sa.text(
        """
        SELECT p.ai_quality_score
        FROM users u
        JOIN profiles p ON p.user_id = u.id
        WHERE u.telegram_id = :telegram_id
        LIMIT 1
        """
    )
    row = (await session.execute(query, {"telegram_id": telegram_id})).first()
    if row is None:
        return None
    value = row[0]
    if value is None:
        return None
    return float(value)


async def _fetch_semantic_bonuses(
    session: AsyncSession,
    *,
    viewer_telegram_id: int,
    candidate_telegram_ids: Sequence[int],
) -> dict[int, float]:
    query = sa.text(
        """
        WITH viewer_embedding AS (
            SELECT ve.embedding AS embedding
            FROM users vu
            JOIN profiles vp ON vp.user_id = vu.id
            JOIN profile_embeddings ve ON ve.profile_id = vp.id
            WHERE vu.telegram_id = :viewer_telegram_id
            LIMIT 1
        )
        SELECT cu.telegram_id AS telegram_id,
               GREATEST(0.0, LEAST(1.0, 1 - (ce.embedding <=> ve.embedding))) AS semantic_bonus
        FROM viewer_embedding ve
        JOIN users cu ON cu.telegram_id = ANY(:candidate_telegram_ids)
        JOIN profiles cp ON cp.user_id = cu.id
        JOIN profile_embeddings ce ON ce.profile_id = cp.id
        """
    )
    rows = (
        await session.execute(
            query,
            {
                "viewer_telegram_id": viewer_telegram_id,
                "candidate_telegram_ids": list(candidate_telegram_ids),
            },
        )
    ).mappings()

    return {int(row["telegram_id"]): float(row["semantic_bonus"]) for row in rows}


async def _fetch_profile_is_active(session: AsyncSession, *, telegram_id: int) -> bool:
    query = sa.text(
        """
        SELECT p.is_active
        FROM users u
        JOIN profiles p ON p.user_id = u.id
        WHERE u.telegram_id = :telegram_id
        LIMIT 1
        """
    )
    row = (await session.execute(query, {"telegram_id": telegram_id})).first()
    if row is None:
        return False
    return bool(row[0])
