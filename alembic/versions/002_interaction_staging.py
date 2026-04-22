"""add interaction staging

Revision ID: 002
Revises: 001
Create Date: 2026-04-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interaction_staging",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("target_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_interaction_staging_actor", "actor_telegram_id"),
        sa.Index("ix_interaction_staging_target", "target_telegram_id"),
    )


def downgrade() -> None:
    op.drop_table("interaction_staging")
