from dataclasses import dataclass
from typing import final

import structlog

from ranking_service.domain.ratings import CombinedRating
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol

log = structlog.stdlib.get_logger("ranking_service.usecases.CalcCombinedScore")

COMBINED_WEIGHT_L1 = 0.30
COMBINED_WEIGHT_L2 = 0.45
COMBINED_WEIGHT_REFERRAL = 0.10
COMBINED_WEIGHT_SEMANTIC = 0.15


class CalcCombinedScoreError(Exception):
    """Base exception for CalcCombinedScore usecase."""


@final
class CalcCombinedScore[SessionT]:
    def __init__(
        self,
        *,
        rating_repository: RatingRepositoryProtocol[SessionT],
    ) -> None:
        self._rating_repository = rating_repository

    @dataclass
    class Request:
        telegram_id: int
        primary_score: float
        behavioral_score: float
        referral_score: float = 0.0
        semantic_bonus: float = 0.0
        status: str = "active"

    @dataclass
    class Response:
        combined_rating: CombinedRating

    async def execute(self, request: Request) -> Response:
        combined_score = (
            COMBINED_WEIGHT_L1 * request.primary_score
            + COMBINED_WEIGHT_L2 * request.behavioral_score
            + COMBINED_WEIGHT_REFERRAL * request.referral_score
            + COMBINED_WEIGHT_SEMANTIC * request.semantic_bonus
        )

        log.debug(
            "calculating combined score",
            telegram_id=request.telegram_id,
            primary_score=request.primary_score,
            behavioral_score=request.behavioral_score,
            referral_score=request.referral_score,
            semantic_bonus=request.semantic_bonus,
            combined_score=combined_score,
        )

        async with self._rating_repository.context() as session:
            combined_rating = await self._rating_repository.upsert_combined_rating(
                session,
                RatingRepositoryProtocol.UpsertCombinedRatingRequest(
                    telegram_id=request.telegram_id,
                    primary_score=request.primary_score,
                    behavioral_score=request.behavioral_score,
                    combined_score=combined_score,
                    status=request.status,
                ),
            )

        log.info(
            "combined score calculated",
            telegram_id=request.telegram_id,
            combined_score=combined_score,
        )

        return self.Response(combined_rating=combined_rating)
