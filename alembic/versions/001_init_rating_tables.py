"""init rating tables

Revision ID: 001
Revises:
Create Date: 2026-04-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "primary_ratings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank_percentile", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_primary_ratings_telegram_id", "telegram_id"),
    )

    op.create_table(
        "behavioral_ratings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("engagement_score", sa.Float(), nullable=False),
        sa.Column("response_rate", sa.Float(), nullable=False),
        sa.Column("avg_response_time_seconds", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_behavioral_ratings_telegram_id", "telegram_id"),
    )

    op.create_table(
        "combined_ratings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("primary_score", sa.Float(), nullable=False),
        sa.Column("behavioral_score", sa.Float(), nullable=False),
        sa.Column("combined_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_combined_ratings_telegram_id", "telegram_id"),
        sa.Index("ix_combined_ratings_combined_score", "combined_score"),
    )


def downgrade() -> None:
    op.drop_table("combined_ratings")
    op.drop_table("behavioral_ratings")
    op.drop_table("primary_ratings")
