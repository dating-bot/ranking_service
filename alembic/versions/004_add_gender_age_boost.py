"""Add gender, age, boost_expires_at to primary_ratings

Revision ID: 004
Revises: 003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "primary_ratings",
        sa.Column("gender", sa.String(16), nullable=True),
    )
    op.add_column(
        "primary_ratings",
        sa.Column("age", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "primary_ratings",
        sa.Column("boost_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_primary_ratings_gender",
        "primary_ratings",
        ["gender"],
    )
    op.create_index(
        "ix_primary_ratings_age",
        "primary_ratings",
        ["age"],
    )


def downgrade() -> None:
    op.drop_index("ix_primary_ratings_age", table_name="primary_ratings")
    op.drop_index("ix_primary_ratings_gender", table_name="primary_ratings")
    op.drop_column("primary_ratings", "boost_expires_at")
    op.drop_column("primary_ratings", "age")
    op.drop_column("primary_ratings", "gender")
