"""Search logs: photo search, AI travel question and name search requests."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261011_07"
down_revision = "20261011_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("photo_key", sa.String(length=64), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("result_keys", postgresql.JSONB(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_search_logs_user_id", "search_logs", ["user_id"])
    op.create_index("ix_search_logs_kind", "search_logs", ["kind"])
    op.create_index("ix_search_logs_created_at", "search_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_search_logs_created_at", table_name="search_logs")
    op.drop_index("ix_search_logs_kind", table_name="search_logs")
    op.drop_index("ix_search_logs_user_id", table_name="search_logs")
    op.drop_table("search_logs")
