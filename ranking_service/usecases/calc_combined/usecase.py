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
COMBINED_COMPONENT_MIN = 0.0
COMBINED_COMPONENT_MAX = 100.0


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
        primary_score = _clamp(request.primary_score, COMBINED_COMPONENT_MIN, COMBINED_COMPONENT_MAX)
        behavioral_score = _clamp(request.behavioral_score, COMBINED_COMPONENT_MIN, COMBINED_COMPONENT_MAX)
        referral_score = _clamp(request.referral_score, COMBINED_COMPONENT_MIN, COMBINED_COMPONENT_MAX)
        semantic_bonus = _clamp(request.semantic_bonus, COMBINED_COMPONENT_MIN, COMBINED_COMPONENT_MAX)

        combined_score = (
            COMBINED_WEIGHT_L1 * primary_score
            + COMBINED_WEIGHT_L2 * behavioral_score
            + COMBINED_WEIGHT_REFERRAL * referral_score
            + COMBINED_WEIGHT_SEMANTIC * semantic_bonus
        )

        log.debug(
            "calculating combined score",
            telegram_id=request.telegram_id,
            primary_score=primary_score,
            behavioral_score=behavioral_score,
            referral_score=referral_score,
            semantic_bonus=semantic_bonus,
            combined_score=combined_score,
        )

        async with self._rating_repository.context() as session:
            combined_rating = await self._rating_repository.upsert_combined_rating(
                session,
                RatingRepositoryProtocol.UpsertCombinedRatingRequest(
                    telegram_id=request.telegram_id,
                    primary_score=primary_score,
                    behavioral_score=behavioral_score,
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


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, float(value)))
