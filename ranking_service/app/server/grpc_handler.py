from dataclasses import dataclass
from typing import final, override

import structlog
from grpclib import Status
from grpclib.exceptions import GRPCError

from api.ranking_api.v1 import ranking_pb2
from api.ranking_api.v1.ranking_grpc import RankingServiceBase
from ranking_service.app.server.utils.unary import unary
from ranking_service.app.tasks.prefetch_ranked_queue import prefetch_ranked_queue
from ranking_service.protocols.rating.repository import RankedQueueProtocol

log = structlog.stdlib.get_logger("ranking_service.grpc")

QUEUE_LOW_THRESHOLD = 2


@final
@dataclass(slots=True)
class RankingServiceHandler(RankingServiceBase):
    _ranked_queue: RankedQueueProtocol

    @override
    @unary
    async def GetNextCandidate(
        self, request: ranking_pb2.GetNextCandidateRequest
    ) -> ranking_pb2.GetNextCandidateResponse:
        if not request.viewer_id:
            raise GRPCError(Status.INVALID_ARGUMENT, "viewer_id is required")

        viewer_id = request.viewer_id

        candidate = await self._ranked_queue.lpop_viewer_candidate(viewer_id)

        if candidate is None:
            log.debug("queue empty, triggering prefetch", viewer_id=viewer_id)
            prefetch_ranked_queue.delay(viewer_id)
            candidate = await self._ranked_queue.lpop_viewer_candidate(viewer_id)

        queue_len = await self._ranked_queue.get_viewer_queue_len(viewer_id)

        if queue_len <= QUEUE_LOW_THRESHOLD:
            log.debug("queue running low, scheduling async prefetch", viewer_id=viewer_id, queue_len=queue_len)
            prefetch_ranked_queue.apply_async(args=[viewer_id])

        if candidate is None:
            raise GRPCError(Status.NOT_FOUND, "no candidates available")

        log.info(
            "returning next candidate",
            viewer_id=viewer_id,
            profile_id=candidate.telegram_id,
            queue_len=queue_len,
        )

        return ranking_pb2.GetNextCandidateResponse(
            profile_id=candidate.telegram_id,
            queue_len=queue_len,
        )
