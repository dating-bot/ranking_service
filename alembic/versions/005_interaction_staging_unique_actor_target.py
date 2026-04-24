"""deduplicate and enforce unique interaction staging pair

Revision ID: 005
Revises: 004
Create Date: 2026-04-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM interaction_staging a
            USING interaction_staging b
            WHERE a.actor_telegram_id = b.actor_telegram_id
              AND a.target_telegram_id = b.target_telegram_id
              AND a.id > b.id;
            """
        )
    )
    op.create_unique_constraint(
        "uq_interaction_staging_actor_target",
        "interaction_staging",
        ["actor_telegram_id", "target_telegram_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_interaction_staging_actor_target", "interaction_staging", type_="unique")

