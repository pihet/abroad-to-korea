"""Inquiries: messages sent from the account settings 문의하기 form."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261011_06"
down_revision = "20261011_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inquiries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inquiries_user_id", "inquiries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_inquiries_user_id", table_name="inquiries")
    op.drop_table("inquiries")
