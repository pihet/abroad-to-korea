import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    nickname: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identities: Mapped[list["AuthIdentity"]] = relationship(back_populates="user", cascade="all, delete-orphan")


Index("uq_users_email_normalized", func.lower(User.email), unique=True)


class AuthIdentity(TimestampMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_auth_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_auth_user_provider"),
        CheckConstraint("(provider = 'email' AND password_hash IS NOT NULL) OR (provider <> 'email' AND password_hash IS NULL)",
                        name="ck_auth_password_provider"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_subject: Mapped[str] = mapped_column(String(320))
    provider_email: Mapped[str | None] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(Text)
    user: Mapped[User] = relationship(back_populates="identities")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_session_expiry_order"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class OneTimeToken(Base):
    __tablename__ = "one_time_tokens"
    __table_args__ = (Index("ix_one_time_token_lookup", "purpose", "token_hash"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient: Mapped[str] = mapped_column(String(320), index=True)
    template: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class UserPreference(TimestampMixin, Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    locale: Mapped[str] = mapped_column(String(10), default="ko")
    origin: Mapped[str | None] = mapped_column(String(30))
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)


class SavedRegion(Base):
    __tablename__ = "saved_regions"
    __table_args__ = (UniqueConstraint("user_id", "region_key", name="uq_saved_user_region"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    region_key: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    object_key: Mapped[str] = mapped_column(Text, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32), index=True)
    retained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeedbackRecord(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        Index("uq_feedback_user_vote", "query_id", "sigungu_key", "attraction_id", "user_id", unique=True,
              postgresql_where=text("user_id IS NOT NULL")),
        Index("uq_feedback_anonymous_vote", "query_id", "sigungu_key", "attraction_id", unique=True,
              postgresql_where=text("user_id IS NULL")),
        CheckConstraint("value IN (-1, 1)", name="ck_feedback_value"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query_id: Mapped[str] = mapped_column(String(40), index=True)
    sigungu_key: Mapped[str] = mapped_column(String(80), index=True)
    attraction_id: Mapped[str] = mapped_column(String(80))
    value: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (UniqueConstraint("source_id", "dag_id", "logical_date", name="uq_ingestion_logical_run"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"))
    dag_id: Mapped[str] = mapped_column(String(150))
    logical_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), index=True)
    rows_received: Mapped[int] = mapped_column(Integer, default=0)
    rows_published: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class RawObject(Base):
    __tablename__ = "raw_objects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True)
    object_key: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Region(TimestampMixin, Base):
    __tablename__ = "regions"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    sido: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(80))
    center_lat: Mapped[float | None] = mapped_column(Float)
    center_lon: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Place(TimestampMixin, Base):
    __tablename__ = "places"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id", name="uq_place_source_record"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"))
    source_record_id: Mapped[str] = mapped_column(String(100))
    region_key: Mapped[str | None] = mapped_column(ForeignKey("regions.key"), index=True)
    content_type: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlaceImage(TimestampMixin, Base):
    __tablename__ = "place_images"
    __table_args__ = (UniqueConstraint("place_id", "source_url", name="uq_place_image_url"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    license_code: Mapped[str | None] = mapped_column(String(30))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_fetch_error: Mapped[str | None] = mapped_column(Text)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Festival(TimestampMixin, Base):
    __tablename__ = "festivals"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id", name="uq_festival_source_record"),
        CheckConstraint("ends_on >= starts_on", name="ck_festival_date_order"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"))
    source_record_id: Mapped[str] = mapped_column(String(100))
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id", ondelete="SET NULL"))
    region_key: Mapped[str | None] = mapped_column(ForeignKey("regions.key"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    starts_on: Mapped[date] = mapped_column(Date, index=True)
    ends_on: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VisitorMetric(Base):
    __tablename__ = "visitor_metrics"
    __table_args__ = (UniqueConstraint("region_key", "period", "basis", name="uq_visitor_region_period_basis"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_key: Mapped[str] = mapped_column(ForeignKey("regions.key"), index=True)
    period: Mapped[date] = mapped_column(Date)
    visitors: Mapped[int] = mapped_column(BigInteger)
    basis: Mapped[str] = mapped_column(String(20))
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_runs.id"))


class ClimateDaily(Base):
    __tablename__ = "climate_daily"
    __table_args__ = (UniqueConstraint("region_key", "observed_on", name="uq_climate_region_day"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_key: Mapped[str] = mapped_column(ForeignKey("regions.key"), index=True)
    observed_on: Mapped[date] = mapped_column(Date)
    temperature_mean_c: Mapped[float | None] = mapped_column(Float)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_runs.id"))


class ImageEmbedding(Base):
    __tablename__ = "image_embeddings"
    __table_args__ = (
        UniqueConstraint("place_image_id", "model_version", name="uq_embedding_image_model"),
        Index("ix_image_embeddings_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    place_image_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("place_images.id", ondelete="CASCADE"), index=True)
    model_version: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float]] = mapped_column(Vector(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
