from typing import final

import dishka

from ranking_service import adapters, infra, protocols


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

    rating_repository = dishka.provide(
        source=adapters.PostgresRatingRepositoryAdapter,
        provides=protocols.RatingRepositoryProtocol,
    )
    interaction_staging_repository = dishka.provide(
        source=adapters.PostgresInteractionStagingRepositoryAdapter,
        provides=protocols.InteractionStagingRepositoryProtocol,
    )


@final
class AppProvider(dishka.Provider):
    scope = dishka.Scope.APP


container = dishka.make_async_container(InfraProvider(), AdapterProvider(), AppProvider())
