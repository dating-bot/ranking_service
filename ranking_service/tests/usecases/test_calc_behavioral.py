from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from ranking_service.domain.ratings import BehavioralRating
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol
from ranking_service.usecases.calc_behavioral.usecase import CalcBehavioralScore


def _make_behavioral_rating(
    *,
    id: int = 1,
    telegram_id: int = 123,
    engagement_score: float = 0.0,
    response_rate: float = 0.0,
    avg_response_time_seconds: float = 0.0,
) -> BehavioralRating:
    return BehavioralRating(
        id=id,
        telegram_id=telegram_id,
        engagement_score=engagement_score,
        response_rate=response_rate,
        avg_response_time_seconds=avg_response_time_seconds,
        updated_at=datetime.now(tz=UTC),
    )


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
    repo.upsert_behavioral = AsyncMock(return_value=_make_behavioral_rating())
    return repo


@pytest.fixture
def usecase(mock_rating_repository: AsyncMock) -> CalcBehavioralScore[AsyncMock]:
    return CalcBehavioralScore[AsyncMock](rating_repository=mock_rating_repository)


class Test_CalcBehavioralScore:
    @pytest.mark.asyncio
    async def test_engagement_score_formula(
        self,
        usecase: CalcBehavioralScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcBehavioralScore.Request(
            telegram_id=123,
            like_ratio=1.0,
            match_rate=1.0,
            chat_init=1.0,
            active_hour=1.0,
            response_rate=0.5,
            avg_response_time_seconds=60.0,
        )

        await usecase.execute(request)

        mock_rating_repository.upsert_behavioral.assert_called_once()
        call_args = mock_rating_repository.upsert_behavioral.call_args
        saved_request = call_args.args[1]
        assert saved_request.engagement_score == 80.0

    @pytest.mark.asyncio
    async def test_engagement_score_zero_ratios(
        self,
        usecase: CalcBehavioralScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcBehavioralScore.Request(
            telegram_id=123,
            like_ratio=0.0,
            match_rate=0.0,
            chat_init=0.0,
            active_hour=0.0,
            response_rate=0.0,
            avg_response_time_seconds=0.0,
        )

        await usecase.execute(request)

        call_args = mock_rating_repository.upsert_behavioral.call_args
        saved_request = call_args.args[1]
        assert saved_request.engagement_score == 0.0

    @pytest.mark.asyncio
    async def test_engagement_score_like_ratio_only(
        self,
        usecase: CalcBehavioralScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcBehavioralScore.Request(
            telegram_id=123,
            like_ratio=1.0,
            match_rate=0.0,
            chat_init=0.0,
            active_hour=0.0,
            response_rate=0.0,
            avg_response_time_seconds=0.0,
        )

        await usecase.execute(request)

        call_args = mock_rating_repository.upsert_behavioral.call_args
        saved_request = call_args.args[1]
        assert saved_request.engagement_score == 40.0

    @pytest.mark.asyncio
    async def test_engagement_score_half_ratios(
        self,
        usecase: CalcBehavioralScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcBehavioralScore.Request(
            telegram_id=123,
            like_ratio=0.5,
            match_rate=0.5,
            chat_init=0.5,
            active_hour=0.5,
            response_rate=0.5,
            avg_response_time_seconds=60.0,
        )

        await usecase.execute(request)

        call_args = mock_rating_repository.upsert_behavioral.call_args
        saved_request = call_args.args[1]
        assert saved_request.engagement_score == 40.0

    @pytest.mark.asyncio
    async def test_response_rate_passed_through(
        self,
        usecase: CalcBehavioralScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcBehavioralScore.Request(
            telegram_id=123,
            like_ratio=0.5,
            match_rate=0.5,
            chat_init=0.5,
            active_hour=0.5,
            response_rate=0.75,
            avg_response_time_seconds=120.0,
        )

        await usecase.execute(request)

        call_args = mock_rating_repository.upsert_behavioral.call_args
        saved_request = call_args.args[1]
        assert saved_request.response_rate == 0.75
        assert saved_request.avg_response_time_seconds == 120.0

    @pytest.mark.asyncio
    async def test_returns_behavioral_rating(
        self,
        usecase: CalcBehavioralScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        mock_rating_repository.upsert_behavioral.return_value = _make_behavioral_rating(engagement_score=80.0)
        request = CalcBehavioralScore.Request(
            telegram_id=123,
            like_ratio=1.0,
            match_rate=1.0,
            chat_init=1.0,
            active_hour=1.0,
            response_rate=0.5,
            avg_response_time_seconds=60.0,
        )

        response = await usecase.execute(request)

        assert response.behavioral_rating.engagement_score == 80.0
