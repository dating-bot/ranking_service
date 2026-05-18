import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ranking_service.protocols import ProfileInsightsProtocol
from ranking_service.usecases.sync_profile_to_ranking import SyncProfileToRanking, _normalize_ai_quality


class _ProfileStub:
    async def GetProfile(self, request, metadata=None):  # noqa: N802
        del request, metadata
        return _profile_response()

    async def GetPreferences(self, request, metadata=None):  # noqa: N802
        del request, metadata
        return SimpleNamespace(found=False)


class _ProfileInsights(ProfileInsightsProtocol):
    async def get_ai_quality_score(self, telegram_id: int) -> float | None:
        del telegram_id
        return 4.2

    async def get_profile_is_active(self, telegram_id: int) -> bool:
        del telegram_id
        return True

    async def get_verification_score(self, telegram_id: int) -> float:
        del telegram_id
        return 15.0

    async def get_referral_score(self, telegram_id: int) -> float:
        del telegram_id
        return 80.0

    async def get_profile_semantic_bonus(self, telegram_id: int) -> float:
        del telegram_id
        return 60.0

    async def get_semantic_bonuses(
        self,
        *,
        viewer_telegram_id: int,
        candidate_telegram_ids: list[int],
    ) -> dict[int, float]:
        del viewer_telegram_id, candidate_telegram_ids
        return {}


class _RatingRepo:
    @asynccontextmanager
    async def context(self):
        yield object()

    async def get_behavioral_rating(self, session, telegram_id: int):
        del session, telegram_id


@dataclass
class _PrimaryRating:
    score: float


@dataclass
class _PrimaryResponse:
    primary_rating: _PrimaryRating


def _profile_response() -> SimpleNamespace:
    photos = [SimpleNamespace(is_active=True), SimpleNamespace(is_active=True)]

    def has_field(name: str) -> bool:
        return name in ("latitude", "longitude")

    return SimpleNamespace(
        found=True,
        profile_id=77,
        name="Alice",
        bio="hello",
        city="Moscow",
        age=28,
        gender=2,
        latitude=55.75,
        longitude=37.61,
        photos=photos,
        HasField=has_field,
    )


def test_sync_uses_ai_quality_from_profile_insights() -> None:
    calc_primary = AsyncMock()
    calc_primary.execute = AsyncMock(return_value=_PrimaryResponse(primary_rating=_PrimaryRating(score=64.0)))
    calc_combined = AsyncMock()
    calc_combined.execute = AsyncMock(return_value=object())

    usecase = SyncProfileToRanking(
        profile_stub=_ProfileStub(),
        rating_repository=_RatingRepo(),
        profile_insights=_ProfileInsights(),
        calc_primary_score=calc_primary,
        calc_combined_score=calc_combined,
    )

    ok = asyncio.run(usecase.execute(SyncProfileToRanking.Request(telegram_id=101, trace_id="t-1")))

    assert ok is True
    calc_primary.execute.assert_called_once()
    req = calc_primary.execute.call_args.args[0]
    assert req.ai_quality == pytest.approx(0.42)
    assert req.completeness == pytest.approx(30.0)
    assert req.photos == pytest.approx(16.6666666667)
    assert req.prefs == pytest.approx(0.0)
    assert req.verification == pytest.approx(15.0)
    combined_req = calc_combined.execute.call_args.args[0]
    assert combined_req.status == "active"
    assert combined_req.referral_score == pytest.approx(80.0)
    assert combined_req.semantic_bonus == pytest.approx(60.0)


def test_sync_archives_inactive_profile() -> None:
    calc_primary = AsyncMock()
    calc_primary.execute = AsyncMock(return_value=_PrimaryResponse(primary_rating=_PrimaryRating(score=64.0)))
    calc_combined = AsyncMock()
    calc_combined.execute = AsyncMock(return_value=object())

    class _InactiveInsights(_ProfileInsights):
        async def get_profile_is_active(self, telegram_id: int) -> bool:
            del telegram_id
            return False

    usecase = SyncProfileToRanking(
        profile_stub=_ProfileStub(),
        rating_repository=_RatingRepo(),
        profile_insights=_InactiveInsights(),
        calc_primary_score=calc_primary,
        calc_combined_score=calc_combined,
    )

    ok = asyncio.run(usecase.execute(SyncProfileToRanking.Request(telegram_id=101, trace_id="t-2")))

    assert ok is True
    combined_req = calc_combined.execute.call_args.args[0]
    assert combined_req.status == "archived"


def test_sync_prefs_component_is_applied() -> None:
    calc_primary = AsyncMock()
    calc_primary.execute = AsyncMock(return_value=_PrimaryResponse(primary_rating=_PrimaryRating(score=64.0)))
    calc_combined = AsyncMock()
    calc_combined.execute = AsyncMock(return_value=object())

    class _ProfileStubWithPrefs(_ProfileStub):
        async def GetPreferences(self, request, metadata=None):  # noqa: N802
            del request, metadata
            return SimpleNamespace(found=True)

    usecase = SyncProfileToRanking(
        profile_stub=_ProfileStubWithPrefs(),
        rating_repository=_RatingRepo(),
        profile_insights=_ProfileInsights(),
        calc_primary_score=calc_primary,
        calc_combined_score=calc_combined,
    )

    ok = asyncio.run(usecase.execute(SyncProfileToRanking.Request(telegram_id=101, trace_id="t-3")))

    assert ok is True
    req = calc_primary.execute.call_args.args[0]
    assert req.prefs == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 1.0),
        (-10.0, 0.0),
        (0.0, 0.0),
        (4.2, 0.42),
        (10.0, 1.0),
        (22.0, 1.0),
    ],
)
def test_normalize_ai_quality(raw: float | None, expected: float) -> None:
    assert _normalize_ai_quality(raw) == pytest.approx(expected)
