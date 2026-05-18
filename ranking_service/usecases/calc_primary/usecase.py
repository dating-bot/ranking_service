from dataclasses import dataclass
from datetime import datetime
from typing import final

import structlog

from ranking_service.domain.ratings import PrimaryRating
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol

log = structlog.stdlib.get_logger("ranking_service.usecases.CalcPrimaryScore")

PRIMARY_COMPLETENESS_MIN = 0.0
PRIMARY_COMPLETENESS_MAX = 30.0
PRIMARY_PHOTOS_MIN = 0.0
PRIMARY_PHOTOS_MAX = 25.0
PRIMARY_PREFS_MIN = 0.0
PRIMARY_PREFS_MAX = 10.0
PRIMARY_VERIFICATION_MIN = 0.0
PRIMARY_VERIFICATION_MAX = 15.0
PRIMARY_AI_QUALITY_MIN = 0.0
PRIMARY_AI_QUALITY_MAX = 1.0


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
        completeness = _clamp(request.completeness, PRIMARY_COMPLETENESS_MIN, PRIMARY_COMPLETENESS_MAX)
        photos = _clamp(request.photos, PRIMARY_PHOTOS_MIN, PRIMARY_PHOTOS_MAX)
        prefs = _clamp(request.prefs, PRIMARY_PREFS_MIN, PRIMARY_PREFS_MAX)
        verification = _clamp(request.verification, PRIMARY_VERIFICATION_MIN, PRIMARY_VERIFICATION_MAX)
        ai_quality = _clamp(request.ai_quality, PRIMARY_AI_QUALITY_MIN, PRIMARY_AI_QUALITY_MAX)

        base_score = completeness + photos + prefs + verification
        score = base_score * ai_quality * 2

        log.debug(
            "calculating primary score",
            telegram_id=request.telegram_id,
            completeness=completeness,
            photos=photos,
            prefs=prefs,
            verification=verification,
            ai_quality=ai_quality,
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


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, float(value)))
