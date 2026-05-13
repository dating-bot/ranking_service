from collections.abc import AsyncGenerator
from typing import final

import aio_pika
import dishka
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from external_clients.profile_api.v1.profile_grpc import ProfileServiceStub
from ranking_service import adapters, infra, protocols, usecases
from ranking_service.app.consumers.events_consumer import EventsConsumer
from ranking_service.app.server import grpc_handler


@final
class InfraProvider(dishka.Provider):
    scope = dishka.Scope.APP

    global_config = dishka.provide(staticmethod(infra.GlobalConfig.load))
    subconfigs = dishka.provide_all(*infra.GlobalConfig.subconfigs())
    async_engine = dishka.provide(staticmethod(infra.provide_async_engine))
    async_session_factory = dishka.provide(staticmethod(infra.provide_async_session_factory))
    async_engine_replica = dishka.provide(staticmethod(infra.provide_async_engine_replica))
    async_session_factory_replica = dishka.provide(staticmethod(infra.provide_async_session_factory_replica))
    valkey = dishka.provide(staticmethod(infra.provide_valkey_client))
    valkey_rankings = dishka.provide(staticmethod(infra.provide_valkey_client_rankings))
    rabbitmq_connection = dishka.provide(staticmethod(infra.provide_rabbitmq_connection))
    profile_stub = dishka.provide(staticmethod(infra.provide_profile_stub), provides=ProfileServiceStub)


@final
class AdapterProvider(dishka.Provider):
    scope = dishka.Scope.APP

    @dishka.provide
    def provide_rating_repository_primary(
        self,
        session_factory: infra.AsyncSessionFactory,
    ) -> protocols.RatingRepositoryProtocol:
        return adapters.PostgresRatingRepositoryAdapter(session_factory=session_factory)

    @dishka.provide
    def provide_rating_repository_replica(
        self,
        session_factory_replica: infra.AsyncSessionFactory,
    ) -> protocols.RatingRepositoryProtocol:
        return adapters.PostgresRatingRepositoryAdapter(session_factory=session_factory_replica)

    @dishka.provide
    def provide_interaction_staging_repository(
        self,
        session_factory: infra.AsyncSessionFactory,
    ) -> protocols.InteractionStagingRepositoryProtocol:
        return adapters.PostgresInteractionStagingRepositoryAdapter(session_factory=session_factory)

    @dishka.provide
    async def provide_profile_insights(
        self,
        profile_postgres: infra.ProfilePostgresConfig,
    ) -> AsyncGenerator[protocols.ProfileInsightsProtocol]:
        engine = create_async_engine(profile_postgres.url)
        session_factory = infra.AsyncSessionFactory(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            yield adapters.PostgresProfileInsightsAdapter(session_factory=session_factory)
        finally:
            await engine.dispose()

    @dishka.provide
    def provide_ranked_queue(self, valkey_rankings: infra.ValkeyClient) -> protocols.RankedQueueProtocol:
        return adapters.ValkeyRankedQueueAdapter(valkey=valkey_rankings)


@final
class AppProvider(dishka.Provider):
    scope = dishka.Scope.APP

    @dishka.provide
    def provide_calc_primary_score(
        self,
        rating_repository: protocols.RatingRepositoryProtocol[AsyncSession],
    ) -> usecases.CalcPrimaryScore[AsyncSession]:
        return usecases.CalcPrimaryScore[AsyncSession](
            rating_repository=rating_repository,
        )

    @dishka.provide
    def provide_calc_behavioral_score(
        self,
        rating_repository: protocols.RatingRepositoryProtocol[AsyncSession],
    ) -> usecases.CalcBehavioralScore:
        return usecases.CalcBehavioralScore(
            rating_repository=rating_repository,
        )

    @dishka.provide
    def provide_calc_combined_score(
        self,
        rating_repository: protocols.RatingRepositoryProtocol[AsyncSession],
    ) -> usecases.CalcCombinedScore[AsyncSession]:
        return usecases.CalcCombinedScore[AsyncSession](
            rating_repository=rating_repository,
        )

    @dishka.provide
    def provide_sync_profile_to_ranking(
        self,
        profile_stub: ProfileServiceStub,
        rating_repository: protocols.RatingRepositoryProtocol[AsyncSession],
        profile_insights: protocols.ProfileInsightsProtocol,
        calc_primary_score: usecases.CalcPrimaryScore[AsyncSession],
        calc_combined_score: usecases.CalcCombinedScore[AsyncSession],
    ) -> usecases.SyncProfileToRanking[AsyncSession]:
        return usecases.SyncProfileToRanking[AsyncSession](
            profile_stub=profile_stub,
            rating_repository=rating_repository,
            profile_insights=profile_insights,
            calc_primary_score=calc_primary_score,
            calc_combined_score=calc_combined_score,
        )

    @dishka.provide
    def provide_ranking_service_handler(
        self,
        ranked_queue: protocols.RankedQueueProtocol,
        calc_behavioral_score: usecases.CalcBehavioralScore,
    ) -> grpc_handler.RankingServiceHandler:
        return grpc_handler.RankingServiceHandler(
            _ranked_queue=ranked_queue,
            _calc_behavioral_score=calc_behavioral_score,
        )

    @dishka.provide
    def provide_events_consumer(
        self,
        rabbitmq_connection: aio_pika.abc.AbstractRobustConnection,
        sync_profile_to_ranking: usecases.SyncProfileToRanking[AsyncSession],
        interaction_staging_repository: protocols.InteractionStagingRepositoryProtocol[AsyncSession],
    ) -> EventsConsumer:
        return EventsConsumer(
            connection=rabbitmq_connection,
            sync_profile_to_ranking=sync_profile_to_ranking,
            interaction_staging_repository=interaction_staging_repository,
        )


container = dishka.make_async_container(InfraProvider(), AdapterProvider(), AppProvider())
