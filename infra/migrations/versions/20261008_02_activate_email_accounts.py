"""Activate email accounts without requiring verification."""

from alembic import op

revision = "20261008_02"
down_revision = "20261008_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET status = 'active'
        WHERE status = 'pending'
          AND EXISTS (
              SELECT 1 FROM auth_identities
              WHERE auth_identities.user_id = users.id
                AND auth_identities.provider = 'email'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET status = 'pending'
        WHERE status = 'active'
          AND email_verified_at IS NULL
          AND EXISTS (
              SELECT 1 FROM auth_identities
              WHERE auth_identities.user_id = users.id
                AND auth_identities.provider = 'email'
          )
        """
    )
