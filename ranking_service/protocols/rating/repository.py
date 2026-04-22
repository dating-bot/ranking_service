from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from ranking_service.domain.ratings import CombinedRating, PrimaryRating, RankedCandidate


class RatingRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class InsertPrimaryRatingRequest:
        telegram_id: int
        score: float
        rank_percentile: float

    async def insert_primary_rating(
        self, session: SessionT, request: InsertPrimaryRatingRequest
    ) -> PrimaryRating: ...

    @dataclass
    class UpsertCombinedRatingRequest:
        telegram_id: int
        primary_score: float
        behavioral_score: float
        combined_score: float

    async def upsert_combined_rating(
        self, session: SessionT, request: UpsertCombinedRatingRequest
    ) -> CombinedRating: ...

    async def get_combined_rating(self, session: SessionT, telegram_id: int) -> CombinedRating | None: ...

    async def list_top_candidates(
        self, session: SessionT, *, limit: int = 100, exclude_ids: list[int] | None = None
    ) -> list[RankedCandidate]: ...


class RankedQueueProtocol(Protocol):
    async def push_candidate(self, candidate: RankedCandidate) -> None: ...

    async def pop_candidate(self) -> RankedCandidate | None: ...

    async def peek(self, *, count: int) -> list[RankedCandidate]: ...

    async def size(self) -> int: ...

    async def clear(self) -> None: ...
