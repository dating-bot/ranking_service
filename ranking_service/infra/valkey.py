from pydantic import BaseModel, Field


class ValkeyConfig(BaseModel):
    host: str = Field(description="Host")
    port: int = Field(default=6379, description="Port")
    db: int = Field(default=0, description="Database number")


class ValkeyClient:
    pass
