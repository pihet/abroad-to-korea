"""로그인 사용자 개인 맞춤 화면용 API (홈 '저장한 곳과 닮은 곳').
취향 계산은 app/recommender.py taste(), 사용자 신호 읽기는 app/main.py _user_signals() 를 그대로 쓴다."""

from typing import Optional

from fastapi import APIRouter, Cookie, Query

from .auth import SESSION_COOKIE

router = APIRouter(prefix="/api/my", tags=["my"])


@router.get("/similar")
async def my_similar(limit: int = Query(10, ge=1, le=30),
                     raw_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE)):
    """취향(좋아요·별로예요·하트 3개 이상)과 대표 사진이 닮은 시군구. 이미 저장한 곳은 뺀다. 꺼져 있으면 빈 목록."""
    from . import main as m  # main 이 이 모듈을 불러오므로 순환을 피해 함수 안에서 읽는다
    s = await m._user_signals(raw_session)
    taste = None if s is None else m.engine.taste(*s)
    if taste is None:
        return {"on": False, "regions": []}
    return {"on": True, "regions": [{"key": k, "reason": why} for k, why in m.engine.similar_regions(taste, set(s[2]), limit)]}
