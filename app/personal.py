"""로그인 사용자 MY 탭·개인 맞춤 화면용 API.
- 홈 '저장한 곳과 닮은 곳' (similar)
- 내가 누른 닮았어요·별로예요 목록과 취소 (votes)
- 개인 맞춤 켜기·끄기, 기본 출발지 (settings)
- 저장한 곳에서 곧 열리는 축제 (festivals)
- 프로필 사진 (avatar): 256px 정사각형 JPEG 로 줄여 MinIO 에 둔다. 원본은 저장하지 않는다
취향 계산은 app/recommender.py taste(), 사용자 신호 읽기는 app/main.py _user_signals() 를 그대로 쓴다."""

import hashlib
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from . import media
from .auth import SESSION_COOKIE, Principal, require_principal
from .db import get_db
from .models import FeedbackRecord, MediaAsset, SavedRegion, UserPreference
from .settings import get_settings

router = APIRouter(prefix="/api/my", tags=["my"])
User = Annotated[Principal, Depends(require_principal)]
DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/similar")
async def my_similar(limit: int = Query(10, ge=1, le=30),
                     raw_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE)):
    """홈 '저장한 곳과 닮은 곳'. 비로그인·개인 맞춤 꺼짐·신호 부족이면 빈 목록."""
    from . import main as m  # main 이 이 모듈을 불러오므로 함수 안에서 불러온다
    s = await m._user_signals(raw_session)
    taste = m._taste_of(s)
    if taste is None:
        return {"on": False, "regions": []}
    return {"on": True, "regions": [{"key": k, "reason": why}
                                    for k, why in m.engine.similar_regions(taste, set(s["saved"]), limit)]}


@router.get("/votes")
async def my_votes(user: User, db: DB):
    """내가 누른 닮았어요(+1)·별로예요(−1). 같은 관광지를 여러 번 눌렀으면 마지막 것만, 최근 순."""
    from . import main as m
    rows = (await db.execute(select(FeedbackRecord.attraction_id, FeedbackRecord.sigungu_key, FeedbackRecord.value)
                             .where(FeedbackRecord.user_id == user.id)
                             .order_by(FeedbackRecord.created_at.desc()))).all()
    out, seen = [], set()
    for cid, key, value in rows:
        if cid in seen:
            continue
        seen.add(cid)
        it = m.engine.I["items"].get(str(cid))
        out.append({"attraction_id": cid, "value": value, "name": it["title"] if it else None,
                    "image_url": f"/images/kr/{cid}" if it else None,
                    "region": {"key": key, "name": key.partition("_")[2]}})
    return {"votes": out}


@router.delete("/votes/{attraction_id}")
async def my_vote_delete(attraction_id: str, user: User, db: DB):
    """관광지 하나에 누른 반응을 모두 지운다 (개인 맞춤에서 빠진다). 평가용 피드백 파일 기록은 남는다."""
    n = (await db.execute(delete(FeedbackRecord).where(FeedbackRecord.user_id == user.id,
                                                        FeedbackRecord.attraction_id == attraction_id))).rowcount
    await db.commit()
    if not n:
        raise HTTPException(404, "누른 기록이 없습니다.")
    return {"ok": True, "deleted": n}


class SettingsBody(BaseModel):
    personal: bool
    origin: Optional[str] = Field(None, max_length=40)


@router.put("/settings")
async def my_settings(body: SettingsBody, user: User, db: DB):
    """개인 맞춤 켜기·끄기와 기본 출발지(5개 도시 이름 또는 시군구 key '51_강릉시', 없으면 null)."""
    from . import main as m
    if body.origin and m.engine.ctx.origin_point(body.origin) is None:
        raise HTTPException(400, "출발지가 올바르지 않습니다.")
    pref = await db.get(UserPreference, user.id)
    if pref is None:
        pref = UserPreference(user_id=user.id, preferences={})
        db.add(pref)
    pref.preferences = {**(pref.preferences or {}), "personal": body.personal}  # 새 dict 로 바꿔야 JSONB 변경이 저장된다
    pref.origin = body.origin
    await db.commit()
    return {"ok": True, "personal": body.personal, "origin": body.origin}


@router.get("/festivals")
async def my_festivals(user: User, db: DB, days: int = Query(31, ge=1, le=62)):
    """저장한 시군구에서 오늘부터 days일 안에 열리는(또는 열리고 있는) 축제."""
    from . import main as m
    saved = set((await db.scalars(select(SavedRegion.region_key).where(SavedRegion.user_id == user.id))).all())
    if not saved:
        return {"items": []}
    s = date.today()
    items = await m.catalog.festivals(db, s, s + timedelta(days=days - 1))
    return {"start": s.isoformat(), "days": days, "items": [f for f in items if f["region_key"] in saved]}


AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 256


def _avatar_jpeg(data: bytes) -> bytes:
    """가운데를 정사각형으로 잘라 256px JPEG 로. 이미지가 아니면 ValueError."""
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception:
        raise ValueError("이미지 파일이 아닙니다.")
    img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


async def _drop_avatar(db: AsyncSession, pref: UserPreference | None) -> None:
    """지금 프로필 사진을 지울 대상으로 표시하고(실제 삭제는 src/ops/cleanup_media.py) 설정에서 뺀다."""
    old = (pref.preferences or {}).get("avatar") if pref else None
    if old:
        asset = await db.get(MediaAsset, uuid.UUID(old))
        if asset is not None:
            asset.retained_at, asset.delete_after = None, datetime.now(timezone.utc)
        pref.preferences = {k: v for k, v in pref.preferences.items() if k != "avatar"}


@router.post("/avatar")
async def my_avatar_upload(user: User, db: DB, file: UploadFile = File(...)):
    """프로필 사진 바꾸기. 5MB 이하 이미지만."""
    data = await file.read(AVATAR_MAX_BYTES + 1)
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(413, "5MB 이하 사진만 올릴 수 있습니다.")
    try:
        jpeg = await run_in_threadpool(_avatar_jpeg, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    asset_id, now = uuid.uuid4(), datetime.now(timezone.utc)
    key = f"avatars/{user.id}/{asset_id}.jpg"
    try:
        await run_in_threadpool(media._put, key, jpeg, "image/jpeg")
    except Exception:
        raise HTTPException(503, "사진 저장소에 연결할 수 없습니다.")
    pref = await db.get(UserPreference, user.id)
    if pref is None:
        pref = UserPreference(user_id=user.id, preferences={})
        db.add(pref)
    await _drop_avatar(db, pref)
    db.add(MediaAsset(id=asset_id, owner_user_id=user.id, kind="avatar", object_key=key, mime_type="image/jpeg",
                      size_bytes=len(jpeg), sha256=hashlib.sha256(jpeg).digest(), retained_at=now))
    pref.preferences = {**(pref.preferences or {}), "avatar": str(asset_id)}
    await db.commit()
    return {"ok": True, "avatar_url": f"/api/my/avatar/{asset_id}"}


@router.delete("/avatar")
async def my_avatar_delete(user: User, db: DB):
    """프로필 사진을 지우고 이름 첫 글자로 돌아간다."""
    await _drop_avatar(db, await db.get(UserPreference, user.id))
    await db.commit()
    return {"ok": True}


@router.get("/avatar/{asset_id}")
async def my_avatar_file(asset_id: uuid.UUID, user: User, db: DB):
    """프로필 사진 파일. 본인 것만 (다른 사람에게 보여 주는 화면이 아직 없다)."""
    asset = await db.get(MediaAsset, asset_id)
    if (asset is None or asset.kind != "avatar" or asset.owner_user_id != user.id
            or asset.deleted_at is not None or asset.delete_after is not None):  # 바꾸거나 지운 사진은 바로 안 보이게
        raise HTTPException(404, "사진을 찾을 수 없습니다.")

    def read() -> bytes:
        r = media._minio().get_object(get_settings().minio_bucket, asset.object_key)
        try:
            return r.read()
        finally:
            r.close(); r.release_conn()
    try:
        data = await run_in_threadpool(read)
    except Exception:
        raise HTTPException(503, "사진 저장소에 연결할 수 없습니다.")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})  # 로그아웃한 뒤 같은 브라우저에 남지 않게
