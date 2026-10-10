"""Enforce account and feedback identity rules."""

import sqlalchemy as sa
from alembic import op

revision = "20261010_03"
down_revision = "20261008_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM users GROUP BY lower(email) HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'users contains duplicate normalized emails; merge them before migrating';
            END IF;
            IF EXISTS (
                SELECT 1 FROM auth_identities GROUP BY user_id, provider HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'a user has multiple identities for the same provider; merge them before migrating';
            END IF;
        END
        $$;
        """
    )
    op.create_index("uq_users_email_normalized", "users", [sa.text("lower(email)")], unique=True)
    op.create_unique_constraint("uq_auth_user_provider", "auth_identities", ["user_id", "provider"])

    # PostgreSQL UNIQUE treats NULL values as distinct. Keep the newest anonymous vote before
    # replacing the old constraint with separate authenticated and anonymous indexes.
    op.execute(
        """
        DELETE FROM feedback
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY query_id, sigungu_key, attraction_id
                    ORDER BY created_at DESC, id DESC
                ) AS position
                FROM feedback
                WHERE user_id IS NULL
            ) ranked
            WHERE position > 1
        )
        """
    )
    op.drop_constraint("uq_feedback_vote", "feedback", type_="unique")
    op.create_index(
        "uq_feedback_user_vote",
        "feedback",
        ["query_id", "sigungu_key", "attraction_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_feedback_anonymous_vote",
        "feedback",
        ["query_id", "sigungu_key", "attraction_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.drop_constraint("feedback_user_id_fkey", "feedback", type_="foreignkey")
    op.create_foreign_key(
        "feedback_user_id_fkey", "feedback", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("feedback_user_id_fkey", "feedback", type_="foreignkey")
    op.create_foreign_key(
        "feedback_user_id_fkey", "feedback", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )
    op.drop_index("uq_feedback_anonymous_vote", table_name="feedback")
    op.drop_index("uq_feedback_user_vote", table_name="feedback")
    op.create_unique_constraint(
        "uq_feedback_vote", "feedback", ["query_id", "sigungu_key", "attraction_id", "user_id"]
    )
    op.drop_constraint("uq_auth_user_provider", "auth_identities", type_="unique")
    op.drop_index("uq_users_email_normalized", table_name="users")
