"""Users: drop the unique lower(email) index so an email sign-up and a Google/Kakao sign-up with the same
address are separate members (email sign-up has no verification mail, so the address may belong to someone else)."""

import sqlalchemy as sa
from alembic import op

revision = "20261011_05"
down_revision = "20261011_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_users_email_normalized", table_name="users")


def downgrade() -> None:
    # Fails if two members already share an address; merge or delete them first.
    op.create_index("uq_users_email_normalized", "users", [sa.text("lower(email)")], unique=True)
