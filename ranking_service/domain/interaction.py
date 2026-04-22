from datetime import UTC, datetime

import pydantic


class InteractionStaging(pydantic.BaseModel):
    id: int = pydantic.Field(description="Staging record ID")
    actor_telegram_id: int = pydantic.Field(description="Actor Telegram user ID")
    target_telegram_id: int = pydantic.Field(description="Target Telegram user ID")
    created_at: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="Creation timestamp",
    )
