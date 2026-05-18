from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from ranking_service.domain.ratings import PrimaryRating
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol
from ranking_service.usecases.calc_primary.usecase import CalcPrimaryScore


def _make_primary_rating(
    *,
    rating_id: int = 1,
    telegram_id: int = 123,
    score: float = 0.0,
    rank_percentile: float = 0.0,
) -> PrimaryRating:
    return PrimaryRating(
        id=rating_id,
        telegram_id=telegram_id,
        score=score,
        rank_percentile=rank_percentile,
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
    repo.upsert_primary = AsyncMock(return_value=_make_primary_rating())
    return repo


@pytest.fixture
def usecase(mock_rating_repository: AsyncMock) -> CalcPrimaryScore[AsyncMock]:
    return CalcPrimaryScore[AsyncMock](rating_repository=mock_rating_repository)


class Test_CalcPrimaryScore:
    @pytest.mark.asyncio
    async def test_score_formula_completeness_photos_prefs_verification(
        self,
        usecase: CalcPrimaryScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcPrimaryScore.Request(
            telegram_id=123,
            completeness=30,
            photos=25,
            prefs=10,
            verification=15,
            ai_quality=1.0,
        )

        _ = await usecase.execute(request)

        mock_rating_repository.upsert_primary.assert_called_once()
        call_args = mock_rating_repository.upsert_primary.call_args
        saved_request = call_args.args[1]
        assert saved_request.score == 160.0

    @pytest.mark.asyncio
    async def test_score_with_ai_quality_multiplier(
        self,
        usecase: CalcPrimaryScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcPrimaryScore.Request(
            telegram_id=123,
            completeness=30,
            photos=25,
            prefs=10,
            verification=15,
            ai_quality=0.5,
        )

        _ = await usecase.execute(request)

        call_args = mock_rating_repository.upsert_primary.call_args
        saved_request = call_args.args[1]
        assert saved_request.score == 80.0

    @pytest.mark.asyncio
    async def test_score_zero_ai_quality(
        self,
        usecase: CalcPrimaryScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcPrimaryScore.Request(
            telegram_id=123,
            completeness=30,
            photos=25,
            prefs=10,
            verification=15,
            ai_quality=0.0,
        )

        await usecase.execute(request)

        call_args = mock_rating_repository.upsert_primary.call_args
        saved_request = call_args.args[1]
        assert saved_request.score == 0.0

    @pytest.mark.asyncio
    async def test_score_with_location(
        self,
        usecase: CalcPrimaryScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcPrimaryScore.Request(
            telegram_id=123,
            completeness=30,
            photos=25,
            prefs=10,
            verification=15,
            ai_quality=1.0,
            latitude=55.7558,
            longitude=37.6173,
        )

        _ = await usecase.execute(request)

        call_args = mock_rating_repository.upsert_primary.call_args
        saved_request = call_args.args[1]
        assert saved_request.latitude == 55.7558
        assert saved_request.longitude == 37.6173
        assert saved_request.score == 160.0

    @pytest.mark.asyncio
    async def test_returns_primary_rating(
        self,
        usecase: CalcPrimaryScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        mock_rating_repository.upsert_primary.return_value = _make_primary_rating(score=80.0)
        request = CalcPrimaryScore.Request(
            telegram_id=123,
            completeness=30,
            photos=25,
            prefs=10,
            verification=15,
            ai_quality=1.0,
        )

        response = await usecase.execute(request)

        assert response.primary_rating.score == 80.0

    @pytest.mark.asyncio
    async def test_partial_completeness(
        self,
        usecase: CalcPrimaryScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcPrimaryScore.Request(
            telegram_id=123,
            completeness=15,
            photos=10,
            prefs=0,
            verification=0,
            ai_quality=1.0,
        )

        await usecase.execute(request)

        call_args = mock_rating_repository.upsert_primary.call_args
        saved_request = call_args.args[1]
        assert saved_request.score == 50.0

    @pytest.mark.asyncio
    async def test_clamps_components_to_invariant_ranges(
        self,
        usecase: CalcPrimaryScore[AsyncMock],
        mock_rating_repository: AsyncMock,
    ) -> None:
        request = CalcPrimaryScore.Request(
            telegram_id=123,
            completeness=99,
            photos=99,
            prefs=99,
            verification=99,
            ai_quality=1.5,
        )

        await usecase.execute(request)

        call_args = mock_rating_repository.upsert_primary.call_args
        saved_request = call_args.args[1]
        assert saved_request.score == pytest.approx(160.0)
