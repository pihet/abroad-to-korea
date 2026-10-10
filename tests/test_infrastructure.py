from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.auth import ensure_oauth_auto_link_allowed, normalize_email, password_hasher, token_hash
from app.models import Base, User
from app.query_cache import QueryCache
from src.ingest.publish_tour import festival_rows, region_map


def test_auth_primitives():
    assert normalize_email("  User@Example.COM ") == "user@example.com"
    assert token_hash("same") == token_hash("same")
    assert token_hash("same") != token_hash("different")
    encoded = password_hasher.hash("long-enough-password")
    assert password_hasher.verify(encoded, "long-enough-password")
    assert "long-enough-password" not in encoded


def test_initial_schema_has_durable_and_cache_source_tables():
    expected = {
        "users", "auth_identities", "auth_sessions", "one_time_tokens", "email_outbox",
        "saved_regions", "media_assets", "feedback", "data_sources", "ingestion_runs", "raw_objects",
        "regions", "places", "place_images", "festivals", "visitor_metrics", "climate_daily", "image_embeddings",
    }
    assert expected <= set(Base.metadata.tables)
    assert Base.metadata.tables["image_embeddings"].c.embedding.type.dim == 512


def test_database_identity_constraints():
    users = Base.metadata.tables["users"]
    identities = Base.metadata.tables["auth_identities"]
    feedback = Base.metadata.tables["feedback"]
    assert "uq_users_email_normalized" in {index.name for index in users.indexes}
    assert "uq_auth_user_provider" in {constraint.name for constraint in identities.constraints}
    assert {"uq_feedback_user_vote", "uq_feedback_anonymous_vote"} <= {index.name for index in feedback.indexes}


def test_oauth_only_auto_links_to_verified_email_accounts():
    unverified = User(email="user@example.com", nickname="user", status="active")
    with pytest.raises(HTTPException) as exc:
        ensure_oauth_auto_link_allowed(unverified)
    assert exc.value.status_code == 409

    verified = User(email="user@example.com", nickname="user", status="active",
                    email_verified_at=datetime.now(timezone.utc))
    ensure_oauth_auto_link_allowed(verified)


def test_query_cache_memory_fallback(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    cache = QueryCache(max_items=2)
    cache["a"], cache["b"], cache["c"] = {"n": 1}, {"n": 2}, {"n": 3}
    assert "a" not in cache and cache["b"] == {"n": 2} and cache["c"] == {"n": 3}


def test_current_raw_tour_data_is_publishable():
    regions = region_map()
    festivals, source = festival_rows()
    assert len(regions) >= 200
    assert source is not None and festivals
    assert all(row.get("contentid") and row.get("title") for row in festivals)
