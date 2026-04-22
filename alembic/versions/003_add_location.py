"""add location to primary ratings

Revision ID: 003
Revises: 002
Create Date: 2026-04-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "primary_ratings",
        sa.Column("latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "primary_ratings",
        sa.Column("longitude", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_primary_ratings_location",
        "primary_ratings",
        ["latitude", "longitude"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_primary_ratings_location", table_name="primary_ratings")
    op.drop_column("primary_ratings", "longitude")
    op.drop_column("primary_ratings", "latitude")
