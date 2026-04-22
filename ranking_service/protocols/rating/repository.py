from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ranking_service.domain.ratings import BehavioralRating, CombinedRating, PrimaryRating, RankedCandidate


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

    @dataclass
    class UpsertPrimaryRatingRequest:
        telegram_id: int
        score: float
        rank_percentile: float
        latitude: float | None = None
        longitude: float | None = None
        age: int | None = None
        gender: str | None = None
        boost_expires_at: datetime | None = None

    @dataclass
    class UpsertBehavioralRatingRequest:
        telegram_id: int
        engagement_score: float
        response_rate: float
        avg_response_time_seconds: float

    @dataclass
    class UpsertCombinedRatingRequest:
        telegram_id: int
        primary_score: float
        behavioral_score: float
        combined_score: float

    async def insert_primary_rating(self, session: SessionT, request: InsertPrimaryRatingRequest) -> PrimaryRating: ...

    async def upsert_primary(self, session: SessionT, request: UpsertPrimaryRatingRequest) -> PrimaryRating: ...

    async def upsert_behavioral(
        self, session: SessionT, request: UpsertBehavioralRatingRequest
    ) -> BehavioralRating: ...

    async def upsert_combined_rating(
        self, session: SessionT, request: UpsertCombinedRatingRequest
    ) -> CombinedRating: ...

    async def get_combined_rating(self, session: SessionT, telegram_id: int) -> CombinedRating | None: ...

    async def list_top_candidates(
        self, session: SessionT, *, limit: int = 100, exclude_ids: list[int] | None = None
    ) -> list[RankedCandidate]: ...

    async def get_ranked_candidates(  # noqa: PLR0913
        self,
        session: SessionT,
        *,
        viewer_id: int,
        user_lat: float,
        user_lon: float,
        gender_pref: str,
        age_min: int,
        age_max: int,
        radius_km: float = 50.0,
        limit: int = 100,
        exclude_ids: list[int] | None = None,
    ) -> list[RankedCandidate]: ...

    @dataclass
    class ProfileRatingData:
        telegram_id: int
        primary_score: float
        behavioral_score: float

    async def list_profiles_for_shard(
        self, session: SessionT, *, shard: int, total_shards: int
    ) -> list["RatingRepositoryProtocol.ProfileRatingData"]: ...


class RankedQueueProtocol(Protocol):
    async def lpush_candidate(self, candidate: RankedCandidate) -> None: ...
    async def rpush_candidate(self, candidate: RankedCandidate) -> None: ...
    async def lpop_candidate(self) -> RankedCandidate | None: ...
    async def queue_len(self) -> int: ...
    async def lrange_candidates(self, start: int, end: int) -> list[RankedCandidate]: ...
    async def clear_queue(self) -> None: ...
    async def get_viewer_queue_len(self, viewer_id: int) -> int: ...
    async def lpop_viewer_candidate(self, viewer_id: int) -> RankedCandidate | None: ...
