from collections.abc import AsyncGenerator

import grpclib.client
from pydantic import BaseModel, Field

from external_clients.profile_api.v1.profile_grpc import ProfileServiceStub


class ProfileServiceConfig(BaseModel):
    host: str = Field(description="profile-service gRPC host")
    port: int = Field(default=50052, description="profile-service gRPC port")


async def provide_profile_stub(config: ProfileServiceConfig) -> AsyncGenerator[ProfileServiceStub]:
    channel = grpclib.client.Channel(host=config.host, port=config.port)
    try:
        yield ProfileServiceStub(channel)
    finally:
        channel.close()
