from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from ranking_service.domain.interaction import InteractionStaging


class InteractionStagingRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class InsertStagingRequest:
        actor_telegram_id: int
        target_telegram_id: int

    async def insert_staging(self, session: SessionT, request: InsertStagingRequest) -> InteractionStaging: ...

    async def list_target_ids_for_actor(self, session: SessionT, actor_telegram_id: int) -> list[int]: ...

    async def delete_staging(self, session: SessionT, actor_telegram_id: int, target_telegram_id: int) -> None: ...
