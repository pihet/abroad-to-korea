import hashlib
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from minio import Minio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .auth import Principal, require_principal, token_hash
from .db import get_db, session_factory
from .models import AuthSession, MediaAsset
from .settings import get_settings

router = APIRouter(prefix="/api/me/photos", tags=["media"])


def _minio() -> Minio:
    settings = get_settings()
    return Minio(settings.minio_endpoint, access_key=settings.minio_access_key,
                 secret_key=settings.minio_secret_key, secure=settings.minio_secure)


def _put(object_key: str, data: bytes, mime_type: str) -> None:
    client, bucket = _minio(), get_settings().minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    client.put_object(bucket, object_key, io.BytesIO(data), len(data), content_type=mime_type)


def _remove(object_key: str) -> None:
    _minio().remove_object(get_settings().minio_bucket, object_key)


async def persist_upload(data: bytes, mime_type: str, retain: bool, raw_session: str | None) -> str | None:
    """Store uploads only when the persistent stack is enabled; local demo mode stays file-free."""
    factory = session_factory()
    if factory is None:
        if retain:
            raise HTTPException(503, "사진 보관에는 DATABASE_URL 설정이 필요합니다.")
        return None
    now, owner_id = datetime.now(timezone.utc), None
    async with factory() as db:
        if raw_session:
            row = (await db.execute(select(AuthSession).where(
                AuthSession.token_hash == token_hash(raw_session), AuthSession.revoked_at.is_(None),
                AuthSession.idle_expires_at > now, AuthSession.absolute_expires_at > now))).scalar_one_or_none()
            owner_id = row.user_id if row else None
        if retain and owner_id is None:
            raise HTTPException(401, "사진 장기 보관에는 로그인이 필요합니다.")
        asset_id = uuid.uuid4()
        object_key = f"uploads/{now:%Y/%m/%d}/{asset_id}"
        try:
            await run_in_threadpool(_put, object_key, data, mime_type)
        except Exception as exc:
            raise HTTPException(503, "사진 저장소에 연결할 수 없습니다.") from exc
        asset = MediaAsset(id=asset_id, owner_user_id=owner_id, kind="user_upload", object_key=object_key,
                           mime_type=mime_type, size_bytes=len(data), sha256=hashlib.sha256(data).digest(),
                           retained_at=now if retain else None, delete_after=None if retain else now + timedelta(hours=24))
        db.add(asset)
        try:
            await db.commit()
        except Exception:
            await run_in_threadpool(_remove, object_key)
            raise
        return str(asset_id)


@router.post("/{asset_id}/retain")
async def retain_photo(asset_id: uuid.UUID, principal: Annotated[Principal, Depends(require_principal)],
                       db: Annotated[AsyncSession, Depends(get_db)]):
    asset = await db.get(MediaAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    if asset.owner_user_id != principal.id:
        raise HTTPException(403, "이 사진을 보관할 권한이 없습니다.")
    asset.owner_user_id = principal.id
    asset.retained_at = datetime.now(timezone.utc)
    asset.delete_after = None
    await db.commit()
    return {"ok": True, "asset_id": str(asset.id), "retained": True}


@router.delete("/{asset_id}")
async def delete_photo(asset_id: uuid.UUID, principal: Annotated[Principal, Depends(require_principal)],
                       db: Annotated[AsyncSession, Depends(get_db)]):
    asset = await db.get(MediaAsset, asset_id)
    if asset is None or asset.owner_user_id != principal.id:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    asset.retained_at = None
    asset.delete_after = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}
