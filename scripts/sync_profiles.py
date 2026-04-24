#!/usr/bin/env python
"""Скрипт для принудительной синхронизации профилей в ranking_service."""

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

import grpclib.client
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from external_clients.profile_api.v1.profile_grpc import ProfileServiceStub
from ranking_service.adapters.rating.postgres.adapter import PostgresRatingRepositoryAdapter
from ranking_service.infra.config import GlobalConfig
from ranking_service.usecases.calc_combined.usecase import CalcCombinedScore
from ranking_service.usecases.calc_primary.usecase import CalcPrimaryScore
from ranking_service.usecases.sync_profile_to_ranking import SyncProfileToRanking

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)
log = structlog.stdlib.get_logger("sync_profiles")


async def sync_profile(telegram_id: int) -> bool:
    """Синхронизирует профиль в ranking_service."""
    config = GlobalConfig.load()
    engine = create_async_engine(config.postgres.url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    profile_channel = grpclib.client.Channel(
        host=config.profile_service.host,
        port=config.profile_service.port,
    )

    try:
        rating_repo = PostgresRatingRepositoryAdapter(session_factory=session_factory)
        profile_stub = ProfileServiceStub(profile_channel)

        calc_primary = CalcPrimaryScore(rating_repository=rating_repo)
        calc_combined = CalcCombinedScore(rating_repository=rating_repo)

        sync_usecase = SyncProfileToRanking(
            profile_stub=profile_stub,
            rating_repository=rating_repo,
            calc_primary_score=calc_primary,
            calc_combined_score=calc_combined,
        )

        result = await sync_usecase.execute(SyncProfileToRanking.Request(telegram_id=telegram_id))

        if result:
            log.info("profile synced successfully", telegram_id=telegram_id)
        else:
            log.warning("profile sync failed (not found?)", telegram_id=telegram_id)

        return result
    finally:
        profile_channel.close()
        await engine.dispose()


async def main(telegram_ids: list[int]) -> None:
    """Синхронизирует список профилей."""
    log.info("starting profile sync", count=len(telegram_ids))

    for telegram_id in telegram_ids:
        try:
            await sync_profile(telegram_id)
        except Exception:
            log.exception("failed to sync profile", telegram_id=telegram_id)

    log.info("profile sync completed")


if __name__ == "__main__":
    # Профили для синхронизации
    profiles_to_sync = [
        5279497294,
        1776978303,
    ]

    if len(sys.argv) > 1:
        profiles_to_sync = [int(arg) for arg in sys.argv[1:]]

    asyncio.run(main(profiles_to_sync))
