from dataclasses import dataclass
from typing import final

import structlog

from ranking_service.domain.ratings import BehavioralRating
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol

log = structlog.stdlib.get_logger("ranking_service.usecases.CalcBehavioralScore")


class CalcBehavioralScoreError(Exception):
    """Base exception for CalcBehavioralScore usecase."""


@final
class CalcBehavioralScore[SessionT]:
    def __init__(
        self,
        *,
        rating_repository: RatingRepositoryProtocol[SessionT],
    ) -> None:
        self._rating_repository = rating_repository

    @dataclass
    class Request:
        telegram_id: int
        like_ratio: float
        match_rate: float
        chat_init: float
        active_hour: float
        response_rate: float
        avg_response_time_seconds: float

    @dataclass
    class Response:
        behavioral_rating: BehavioralRating

    async def execute(self, request: Request) -> Response:
        engagement_score = (
            request.like_ratio * 40 + request.match_rate * 20 + request.chat_init * 15 + request.active_hour * 5
        )

        log.debug(
            "calculating behavioral score",
            telegram_id=request.telegram_id,
            like_ratio=request.like_ratio,
            match_rate=request.match_rate,
            chat_init=request.chat_init,
            active_hour=request.active_hour,
            response_rate=request.response_rate,
            avg_response_time_seconds=request.avg_response_time_seconds,
            engagement_score=engagement_score,
        )

        async with self._rating_repository.context() as session:
            behavioral_rating = await self._rating_repository.upsert_behavioral(
                session,
                RatingRepositoryProtocol.UpsertBehavioralRatingRequest(
                    telegram_id=request.telegram_id,
                    engagement_score=engagement_score,
                    response_rate=request.response_rate,
                    avg_response_time_seconds=request.avg_response_time_seconds,
                ),
            )

        log.info(
            "behavioral score calculated",
            telegram_id=request.telegram_id,
            engagement_score=engagement_score,
        )

        return self.Response(behavioral_rating=behavioral_rating)
