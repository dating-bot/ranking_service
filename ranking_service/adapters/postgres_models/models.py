from datetime import UTC, datetime
from typing import final

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ranking_service.domain.interaction import InteractionStaging
from ranking_service.domain.ratings import (
    BehavioralRating,
    CombinedRating,
    PrimaryRating,
    RatingStatus,
)


class Base(DeclarativeBase):
    pass


@final
class PrimaryRatingORM(Base):
    __tablename__ = "primary_ratings"

    id: Mapped[int] = mapped_column(sa.BigInteger(), primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger(), unique=True, nullable=False)
    score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    rank_percentile: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    latitude: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    longitude: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        default=lambda: datetime.now(UTC),
    )

    __table_args__: tuple[sa.Index] = (
        sa.Index("ix_primary_ratings_telegram_id", "telegram_id"),
        sa.Index("ix_primary_ratings_location", "latitude", "longitude"),
    )

    def to_domain(self) -> PrimaryRating:
        return PrimaryRating(
            id=self.id,
            telegram_id=self.telegram_id,
            score=self.score,
            rank_percentile=self.rank_percentile,
            updated_at=self.updated_at,
        )


@final
class BehavioralRatingORM(Base):
    __tablename__ = "behavioral_ratings"

    id: Mapped[int] = mapped_column(sa.BigInteger(), primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger(), unique=True, nullable=False)
    engagement_score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    response_rate: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    avg_response_time_seconds: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        default=lambda: datetime.now(UTC),
    )

    __table_args__: tuple[sa.Index] = (sa.Index("ix_behavioral_ratings_telegram_id", "telegram_id"),)

    def to_domain(self) -> BehavioralRating:
        return BehavioralRating(
            id=self.id,
            telegram_id=self.telegram_id,
            engagement_score=self.engagement_score,
            response_rate=self.response_rate,
            avg_response_time_seconds=self.avg_response_time_seconds,
            updated_at=self.updated_at,
        )


@final
class CombinedRatingORM(Base):
    __tablename__ = "combined_ratings"

    id: Mapped[int] = mapped_column(sa.BigInteger(), primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger(), unique=True, nullable=False)
    primary_score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    behavioral_score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    combined_score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        default=lambda: datetime.now(UTC),
    )

    __table_args__: tuple[sa.Index, sa.Index] = (
        sa.Index("ix_combined_ratings_telegram_id", "telegram_id"),
        sa.Index("ix_combined_ratings_combined_score", "combined_score"),
    )

    def to_domain(self) -> CombinedRating:
        return CombinedRating(
            id=self.id,
            telegram_id=self.telegram_id,
            primary_score=self.primary_score,
            behavioral_score=self.behavioral_score,
            combined_score=self.combined_score,
            status=RatingStatus(self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


@final
class InteractionStagingORM(Base):
    __tablename__ = "interaction_staging"

    id: Mapped[int] = mapped_column(sa.BigInteger(), primary_key=True, autoincrement=True)
    actor_telegram_id: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    target_telegram_id: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        default=lambda: datetime.now(UTC),
    )

    __table_args__: tuple[sa.Index, sa.Index] = (
        sa.Index("ix_interaction_staging_actor", "actor_telegram_id"),
        sa.Index("ix_interaction_staging_target", "target_telegram_id"),
    )

    def to_domain(self) -> InteractionStaging:
        return InteractionStaging(
            id=self.id,
            actor_telegram_id=self.actor_telegram_id,
            target_telegram_id=self.target_telegram_id,
            created_at=self.created_at,
        )
