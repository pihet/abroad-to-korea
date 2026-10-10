"""Feedback: which photo was searched and the rank shown, for photo-level feedback ranking."""

import sqlalchemy as sa
from alembic import op

revision = "20261011_04"
down_revision = "20261010_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("photo_key", sa.String(length=64), nullable=True))
    op.add_column("feedback", sa.Column("rank", sa.Integer(), nullable=True))
    op.create_index("ix_feedback_photo_key", "feedback", ["photo_key"])


def downgrade() -> None:
    op.drop_index("ix_feedback_photo_key", table_name="feedback")
    op.drop_column("feedback", "rank")
    op.drop_column("feedback", "photo_key")
