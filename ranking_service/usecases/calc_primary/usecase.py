from dataclasses import dataclass
from datetime import datetime
from typing import final

import structlog

from ranking_service.domain.ratings import PrimaryRating
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol

log = structlog.stdlib.get_logger("ranking_service.usecases.CalcPrimaryScore")


class CalcPrimaryScoreError(Exception):
    """Base exception for CalcPrimaryScore usecase."""


@final
class CalcPrimaryScore[SessionT]:
    def __init__(
        self,
        *,
        rating_repository: RatingRepositoryProtocol[SessionT],
    ) -> None:
        self._rating_repository = rating_repository

    @dataclass
    class Request:
        telegram_id: int
        completeness: float
        photos: float
        prefs: float
        verification: float
        ai_quality: float
        latitude: float | None = None
        longitude: float | None = None
        age: int | None = None
        gender: str | None = None
        boost_expires_at: datetime | None = None

    @dataclass
    class Response:
        primary_rating: PrimaryRating

    async def execute(self, request: Request) -> Response:
        base_score = request.completeness + request.photos + request.prefs + request.verification
        score = base_score * request.ai_quality * 2

        log.debug(
            "calculating primary score",
            telegram_id=request.telegram_id,
            completeness=request.completeness,
            photos=request.photos,
            prefs=request.prefs,
            verification=request.verification,
            ai_quality=request.ai_quality,
            base_score=base_score,
            final_score=score,
        )

        async with self._rating_repository.context() as session:
            primary_rating = await self._rating_repository.upsert_primary(
                session,
                RatingRepositoryProtocol.UpsertPrimaryRatingRequest(
                    telegram_id=request.telegram_id,
                    score=score,
                    rank_percentile=0.0,
                    latitude=request.latitude,
                    longitude=request.longitude,
                    age=request.age,
                    gender=request.gender,
                    boost_expires_at=request.boost_expires_at,
                ),
            )

        log.info(
            "primary score calculated",
            telegram_id=request.telegram_id,
            score=score,
        )

        return self.Response(primary_rating=primary_rating)
