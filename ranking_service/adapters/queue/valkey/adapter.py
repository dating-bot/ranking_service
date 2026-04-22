import json
from typing import final, override

from ranking_service.domain.ratings import RankedCandidate
from ranking_service.infra.valkey import ValkeyClient
from ranking_service.protocols.rating.repository import RankedQueueProtocol

RANKED_QUEUE_KEY = "ranking:queue"
RANKED_QUEUE_TTL = 3600


@final
class ValkeyRankedQueueAdapter(RankedQueueProtocol):
    def __init__(self, *, valkey: ValkeyClient, ttl: int = RANKED_QUEUE_TTL) -> None:
        self._valkey = valkey
        self._ttl = ttl

    @override
    async def lpush_candidate(self, candidate: RankedCandidate) -> None:
        data = json.dumps({
            "telegram_id": candidate.telegram_id,
            "combined_score": candidate.combined_score,
            "rank": candidate.rank,
            "reason": candidate.reason,
        })
        await self._valkey.client.lpush(RANKED_QUEUE_KEY, data)
        await self._valkey.client.expire(RANKED_QUEUE_KEY, self._ttl)

    @override
    async def rpush_candidate(self, candidate: RankedCandidate) -> None:
        data = json.dumps({
            "telegram_id": candidate.telegram_id,
            "combined_score": candidate.combined_score,
            "rank": candidate.rank,
            "reason": candidate.reason,
        })
        await self._valkey.client.rpush(RANKED_QUEUE_KEY, data)
        await self._valkey.client.expire(RANKED_QUEUE_KEY, self._ttl)

    @override
    async def lpop_candidate(self) -> RankedCandidate | None:
        data = await self._valkey.client.lpop(RANKED_QUEUE_KEY)
        if data is None:
            return None
        parsed = json.loads(data)
        return RankedCandidate(
            telegram_id=parsed["telegram_id"],
            combined_score=parsed["combined_score"],
            rank=parsed["rank"],
            reason=parsed["reason"],
        )

    @override
    async def queue_len(self) -> int:
        return await self._valkey.client.llen(RANKED_QUEUE_KEY)

    @override
    async def lrange_candidates(self, start: int, end: int) -> list[RankedCandidate]:
        data = await self._valkey.client.lrange(RANKED_QUEUE_KEY, start, end)
        return [
            RankedCandidate(
                telegram_id=parsed["telegram_id"],
                combined_score=parsed["combined_score"],
                rank=parsed["rank"],
                reason=parsed["reason"],
            )
            for parsed in (json.loads(item) for item in data)
        ]

    @override
    async def clear_queue(self) -> None:
        await self._valkey.client.delete(RANKED_QUEUE_KEY)
