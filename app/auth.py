import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import urlencode

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import AuthIdentity, AuthSession, EmailOutbox, OneTimeToken, SavedRegion, User, UserPreference
from .settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
me_router = APIRouter(prefix="/api/me", tags=["me"])
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
SESSION_COOKIE = "atk_session"
IDLE_TTL = timedelta(days=7)
ABSOLUTE_TTL = timedelta(days=30)
TOKEN_TTL = timedelta(hours=24)
AUTH_CACHE_TTL_SECONDS = 300


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def redis_client() -> Redis | None:
    url = get_settings().redis_url
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5) if url else None


async def rate_limit(key: str, maximum: int, seconds: int) -> None:
    client = await redis_client()
    if client is None:
        return
    try:
        count = await client.incr(f"rate:{key}")
        if count == 1:
            await client.expire(f"rate:{key}", seconds)
        if count > maximum:
            raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    except RedisError:
        return
    finally:
        await client.aclose()


class SignupBody(BaseModel):
    email: EmailStr
    nickname: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("nickname")
    @classmethod
    def clean_nickname(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("닉네임은 공백을 제외하고 2자 이상이어야 합니다.")
        return value


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ForgotPasswordBody(BaseModel):
    email: EmailStr


class ResetPasswordBody(TokenBody):
    password: str = Field(min_length=10, max_length=128)


class SavedRegionBody(BaseModel):
    region_key: str = Field(pattern=r"^[0-9]+_.{1,70}$")


@dataclass
class Principal:
    id: uuid.UUID
    email: str
    nickname: str
    status: str
    email_verified: bool
    session_id: uuid.UUID
    session_hash_hex: str


async def _principal_from_db(db: AsyncSession, raw_token: str) -> Principal | None:
    now = utcnow()
    row = (await db.execute(
        select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(
            AuthSession.token_hash == token_hash(raw_token), AuthSession.revoked_at.is_(None),
            AuthSession.idle_expires_at > now, AuthSession.absolute_expires_at > now,
            User.status == "active", User.deleted_at.is_(None)))).first()
    if row is None:
        return None
    session, user = row
    if now - session.last_seen_at > timedelta(minutes=5):
        session.last_seen_at = now
        session.idle_expires_at = min(now + IDLE_TTL, session.absolute_expires_at)
        await db.commit()
    return Principal(user.id, user.email, user.nickname, user.status, user.email_verified_at is not None,
                     session.id, session.token_hash.hex())


async def optional_principal(
    db: Annotated[AsyncSession, Depends(get_db)],
    raw_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Principal | None:
    if not raw_token:
        return None
    key = token_hash(raw_token).hex()
    client = await redis_client()
    if client is not None:
        try:
            try:
                cached = await client.get(f"auth:session:{key}")
            except RedisError:
                cached = None
            if cached:
                data = json.loads(cached)
                return Principal(uuid.UUID(data["id"]), data["email"], data["nickname"], "active",
                                 data["email_verified"], uuid.UUID(data["session_id"]), key)
        finally:
            await client.aclose()
    principal = await _principal_from_db(db, raw_token)
    if principal:
        await _cache_principal(principal)
    return principal


async def require_principal(principal: Annotated[Principal | None, Depends(optional_principal)]) -> Principal:
    if principal is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    return principal


async def _cache_principal(principal: Principal) -> None:
    client = await redis_client()
    if client is None:
        return
    try:
        value = json.dumps({"id": str(principal.id), "email": principal.email, "nickname": principal.nickname,
                            "email_verified": principal.email_verified, "session_id": str(principal.session_id)})
        await client.setex(f"auth:session:{principal.session_hash_hex}", AUTH_CACHE_TTL_SECONDS, value)
    except RedisError:
        return
    finally:
        await client.aclose()


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(SESSION_COOKIE, raw_token, max_age=int(ABSOLUTE_TTL.total_seconds()), httponly=True,
                        secure=get_settings().cookie_secure, samesite="lax", path="/")


async def _create_session(db: AsyncSession, user: User, request: Request, response: Response) -> Principal:
    now, raw = utcnow(), secrets.token_urlsafe(32)
    session = AuthSession(user_id=user.id, token_hash=token_hash(raw), idle_expires_at=now + IDLE_TTL,
                          absolute_expires_at=now + ABSOLUTE_TTL,
                          ip_address=request.client.host if request.client else None,
                          user_agent=request.headers.get("user-agent", "")[:512] or None)
    user.last_login_at = now
    db.add(session)
    await db.commit()
    principal = Principal(user.id, user.email, user.nickname, user.status, user.email_verified_at is not None,
                          session.id, session.token_hash.hex())
    await _cache_principal(principal)
    _set_session_cookie(response, raw)
    return principal


async def _issue_one_time_token(db: AsyncSession, user: User, purpose: str) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(OneTimeToken(user_id=user.id, purpose=purpose, token_hash=token_hash(raw), expires_at=utcnow() + TOKEN_TTL))
    db.add(EmailOutbox(recipient=user.email, template=purpose, payload={"token": raw}))
    return raw


async def _consume_token(db: AsyncSession, raw: str, purpose: str) -> tuple[OneTimeToken, User]:
    now = utcnow()
    row = (await db.execute(select(OneTimeToken, User).join(User).where(
        OneTimeToken.token_hash == token_hash(raw), OneTimeToken.purpose == purpose,
        OneTimeToken.used_at.is_(None), OneTimeToken.expires_at > now))).first()
    if row is None:
        raise HTTPException(400, "토큰이 유효하지 않거나 만료됐습니다.")
    token, user = row
    token.used_at = now
    return token, user


@router.post("/signup", status_code=201)
async def signup(body: SignupBody, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    email = normalize_email(body.email)
    await rate_limit(f"signup:{request.client.host if request.client else 'unknown'}", 10, 3600)
    exists = await db.scalar(select(AuthIdentity.id).where(AuthIdentity.provider == "email", AuthIdentity.provider_subject == email))
    if exists:
        raise HTTPException(409, "이미 이메일로 가입된 계정입니다.")
    user = User(email=email, nickname=body.nickname, status="active")
    user.identities.append(AuthIdentity(provider="email", provider_subject=email, provider_email=email,
                                        password_hash=password_hasher.hash(body.password)))
    db.add(user)
    await db.flush()
    db.add(UserPreference(user_id=user.id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "이미 이메일로 가입된 계정입니다.")
    return {"ok": True, "message": "가입되었습니다. 로그인해 주세요."}


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    email = normalize_email(body.email)
    await rate_limit(f"login:{request.client.host if request.client else 'unknown'}:{email}", 10, 900)
    row = (await db.execute(select(AuthIdentity, User).join(User).where(
        AuthIdentity.provider == "email", AuthIdentity.provider_subject == email, User.deleted_at.is_(None)))).first()
    if row is None:
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")
    identity, user = row
    try:
        password_hasher.verify(identity.password_hash or "", body.password)
    except (VerifyMismatchError, InvalidHashError):
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")
    if user.status != "active":
        raise HTTPException(403, "사용할 수 없는 계정입니다.")
    principal = await _create_session(db, user, request, response)
    return public_principal(principal)


def public_principal(principal: Principal) -> dict:
    return {"id": str(principal.id), "email": principal.email, "nickname": principal.nickname,
            "status": principal.status, "email_verified": principal.email_verified}


@router.post("/logout")
async def logout(response: Response, principal: Annotated[Principal, Depends(require_principal)],
                 db: Annotated[AsyncSession, Depends(get_db)]):
    session = await db.get(AuthSession, principal.session_id)
    if session:
        session.revoked_at = utcnow()
        await db.commit()
    client = await redis_client()
    if client is not None:
        try:
            try:
                await client.delete(f"auth:session:{principal.session_hash_hex}")
            except RedisError:
                pass
        finally:
            await client.aclose()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(principal: Annotated[Principal, Depends(require_principal)]):
    return public_principal(principal)


@router.delete("/me")
async def delete_account(response: Response, principal: Annotated[Principal, Depends(require_principal)],
                         db: Annotated[AsyncSession, Depends(get_db)]):
    from .models import MediaAsset
    now = utcnow()
    user = await db.get(User, principal.id)
    if user is None:
        raise HTTPException(404, "계정을 찾을 수 없습니다.")
    hashes = list((await db.scalars(select(AuthSession.token_hash).where(AuthSession.user_id == user.id))).all())
    user.status, user.deleted_at = "deleted", now
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    assets = (await db.scalars(select(MediaAsset).where(MediaAsset.owner_user_id == user.id,
                                                       MediaAsset.deleted_at.is_(None)))).all()
    for asset in assets:
        asset.retained_at, asset.delete_after = None, now
    await db.commit()
    await _invalidate_cached_sessions(hashes)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/password/forgot")
async def forgot_password(body: ForgotPasswordBody, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    email = normalize_email(body.email)
    await rate_limit(f"forgot:{request.client.host if request.client else 'unknown'}:{email}", 5, 3600)
    row = (await db.execute(select(AuthIdentity, User).join(User).where(
        AuthIdentity.provider == "email", AuthIdentity.provider_subject == email))).first()
    if row:
        await _issue_one_time_token(db, row[1], "reset_password")
        await db.commit()
    return {"ok": True, "message": "계정이 있으면 재설정 메일이 발송됩니다."}


@router.post("/password/reset")
async def reset_password(body: ResetPasswordBody, db: Annotated[AsyncSession, Depends(get_db)]):
    _, user = await _consume_token(db, body.token, "reset_password")
    identity = await db.scalar(select(AuthIdentity).where(AuthIdentity.user_id == user.id, AuthIdentity.provider == "email"))
    if identity is None:
        raise HTTPException(400, "이메일 로그인 계정이 아닙니다.")
    identity.password_hash = password_hasher.hash(body.password)
    hashes = list((await db.scalars(select(AuthSession.token_hash).where(AuthSession.user_id == user.id))).all())
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    await db.commit()
    await _invalidate_cached_sessions(hashes)
    return {"ok": True}


async def _invalidate_cached_sessions(hashes: list[bytes]) -> None:
    client = await redis_client()
    if client is None or not hashes:
        return
    try:
        await client.delete(*(f"auth:session:{value.hex()}" for value in hashes))
    except RedisError:
        return
    finally:
        await client.aclose()


OAUTH = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "kakao": {
        "authorize": "https://kauth.kakao.com/oauth/authorize",
        "token": "https://kauth.kakao.com/oauth/token",
        "userinfo": "https://kapi.kakao.com/v2/user/me",
        "scope": "profile_nickname account_email",
    },
}


def _oauth_credentials(provider: str) -> tuple[str, str | None]:
    settings = get_settings()
    client_id = getattr(settings, f"{provider}_client_id")
    client_secret = getattr(settings, f"{provider}_client_secret")
    if not client_id:
        raise HTTPException(503, f"{provider} 로그인이 설정되지 않았습니다.")
    return client_id, client_secret


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/oauth/{provider}/start")
async def oauth_start(provider: Literal["google", "kakao"], mode: Literal["login", "link"] = Query("login"),
                      principal: Annotated[Principal | None, Depends(optional_principal)] = None):
    if mode == "link" and principal is None:
        raise HTTPException(401, "계정 연결에는 로그인이 필요합니다.")
    client = await redis_client()
    if client is None:
        raise HTTPException(503, "OAuth에는 REDIS_URL 설정이 필요합니다.")
    client_id, _ = _oauth_credentials(provider)
    state, (verifier, challenge) = secrets.token_urlsafe(32), _pkce()
    payload = {"provider": provider, "mode": mode, "verifier": verifier,
               "user_id": str(principal.id) if principal else None}
    try:
        try:
            await client.setex(f"oauth:state:{state}", 600, json.dumps(payload))
        except RedisError as exc:
            raise HTTPException(503, "OAuth 상태 저장소에 연결할 수 없습니다.") from exc
    finally:
        await client.aclose()
    redirect_uri = f"{get_settings().public_base_url}/api/auth/oauth/{provider}/callback"
    params = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": OAUTH[provider]["scope"],
              "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return {"authorization_url": f"{OAUTH[provider]['authorize']}?{urlencode(params)}"}


async def _oauth_profile(provider: str, code: str, state_data: dict) -> tuple[str, str, str]:
    client_id, client_secret = _oauth_credentials(provider)
    redirect_uri = f"{get_settings().public_base_url}/api/auth/oauth/{provider}/callback"
    form = {"grant_type": "authorization_code", "client_id": client_id, "redirect_uri": redirect_uri,
            "code": code, "code_verifier": state_data["verifier"]}
    if client_secret:
        form["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(OAUTH[provider]["token"], data=form)
        if token_response.is_error:
            raise HTTPException(400, "소셜 로그인 토큰 교환에 실패했습니다.")
        access_token = token_response.json().get("access_token")
        profile_response = await client.get(OAUTH[provider]["userinfo"], headers={"Authorization": f"Bearer {access_token}"})
        if profile_response.is_error:
            raise HTTPException(400, "소셜 프로필을 불러오지 못했습니다.")
    profile = profile_response.json()
    if provider == "google":
        subject, email, nickname = str(profile.get("sub", "")), profile.get("email"), profile.get("name")
        verified = profile.get("email_verified") is True
    else:
        account, props = profile.get("kakao_account") or {}, profile.get("properties") or {}
        subject, email = str(profile.get("id", "")), account.get("email")
        nickname, verified = props.get("nickname") or account.get("profile", {}).get("nickname"), account.get("is_email_verified") is True
    if not subject or not email or not verified:
        raise HTTPException(400, "인증된 이메일 제공에 동의해야 가입할 수 있습니다.")
    return subject, normalize_email(email), (nickname or email.split("@", 1)[0])[:40]


@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: Literal["google", "kakao"], code: str, state: str, request: Request,
                         db: Annotated[AsyncSession, Depends(get_db)]):
    client = await redis_client()
    if client is None:
        raise HTTPException(503, "OAuth에는 REDIS_URL 설정이 필요합니다.")
    try:
        try:
            raw = await client.getdel(f"oauth:state:{state}")
        except RedisError as exc:
            raise HTTPException(503, "OAuth 상태 저장소에 연결할 수 없습니다.") from exc
    finally:
        await client.aclose()
    if not raw:
        raise HTTPException(400, "OAuth 요청이 만료됐거나 이미 사용됐습니다.")
    state_data = json.loads(raw)
    if state_data["provider"] != provider:
        raise HTTPException(400, "OAuth 공급자가 일치하지 않습니다.")
    subject, email, nickname = await _oauth_profile(provider, code, state_data)
    identity = await db.scalar(select(AuthIdentity).where(AuthIdentity.provider == provider,
                                                          AuthIdentity.provider_subject == subject))
    if state_data["mode"] == "link":
        if identity:
            raise HTTPException(409, "이미 다른 계정에 연결된 로그인 수단입니다.")
        user = await db.get(User, uuid.UUID(state_data["user_id"]))
        if user is None or user.status != "active":
            raise HTTPException(401, "연결할 계정을 찾을 수 없습니다.")
        db.add(AuthIdentity(user_id=user.id, provider=provider, provider_subject=subject, provider_email=email))
        await db.commit()
        return RedirectResponse(f"{get_settings().public_base_url}/?account_linked={provider}", status_code=303)
    if identity:
        user = await db.get(User, identity.user_id)
        if user is None or user.status != "active" or user.deleted_at is not None:
            raise HTTPException(403, "사용할 수 없는 계정입니다.")
    else:
        user = User(email=email, nickname=nickname, status="active", email_verified_at=utcnow())
        user.identities.append(AuthIdentity(provider=provider, provider_subject=subject, provider_email=email))
        db.add(user)
        await db.flush()
        db.add(UserPreference(user_id=user.id))
    response = RedirectResponse(f"{get_settings().public_base_url}/", status_code=303)
    await _create_session(db, user, request, response)
    return response


@router.delete("/identities/{provider}")
async def unlink_identity(provider: Literal["email", "google", "kakao"],
                          principal: Annotated[Principal, Depends(require_principal)],
                          db: Annotated[AsyncSession, Depends(get_db)]):
    identities = list((await db.scalars(select(AuthIdentity).where(AuthIdentity.user_id == principal.id))).all())
    target = next((identity for identity in identities if identity.provider == provider), None)
    if target is None:
        raise HTTPException(404, "연결된 로그인 수단이 아닙니다.")
    if len(identities) == 1:
        raise HTTPException(409, "마지막 로그인 수단은 해제할 수 없습니다.")
    await db.delete(target)
    await db.commit()
    return {"ok": True}


@me_router.get("/saved-regions")
async def saved_regions(principal: Annotated[Principal, Depends(require_principal)],
                        db: Annotated[AsyncSession, Depends(get_db)]):
    rows = (await db.scalars(select(SavedRegion).where(SavedRegion.user_id == principal.id).order_by(SavedRegion.created_at))).all()
    return {"regions": [row.region_key for row in rows]}


@me_router.post("/saved-regions", status_code=201)
async def save_region(body: SavedRegionBody, principal: Annotated[Principal, Depends(require_principal)],
                      db: Annotated[AsyncSession, Depends(get_db)]):
    db.add(SavedRegion(user_id=principal.id, region_key=body.region_key))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return {"ok": True, "region_key": body.region_key}


@me_router.delete("/saved-regions/{region_key}")
async def unsave_region(region_key: str, principal: Annotated[Principal, Depends(require_principal)],
                        db: Annotated[AsyncSession, Depends(get_db)]):
    await db.execute(delete(SavedRegion).where(SavedRegion.user_id == principal.id, SavedRegion.region_key == region_key))
    await db.commit()
    return {"ok": True}
