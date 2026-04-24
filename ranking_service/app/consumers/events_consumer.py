import asyncio
import json
from typing import final

import aio_pika
import structlog
from aio_pika import ExchangeType

from ranking_service.protocols.interaction_staging.repository import InteractionStagingRepositoryProtocol
from ranking_service.usecases.sync_profile_to_ranking import SyncProfileToRanking

log = structlog.stdlib.get_logger("ranking_service.consumers.EventsConsumer")

PROFILE_EXCHANGE = "profile_exchange"
PROFILE_UPDATED_QUEUE = "ranking.profile.updated"
PHOTO_UPLOADED_QUEUE = "ranking.photo.uploaded"
RANKING_INTERACTION_LIKE_QUEUE = "ranking.interaction.like"
RANKING_INTERACTION_SKIP_QUEUE = "ranking.interaction.skip"


@final
class EventsConsumer[SessionT]:
    def __init__(
        self,
        *,
        connection: aio_pika.abc.AbstractRobustConnection,
        sync_profile_to_ranking: SyncProfileToRanking[SessionT],
        interaction_staging_repository: InteractionStagingRepositoryProtocol[SessionT],
    ) -> None:
        self._connection = connection
        self._sync_profile_to_ranking = sync_profile_to_ranking
        self._interaction_staging_repository = interaction_staging_repository
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def run(self) -> None:
        channel = await self._connection.channel()
        self._channel = channel
        _ = await channel.set_qos(prefetch_count=32)

        profile_exchange = await channel.declare_exchange(
            PROFILE_EXCHANGE,
            ExchangeType.TOPIC,
            durable=True,
        )
        profile_updated_queue = await channel.declare_queue(PROFILE_UPDATED_QUEUE, durable=True)
        _ = await profile_updated_queue.bind(profile_exchange, routing_key="profile.updated")
        photo_uploaded_queue = await channel.declare_queue(PHOTO_UPLOADED_QUEUE, durable=True)
        _ = await photo_uploaded_queue.bind(profile_exchange, routing_key="photo.uploaded")

        like_queue = await channel.declare_queue(RANKING_INTERACTION_LIKE_QUEUE, durable=True)
        skip_queue = await channel.declare_queue(RANKING_INTERACTION_SKIP_QUEUE, durable=True)

        try:
            async with asyncio.TaskGroup() as tg:
                _ = tg.create_task(self._consume_profile_events(profile_updated_queue))
                _ = tg.create_task(self._consume_profile_events(photo_uploaded_queue))
                _ = tg.create_task(self._consume_interactions(like_queue))
                _ = tg.create_task(self._consume_interactions(skip_queue))
        finally:
            self._channel = None

    async def stop(self) -> None:
        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()

    async def _consume_profile_events(self, queue: aio_pika.abc.AbstractQueue) -> None:
        try:
            async with queue.iterator() as iterator:
                async for message in iterator:
                    async with message.process(ignore_processed=True):
                        payload = json.loads(message.body)
                        telegram_id = int(payload["telegram_id"])
                        try:
                            _ = await self._sync_profile_to_ranking.execute(
                                SyncProfileToRanking.Request(telegram_id=telegram_id)
                            )
                            log.info("ranking profile sync event processed", queue=queue.name, telegram_id=telegram_id)
                        except Exception:
                            log.exception("ranking profile sync event failed", queue=queue.name, telegram_id=telegram_id)
        except (asyncio.CancelledError, aio_pika.exceptions.ChannelInvalidStateError):
            log.info("profile events consumer stopped", queue=queue.name)

    async def _consume_interactions(self, queue: aio_pika.abc.AbstractQueue) -> None:
        try:
            async with queue.iterator() as iterator:
                async for message in iterator:
                    async with message.process(ignore_processed=True):
                        payload = json.loads(message.body)
                        actor_id = int(payload.get("actor_telegram_id") or payload.get("liker_telegram_id"))
                        target_id = int(payload.get("target_telegram_id") or payload.get("liked_telegram_id"))
                        async with self._interaction_staging_repository.context() as session:
                            _ = await self._interaction_staging_repository.insert_staging(
                                session,
                                InteractionStagingRepositoryProtocol.InsertStagingRequest(
                                    actor_telegram_id=actor_id,
                                    target_telegram_id=target_id,
                                ),
                            )
                        log.debug(
                            "ranking interaction staged", queue=queue.name, actor_id=actor_id, target_id=target_id
                        )
        except (asyncio.CancelledError, aio_pika.exceptions.ChannelInvalidStateError):
            log.info("interaction consumer stopped", queue=queue.name)
