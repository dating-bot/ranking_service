from collections.abc import Sequence
from datetime import UTC, datetime
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

    async def get_verification_score(self, telegram_id: int) -> float:
        async with self._session_factory() as session:
            return await _fetch_verification_score(session, telegram_id=telegram_id)

    async def get_referral_score(self, telegram_id: int) -> float:
        async with self._session_factory() as session:
            referrals_table_exists = await _table_exists(session, table_name="referrals")
            if referrals_table_exists:
                referral_count = await _fetch_referral_count(session, telegram_id=telegram_id)
                return min(max((referral_count / 5.0) * 100.0, 0.0), 100.0)
            account_age_days = await _fetch_account_age_days(session, telegram_id=telegram_id)
            return min(max((account_age_days / 90.0) * 100.0, 0.0), 100.0)

    async def get_profile_semantic_bonus(self, telegram_id: int) -> float:
        async with self._session_factory() as session:
            return await _fetch_profile_semantic_bonus(session, telegram_id=telegram_id)

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


async def _fetch_verification_score(session: AsyncSession, *, telegram_id: int) -> float:
    query = sa.text(
        """
        SELECT p.subscription_tier, p.subscription_expires_at
        FROM users u
        JOIN profiles p ON p.user_id = u.id
        WHERE u.telegram_id = :telegram_id
        LIMIT 1
        """
    )
    row = (await session.execute(query, {"telegram_id": telegram_id})).first()
    if row is None:
        return 0.0
    tier = str(row[0] or "").lower()
    expires_at = row[1]
    if tier != "premium":
        return 0.0
    if expires_at is None:
        return 15.0
    now = datetime.now(tz=UTC)
    return 15.0 if expires_at > now else 0.0


async def _table_exists(session: AsyncSession, *, table_name: str) -> bool:
    query = sa.text("SELECT to_regclass(:table_name)")
    row = (await session.execute(query, {"table_name": f"public.{table_name}"})).first()
    return row is not None and row[0] is not None


async def _fetch_referral_count(session: AsyncSession, *, telegram_id: int) -> int:
    query = sa.text(
        """
        SELECT COUNT(*)::int
        FROM users referrer
        JOIN referrals r ON r.referrer_id = referrer.id
        WHERE referrer.telegram_id = :telegram_id
        """
    )
    row = (await session.execute(query, {"telegram_id": telegram_id})).first()
    return int(row[0] or 0) if row is not None else 0


async def _fetch_account_age_days(session: AsyncSession, *, telegram_id: int) -> float:
    query = sa.text(
        """
        SELECT EXTRACT(EPOCH FROM (NOW() - u.created_at)) / 86400.0
        FROM users u
        WHERE u.telegram_id = :telegram_id
        LIMIT 1
        """
    )
    row = (await session.execute(query, {"telegram_id": telegram_id})).first()
    if row is None or row[0] is None:
        return 0.0
    return float(row[0])


async def _fetch_profile_semantic_bonus(session: AsyncSession, *, telegram_id: int) -> float:
    embeddings_exist = await _table_exists(session, table_name="profile_embeddings")
    if not embeddings_exist:
        return 0.0

    query = sa.text(
        """
        SELECT
            EXISTS (
                SELECT 1
                FROM profile_embeddings e
                JOIN profiles p2 ON p2.id = e.profile_id
                JOIN users u2 ON u2.id = p2.user_id
                WHERE u2.telegram_id = :telegram_id
            ) AS has_embedding,
            p.ai_quality_score
        FROM users u
        JOIN profiles p ON p.user_id = u.id
        WHERE u.telegram_id = :telegram_id
        LIMIT 1
        """
    )
    row = (await session.execute(query, {"telegram_id": telegram_id})).first()
    if row is None:
        return 0.0
    has_embedding = bool(row[0])
    if not has_embedding:
        return 0.0
    ai_quality_raw = row[1]
    ai_quality = 0.0 if ai_quality_raw is None else max(0.0, min(10.0, float(ai_quality_raw)))
    return ai_quality * 10.0
