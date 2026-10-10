"""로그인 사용자 MY 탭·개인 맞춤 화면용 API.
- 홈 '저장한 곳과 닮은 곳' (similar)
- 내가 누른 닮았어요·별로예요 목록과 취소 (votes)
- 개인 맞춤 켜기·끄기, 기본 출발지 (settings)
- 저장한 곳에서 곧 열리는 축제 (festivals)
취향 계산은 app/recommender.py taste(), 사용자 신호 읽기는 app/main.py _user_signals() 를 그대로 쓴다."""

from datetime import date, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import SESSION_COOKIE, Principal, require_principal
from .db import get_db
from .models import FeedbackRecord, SavedRegion, UserPreference
from .schemas import Origin

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
    origin: Optional[Origin] = None


@router.put("/settings")
async def my_settings(body: SettingsBody, user: User, db: DB):
    """개인 맞춤 켜기·끄기와 기본 출발지(서울·부산·대구·광주·대전, 없으면 null)."""
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
