import asyncio

from ranking_service.app.tasks.prefetch_ranked_queue import _rerank_with_semantic
from ranking_service.domain import RankedCandidate
from ranking_service.protocols import ProfileInsightsProtocol


class _ProfileInsights(ProfileInsightsProtocol):
    async def get_ai_quality_score(self, telegram_id: int) -> float | None:
        del telegram_id
        return None

    async def get_profile_is_active(self, telegram_id: int) -> bool:
        del telegram_id
        return True

    async def get_verification_score(self, telegram_id: int) -> float:
        del telegram_id
        return 0.0

    async def get_referral_score(self, telegram_id: int) -> float:
        del telegram_id
        return 0.0

    async def get_profile_semantic_bonus(self, telegram_id: int) -> float:
        del telegram_id
        return 0.0

    async def get_semantic_bonuses(
        self,
        *,
        viewer_telegram_id: int,
        candidate_telegram_ids: list[int],
    ) -> dict[int, float]:
        del viewer_telegram_id, candidate_telegram_ids
        return {2: 0.8, 3: 0.2}


def test_rerank_with_semantic_bonus() -> None:
    candidates = [
        RankedCandidate(telegram_id=1, combined_score=60.0, rank=1, reason="top_score"),
        RankedCandidate(telegram_id=2, combined_score=59.0, rank=2, reason="top_score"),
        RankedCandidate(telegram_id=3, combined_score=58.0, rank=3, reason="top_score"),
    ]

    reranked = asyncio.run(
        _rerank_with_semantic(
            profile_insights=_ProfileInsights(),
            viewer_id=777,
            candidates=candidates,
            limit=2,
        )
    )

    assert [item.telegram_id for item in reranked] == [2, 3]
    assert reranked[0].combined_score > reranked[1].combined_score
    assert reranked[0].reason.endswith("+semantic")
    assert reranked[1].reason.endswith("+semantic")
