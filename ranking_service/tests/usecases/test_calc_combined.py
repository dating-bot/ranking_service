from contextlib import asynccontextmanager
from datetime import UTC, datetime
from enum import StrEnum
from unittest.mock import AsyncMock

import pytest

from ranking_service.protocols.rating.repository import RatingRepositoryProtocol
from ranking_service.usecases.calc_combined.usecase import CalcCombinedScore


class _RatingStatus(StrEnum):
    ACTIVE = "active"


class _CombinedRatingMock:
    def __init__(
        self,
        *,
        rating_id: int = 1,
        telegram_id: int = 123,
        primary_score: float = 0.0,
        behavioral_score: float = 0.0,
        combined_score: float = 0.0,
    ) -> None:
        self.id = rating_id
        self.telegram_id = telegram_id
        self.primary_score = primary_score
        self.behavioral_score = behavioral_score
        self.combined_score = combined_score
        self.status = _RatingStatus.ACTIVE
        self.created_at = datetime.now(tz=UTC)
        self.updated_at = datetime.now(tz=UTC)


@asynccontextmanager
async def _mock_context(session: object):
    yield session


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_rating_repository(mock_session: AsyncMock) -> AsyncMock:
    repo = AsyncMock(spec=RatingRepositoryProtocol)
    repo.context = lambda: _mock_context(mock_session)
    repo.upsert_combined_rating = AsyncMock(return_value=_CombinedRatingMock())
    return repo


@pytest.fixture
def usecase(mock_rating_repository: AsyncMock) -> CalcCombinedScore[AsyncMock]:
    return CalcCombinedScore[AsyncMock](rating_repository=mock_rating_repository)


@pytest.mark.asyncio
async def test_combined_formula_uses_all_components(
    usecase: CalcCombinedScore[AsyncMock],
    mock_rating_repository: AsyncMock,
) -> None:
    request = CalcCombinedScore.Request(
        telegram_id=123,
        primary_score=80.0,
        behavioral_score=40.0,
        referral_score=20.0,
        semantic_bonus=10.0,
    )

    await usecase.execute(request)

    call_args = mock_rating_repository.upsert_combined_rating.call_args
    saved_request = call_args.args[1]
    assert saved_request.combined_score == pytest.approx(45.5)


@pytest.mark.asyncio
async def test_combined_clamps_components_to_valid_range(
    usecase: CalcCombinedScore[AsyncMock],
    mock_rating_repository: AsyncMock,
) -> None:
    request = CalcCombinedScore.Request(
        telegram_id=123,
        primary_score=180.0,
        behavioral_score=-10.0,
        referral_score=200.0,
        semantic_bonus=-3.0,
    )

    await usecase.execute(request)

    call_args = mock_rating_repository.upsert_combined_rating.call_args
    saved_request = call_args.args[1]
    assert saved_request.primary_score == pytest.approx(100.0)
    assert saved_request.behavioral_score == pytest.approx(0.0)
    assert saved_request.combined_score == pytest.approx(40.0)
