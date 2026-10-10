"""Initial member, tourism, media, and ingestion schema."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "20261008_01"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("nickname", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "auth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_subject", sa.String(320), nullable=False),
        sa.Column("provider_email", sa.String(320)),
        sa.Column("password_hash", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_auth_provider_subject"),
        sa.CheckConstraint(
            "(provider = 'email' AND password_hash IS NOT NULL) OR "
            "(provider <> 'email' AND password_hash IS NULL)",
            name="ck_auth_password_provider",
        ),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_session_expiry_order"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_idle_expires_at", "auth_sessions", ["idle_expires_at"])
    op.create_index("ix_auth_sessions_absolute_expires_at", "auth_sessions", ["absolute_expires_at"])

    op.create_table(
        "one_time_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(32), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_one_time_token_lookup", "one_time_tokens", ["purpose", "token_hash"])
    op.create_index("ix_one_time_tokens_user_id", "one_time_tokens", ["user_id"])
    op.create_index("ix_one_time_tokens_expires_at", "one_time_tokens", ["expires_at"])

    op.create_table(
        "email_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("template", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_email_outbox_recipient", "email_outbox", ["recipient"])

    op.create_table(
        "user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("origin", sa.String(30)),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        *timestamps(),
    )

    op.create_table(
        "saved_regions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region_key", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "region_key", name="uq_saved_user_region"),
    )
    op.create_index("ix_saved_regions_user_id", "saved_regions", ["user_id"])
    op.create_index("ix_saved_regions_region_key", "saved_regions", ["region_key"])

    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(32), nullable=False),
        sa.Column("retained_at", sa.DateTime(timezone=True)),
        sa.Column("delete_after", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_media_assets_owner_user_id", "media_assets", ["owner_user_id"])
    op.create_index("ix_media_assets_kind", "media_assets", ["kind"])
    op.create_index("ix_media_assets_sha256", "media_assets", ["sha256"])
    op.create_index("ix_media_assets_delete_after", "media_assets", ["delete_after"])

    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("query_id", sa.String(40), nullable=False),
        sa.Column("sigungu_key", sa.String(80), nullable=False),
        sa.Column("attraction_id", sa.String(80), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("query_id", "sigungu_key", "attraction_id", "user_id", name="uq_feedback_vote"),
        sa.CheckConstraint("value IN (-1, 1)", name="ck_feedback_value"),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_index("ix_feedback_query_id", "feedback", ["query_id"])
    op.create_index("ix_feedback_sigungu_key", "feedback", ["sigungu_key"])

    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_url", sa.Text()),
        *timestamps(),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("dag_id", sa.String(150), nullable=False),
        sa.Column("logical_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rows_received", sa.Integer(), nullable=False),
        sa.Column("rows_published", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.UniqueConstraint("source_id", "dag_id", "logical_date", name="uq_ingestion_logical_run"),
    )
    op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"])

    op.create_table(
        "raw_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False, unique=True),
        sa.Column("sha256", sa.LargeBinary(32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_raw_objects_ingestion_run_id", "raw_objects", ["ingestion_run_id"])

    op.create_table(
        "regions",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("sido", sa.String(80), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("center_lat", sa.Float()),
        sa.Column("center_lon", sa.Float()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_regions_sido", "regions", ["sido"])

    op.create_table(
        "places",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_record_id", sa.String(100), nullable=False),
        sa.Column("region_key", sa.String(80), sa.ForeignKey("regions.key")),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("source_id", "source_record_id", name="uq_place_source_record"),
    )
    op.create_index("ix_places_region_key", "places", ["region_key"])
    op.create_index("ix_places_content_type", "places", ["content_type"])

    op.create_table(
        "place_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("places.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text()),
        sa.Column("sha256", sa.LargeBinary(32)),
        sa.Column("license_code", sa.String(30)),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("fetch_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_fetch_error", sa.Text()),
        sa.Column("last_fetch_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("place_id", "source_url", name="uq_place_image_url"),
    )
    op.create_index("ix_place_images_place_id", "place_images", ["place_id"])

    op.create_table(
        "festivals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_record_id", sa.String(100), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("places.id", ondelete="SET NULL")),
        sa.Column("region_key", sa.String(80), sa.ForeignKey("regions.key")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("source_id", "source_record_id", name="uq_festival_source_record"),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_festival_date_order"),
    )
    op.create_index("ix_festivals_region_key", "festivals", ["region_key"])
    op.create_index("ix_festivals_starts_on", "festivals", ["starts_on"])
    op.create_index("ix_festivals_ends_on", "festivals", ["ends_on"])

    op.create_table(
        "visitor_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("region_key", sa.String(80), sa.ForeignKey("regions.key"), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("visitors", sa.BigInteger(), nullable=False),
        sa.Column("basis", sa.String(20), nullable=False),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id")),
        sa.UniqueConstraint("region_key", "period", "basis", name="uq_visitor_region_period_basis"),
    )
    op.create_index("ix_visitor_metrics_region_key", "visitor_metrics", ["region_key"])

    op.create_table(
        "climate_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("region_key", sa.String(80), sa.ForeignKey("regions.key"), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("temperature_mean_c", sa.Float()),
        sa.Column("precipitation_mm", sa.Float()),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id")),
        sa.UniqueConstraint("region_key", "observed_on", name="uq_climate_region_day"),
    )
    op.create_index("ix_climate_daily_region_key", "climate_daily", ["region_key"])

    op.create_table(
        "image_embeddings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("place_image_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("place_images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("place_image_id", "model_version", name="uq_embedding_image_model"),
    )
    op.create_index("ix_image_embeddings_place_image_id", "image_embeddings", ["place_image_id"])
    op.create_index(
        "ix_image_embeddings_hnsw",
        "image_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    for table in (
        "image_embeddings", "climate_daily", "visitor_metrics", "festivals", "place_images", "places",
        "regions", "raw_objects", "ingestion_runs", "data_sources", "feedback", "media_assets",
        "saved_regions", "user_preferences", "email_outbox", "one_time_tokens", "auth_sessions",
        "auth_identities", "users",
    ):
        op.drop_table(table)
