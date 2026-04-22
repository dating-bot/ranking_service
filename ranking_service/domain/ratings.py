from datetime import UTC, datetime
from enum import StrEnum

import pydantic


class RatingStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PrimaryRating(pydantic.BaseModel):
    id: int = pydantic.Field(description="Primary rating ID")
    telegram_id: int = pydantic.Field(description="Telegram user ID")
    score: float = pydantic.Field(description="Primary rating score (0-100)")
    rank_percentile: float = pydantic.Field(description="Rank percentile (0-100)")
    updated_at: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="Last update timestamp",
    )


class BehavioralRating(pydantic.BaseModel):
    id: int = pydantic.Field(description="Behavioral rating ID")
    telegram_id: int = pydantic.Field(description="Telegram user ID")
    engagement_score: float = pydantic.Field(description="Engagement score (0-100)")
    response_rate: float = pydantic.Field(description="Response rate (0-1)")
    avg_response_time_seconds: float = pydantic.Field(description="Average response time in seconds")
    updated_at: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="Last update timestamp",
    )


class CombinedRating(pydantic.BaseModel):
    id: int = pydantic.Field(description="Combined rating ID")
    telegram_id: int = pydantic.Field(description="Telegram user ID")
    primary_score: float = pydantic.Field(description="Normalized primary score (0-100)")
    behavioral_score: float = pydantic.Field(description="Normalized behavioral score (0-100)")
    combined_score: float = pydantic.Field(description="Final combined score (0-100)")
    status: RatingStatus = pydantic.Field(default=RatingStatus.ACTIVE, description="Rating status")
    created_at: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="Creation timestamp",
    )
    updated_at: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="Last update timestamp",
    )


class RankedCandidate(pydantic.BaseModel):
    telegram_id: int = pydantic.Field(description="Candidate Telegram user ID")
    combined_score: float = pydantic.Field(description="Combined ranking score")
    rank: int = pydantic.Field(description="Rank position")
    reason: str = pydantic.Field(description="Ranking reason")
