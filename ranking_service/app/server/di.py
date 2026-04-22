from typing import final

import dishka
from sqlalchemy.ext.asyncio import AsyncSession

from ranking_service import adapters, infra, protocols, usecases


@final
class InfraProvider(dishka.Provider):
    scope = dishka.Scope.APP

    global_config = dishka.provide(staticmethod(infra.GlobalConfig.load))
    subconfigs = dishka.provide_all(*infra.GlobalConfig.subconfigs())
    async_engine = dishka.provide(staticmethod(infra.provide_async_engine))
    async_session_factory = dishka.provide(staticmethod(infra.provide_async_session_factory))
    valkey = dishka.provide(staticmethod(infra.provide_valkey_client))


@final
class AdapterProvider(dishka.Provider):
    scope = dishka.Scope.APP

    @dishka.provide
    def provide_rating_repository(
        self,
        session_factory: infra.AsyncSessionFactory,
    ) -> protocols.RatingRepositoryProtocol:
        return adapters.PostgresRatingRepositoryAdapter(session_factory=session_factory)

    @dishka.provide
    def provide_interaction_staging_repository(
        self,
        session_factory: infra.AsyncSessionFactory,
    ) -> protocols.InteractionStagingRepositoryProtocol:
        return adapters.PostgresInteractionStagingRepositoryAdapter(session_factory=session_factory)

    @dishka.provide
    def provide_ranked_queue(self, valkey: infra.ValkeyClient) -> protocols.RankedQueueProtocol:
        return adapters.ValkeyRankedQueueAdapter(valkey=valkey)


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
    ) -> usecases.CalcBehavioralScore[AsyncSession]:
        return usecases.CalcBehavioralScore[AsyncSession](
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


container = dishka.make_async_container(InfraProvider(), AdapterProvider(), AppProvider())
