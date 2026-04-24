from dataclasses import dataclass
from typing import final, override

import structlog
from grpclib import Status
from grpclib.exceptions import GRPCError

from ranking_api.v1 import ranking_pb2
from ranking_api.v1.ranking_grpc import RankingServiceBase
from ranking_service.app.server.utils.unary import unary
from ranking_service.app.tasks.prefetch_ranked_queue import _prefetch_for_viewer, prefetch_ranked_queue
from ranking_service.protocols.rating.repository import RankedQueueProtocol
from ranking_service.usecases.calc_behavioral.usecase import CalcBehavioralScore

log = structlog.stdlib.get_logger("ranking_service.grpc")

PREFETCH_AT_RANK = 8
CANDIDATES_PER_PAGE = 10


@final
@dataclass(slots=True)
class RankingServiceHandler(RankingServiceBase):
    _ranked_queue: RankedQueueProtocol
    _calc_behavioral_score: CalcBehavioralScore

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
            log.debug("queue empty, running sync prefetch", viewer_id=viewer_id)
            try:
                _ = await _prefetch_for_viewer(viewer_id, limit=CANDIDATES_PER_PAGE)
            except Exception:
                log.exception("sync prefetch failed, scheduling async prefetch", viewer_id=viewer_id)
                prefetch_ranked_queue.delay(viewer_id)
            candidate = await self._ranked_queue.lpop_viewer_candidate(viewer_id)

        queue_len = await self._ranked_queue.get_viewer_queue_len(viewer_id)

        remaining_after_pop = queue_len
        next_rank = CANDIDATES_PER_PAGE - remaining_after_pop + 1
        if next_rank >= PREFETCH_AT_RANK:
            log.debug(
                "approaching prefetch rank, scheduling async prefetch",
                viewer_id=viewer_id,
                next_rank=next_rank,
                remaining=remaining_after_pop,
            )
            _ = prefetch_ranked_queue.apply_async(args=[viewer_id])

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

    @override
    @unary
    async def GetViewerQueueState(
        self, request: ranking_pb2.GetViewerQueueStateRequest
    ) -> ranking_pb2.GetViewerQueueStateResponse:
        if not request.viewer_id:
            raise GRPCError(Status.INVALID_ARGUMENT, "viewer_id is required")

        viewer_id = request.viewer_id
        q_len = await self._ranked_queue.get_viewer_queue_len(viewer_id)
        preview = await self._ranked_queue.lrange_viewer_candidates(viewer_id, 0, 4)
        head = preview[0].telegram_id if preview else 0
        return ranking_pb2.GetViewerQueueStateResponse(
            queue_len=q_len,
            head_candidate_telegram_id=head,
            preview_telegram_ids=[c.telegram_id for c in preview],
        )

    @override
    @unary
    async def UpdateEngagement(
        self, request: ranking_pb2.UpdateEngagementRequest
    ) -> ranking_pb2.UpdateEngagementResponse:
        if not request.user1_telegram_id or not request.user2_telegram_id:
            raise GRPCError(Status.INVALID_ARGUMENT, "user IDs are required")

        if request.event_type == "match_created":
            for user_id in [request.user1_telegram_id, request.user2_telegram_id]:
                try:
                    _ = await self._calc_behavioral_score.execute(
                        CalcBehavioralScore.Request(
                            telegram_id=user_id,
                            like_ratio=0.5,
                            match_rate=1.0,
                            chat_init=0.5,
                            active_hour=0.5,
                            response_rate=0.5,
                            avg_response_time_seconds=300.0,
                        )
                    )
                except Exception:
                    log.exception("failed to update engagement", user_id=user_id)
                    return ranking_pb2.UpdateEngagementResponse(success=False)
            log.info(
                "engagement updated from match event",
                user1=request.user1_telegram_id,
                user2=request.user2_telegram_id,
            )
            return ranking_pb2.UpdateEngagementResponse(success=True)

        return ranking_pb2.UpdateEngagementResponse(success=True)
