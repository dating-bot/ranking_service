from collections.abc import AsyncGenerator

import redis.asyncio as redis
from pydantic import BaseModel, Field


class ValkeyConfig(BaseModel):
    host: str = Field(description="Host")
    port: int = Field(default=6379, description="Port")
    db: int = Field(default=0, description="Default database")
    db_rankings: int = Field(default=1, description="Database for ranked queues")
    password: str | None = Field(default=None, description="Password")


class ValkeyClient:
    def __init__(self, config: ValkeyConfig, *, db: int | None = None) -> None:
        self._config = config
        self._db = db if db is not None else config.db
        self._client: redis.Redis | None = None

    async def initialize(self) -> None:
        self._client = redis.Redis(
            host=self._config.host,
            port=self._config.port,
            db=self._db,
            password=self._config.password,
            decode_responses=True,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("ValkeyClient not initialized")
        return self._client


async def provide_valkey_client(config: ValkeyConfig) -> AsyncGenerator[ValkeyClient]:
    client = ValkeyClient(config)
    await client.initialize()
    try:
        yield client
    finally:
        await client.close()


async def provide_valkey_client_rankings(config: ValkeyConfig) -> AsyncGenerator[ValkeyClient]:
    client = ValkeyClient(config, db=config.db_rankings)
    await client.initialize()
    try:
        yield client
    finally:
        await client.close()
