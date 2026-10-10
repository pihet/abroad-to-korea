"""FastAPI 서버: 추천 API + 사진 제공 + 빌드된 프론트(web/dist).

실행 (저장소 루트에서):
    .venv/bin/uvicorn app.main:app --port 8000
    → http://localhost:8000  (web/dist 가 있으면 화면, 없으면 /docs 에서 API 확인)
"""

import io
import json
import sys
import time
from contextlib import asynccontextmanager
import urllib.error
import urllib.request
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from collections import Counter

from .activities import GROUPS as ACT_GROUPS, Activities
from .neighborhoods import CREDIT as DONG_CREDIT, Neighborhoods
from .regions import Regions
from .context import DATA_SOURCES, ORIGINS, ROOT
from .rain import Rain, RainError
from .courses import Courses
from .cost import Cost
from .travel_time import TravelError, TravelTime
from .search import Search
from .recommender import PERSONAL_MIN, PERSONAL_WEIGHT, PRIORITIES, Engine, cp, sc
from .schemas import ActivitiesResponse, AnalyzeResponse, Crop, Feedback, RecommendRequest, RecommendResponse
from .auth import me_router, router as auth_router
from .db import close_db, session_factory
from .auth import SESSION_COOKIE, _principal_from_db, token_hash
from .media import persist_upload, router as media_router
from .models import AuthSession, FeedbackRecord, SavedRegion
from sqlalchemy import select

MAX_UPLOAD = 15 * 1024 * 1024
BAD_IMAGE = "사진 파일을 열 수 없습니다. JPG·PNG·WEBP·HEIC 사진인지 확인해 주세요."
APP_DATA = ROOT / "data/interim/app"
KR_FULL = APP_DATA / "kr_full"       # TourAPI 원본 사진 캐시 (처음 요청 때 받는다)
TOUR_THUMB = APP_DATA / "tour_thumb"  # 활동 목록 썸네일 캐시
EXTRA_DIRS = [ROOT / "data/raw/tourapi/detailImage2_ct39", ROOT / "data/raw/tourapi/detailImage2_ct39_sample",
              ROOT / "data/raw/tourapi/detailImage2"]  # 추가 사진 원문 (음식점: 누를 때 받아 저장 / 표본 / 관광지 매일 수집)
EXTRA_IMG = APP_DATA / "extra_img"  # 추가 사진 파일 캐시
FEEDBACK = APP_DATA / "feedback.jsonl"
WEB_DIST = ROOT / "web/dist"

engine: Optional[Engine] = None
acts: Optional[Activities] = None
regions: Optional[Regions] = None
hoods: Optional[Neighborhoods] = None
MISSING_PHOTOS: set[str] = set()


@asynccontextmanager
async def lifespan(_app):
    global engine, acts, regions, hoods, rain, courses, search, cost, travel
    t = time.time()
    engine = Engine()
    acts = Activities()
    regions = Regions(engine, acts)
    hoods = Neighborhoods(acts, {s['sido']: s['key'].split('_')[0] for s in regions.static.values()})
    rain = Rain(engine.ctx.centers)
    courses = Courses(acts, engine)
    cost = Cost()
    travel = TravelTime()
    search = Search(acts, hoods, regions.static)
    KR_FULL.mkdir(parents=True, exist_ok=True)
    TOUR_THUMB.mkdir(parents=True, exist_ok=True)
    print(f"[startup] 모델·인덱스 준비 {time.time() - t:.0f}초", flush=True)
    yield
    await close_db()


app = FastAPI(title="닮은꼴 국내 여행지 API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(media_router)


@app.get("/api/health")
def health():
    return {"ok": engine is not None}


@app.get("/api/demo-photos")
def demo_photos():
    return {"is_example": False, "photos": engine.demo_photos()}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(image: Optional[UploadFile] = File(None), demo_photo_id: Optional[str] = Form(None),
                  crop: Optional[str] = Form(None), source_attraction_id: Optional[str] = Form(None),
                  retain_photo: bool = Form(False), store_photo: bool = Form(True),
                  raw_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE)):
    media_asset_id = None
    if image is not None:
        data = await image.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "사진이 15MB보다 큽니다. 더 작은 사진을 골라 주세요.")
    elif demo_photo_id:
        known = {p["photo_id"] for p in engine.demo_photos()}
        if demo_photo_id not in known:
            raise HTTPException(404, "데모 사진을 찾을 수 없습니다.")
        data = (sc.IMG_DIR / demo_photo_id).read_bytes()
    else:
        raise HTTPException(400, "사진을 올리거나 데모 사진을 골라 주세요.")
    try:
        c = Crop(**json.loads(crop)).model_dump() if crop else None
    except Exception:
        raise HTTPException(400, "자를 영역 값이 올바르지 않습니다.")
    try:
        img, meta = engine.open_image(data, c)
    except Exception:
        raise HTTPException(400, BAD_IMAGE)
    exclude = None
    if source_attraction_id:  # 국내 관광지 사진으로 다시 찾기: 그 시군구는 후보에서 뺀다
        exclude = engine.region_of(source_attraction_id)
        if exclude is None:
            raise HTTPException(404, "출발 관광지를 찾을 수 없습니다.")
    qid, tags = engine.analyze(img, exclude)
    # 올린 사진은 사용자가 '계속 보관'에 동의했을 때만 저장한다 (로그인 필요). 동의하지 않으면 분석만 하고 버린다
    if image is not None and store_photo and retain_photo:
        media_asset_id = await persist_upload(data, image.content_type or "application/octet-stream", retain_photo, raw_session)
    return {"query_id": qid, "scene_tags": tags, "image": meta, "excluded_sigungu": _sigungu(exclude),
            "media_asset_id": media_asset_id}


def _sigungu(ri):
    if ri is None:
        return None
    key = engine.region_keys[ri]
    return {"key": key, "name": key.split("_", 1)[1]}


@app.post("/api/convert")
async def convert(image: UploadFile = File(...)):
    """브라우저가 못 띄우는 사진(HEIC)을 미리보기용 JPEG 로 바꾼다. 분석은 원본으로 한다."""
    data = await image.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "사진이 15MB보다 큽니다. 더 작은 사진을 골라 주세요.")
    try:
        img, _ = engine.open_image(data)
    except Exception:
        raise HTTPException(400, BAD_IMAGE)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return Response(buf.getvalue(), media_type="image/jpeg")


async def _user_taste(raw_session):
    """로그인 사용자의 좋아요·별로예요·하트로 만든 취향 (engine.taste). 비로그인·DB 없음·신호 부족이면 None."""
    factory = session_factory()
    if factory is None or not raw_session:
        return None
    async with factory() as db:
        principal = await _principal_from_db(db, raw_session)
        if principal is None:
            return None
        votes = (await db.execute(select(FeedbackRecord.attraction_id, FeedbackRecord.value)
                                  .where(FeedbackRecord.user_id == principal.id))).all()
        saved = (await db.scalars(select(SavedRegion.region_key).where(SavedRegion.user_id == principal.id))).all()
    return engine.taste([a for a, v in votes if v == 1], [a for a, v in votes if v == -1], saved)


@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest, raw_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE)):
    if req.query_id not in engine.cache:
        raise HTTPException(404, "분석 결과가 만료됐습니다. 사진을 다시 분석해 주세요.")
    if req.sido and req.sido not in {s["sido"] for s in regions.static.values()}:
        raise HTTPException(400, "시도 이름이 올바르지 않습니다.")
    if req.travel_month is None and req.priority == "season":
        raise HTTPException(400, "'고른 달에 가기 좋은 곳'은 여행 월을 골라야 쓸 수 있습니다.")
    if req.travel_month is None and "mild" in req.filters:
        raise HTTPException(400, "날씨 조건은 여행 월을 골라야 쓸 수 있습니다.")
    allowed = regions.allowed(req.travel_month, req.filters, req.sido)
    exclude = engine.cache[req.query_id]["exclude"]
    if allowed is not None and exclude is not None:  # 필터 개수도 출발 시군구를 뺀 수로 보여 준다
        allowed = allowed - {exclude}
    taste = await _user_taste(raw_session)
    r = await run_in_threadpool(engine.recommend, req.query_id, req.travel_month, req.priority, req.origin, req.kept_tags,
                                req.limit, req.offset, allowed, taste)
    q = engine.cache[req.query_id]
    return {
        "query": {"query_id": req.query_id, "scene_tags": [t["tag"] for t in q["tags"]], "kept_tags": req.kept_tags,
                  "month": req.travel_month, "priority": req.priority, "origin": req.origin,
                  "filters": req.filters, "sido": req.sido, "allowed_regions": None if allowed is None else len(allowed),
                  "excluded_sigungu": _sigungu(q["exclude"])},
        "model": {"visual": "CLIP ViT-B/32 (frozen) · 관광지별 최고 1장 → 시군구 vote100 → 상위 30곳",
                  "rerank": "30곳 안에서만 재정렬 · 시각 가중치 0.5 이상 · 단일 종합점수 없음",
                  "personal": {"on": taste is not None, "signals": taste["signals"] if taste else 0,
                               "min_signals": PERSONAL_MIN, "weight": PERSONAL_WEIGHT},
                  "priorities": list(PRIORITIES)},
        "total_candidates": r["total"], "candidates": r["candidates"], "data_sources": DATA_SOURCES,
    }


@app.post("/api/feedback")
async def feedback(fb: Feedback, raw_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE)):
    factory = session_factory()
    if factory is not None:
        async with factory() as db:
            user_id = None
            if raw_session:
                now = datetime.now(timezone.utc)
                session = await db.scalar(select(AuthSession).where(
                    AuthSession.token_hash == token_hash(raw_session), AuthSession.revoked_at.is_(None),
                    AuthSession.idle_expires_at > now, AuthSession.absolute_expires_at > now))
                user_id = session.user_id if session else None
            query = select(FeedbackRecord).where(FeedbackRecord.query_id == fb.query_id,
                                                  FeedbackRecord.sigungu_key == fb.sigungu_key,
                                                  FeedbackRecord.attraction_id == fb.attraction_id)
            query = query.where(FeedbackRecord.user_id == user_id) if user_id else query.where(FeedbackRecord.user_id.is_(None))
            record = await db.scalar(query)
            if record:
                record.value = fb.value
            else:
                db.add(FeedbackRecord(user_id=user_id, **fb.model_dump()))
            await db.commit()
        return {"ok": True}
    APP_DATA.mkdir(parents=True, exist_ok=True)
    with FEEDBACK.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**fb.model_dump(), "ts": time.time()}, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.get("/images/kr/{cid}")
def kr_image(cid: str):
    it = engine.I["items"].get(cid)
    if it is None:
        raise HTTPException(404)
    cached = KR_FULL / f"{cid}.jpg"
    if not cached.exists() and it.get("firstimage"):
        try:  # 목록에 있는 공식 원본 주소만 받는다 (요청의 임의 주소는 쓰지 않음)
            req = urllib.request.Request(it["firstimage"], headers={"User-Agent": cp.UA})
            cached.write_bytes(urllib.request.urlopen(req, timeout=15).read())
        except Exception:
            pass
    path = cached if cached.exists() else cp.KR_DIR / f"{cid}.jpg"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/regions")
def region_table(month: Optional[int] = Query(None, ge=1, le=12), origin: Optional[str] = None):
    """시군구별 조건 값·필터 통과 여부·대표 사진. 조건 칩의 곳 수와 '사진 없이 둘러보기'에 쓴다."""
    if origin is not None and origin not in ORIGINS:
        raise HTTPException(400, "출발지가 올바르지 않습니다.")
    rows = []
    for r in regions.month_table(month):
        k = tuple(r["key"].split("_", 1))
        rows.append({**{x: v for x, v in r.items() if x != "ri"}, "photo": engine.region_photo(r["ri"]),
                     "kind_photos": {kd: engine.region_photo(r["ri"], kd) for kd in engine.KINDS},
                     "distance_km": engine.ctx.distance(k, origin) if origin else None})
    return {"is_example": False, "month": month,
            "filters": regions.filter_meta(month),
            "sidos": sorted({r["sido"] for r in rows}), "regions": rows}


@app.get("/api/rankings")
def rankings(month: Optional[int] = Query(None, ge=1, le=12)):
    """이 달의 목록. 목록마다 거르는 조건 하나 + 정렬 기준 하나, 둘 다 화면에 적는다 (종합점수 없음)."""
    rows = regions.month_table(month)
    meta = {f["key"]: f for f in regions.filter_meta(month)}
    n_act = {k: sum(r["group"] not in ("festival", "food") for r in v) for k, v in acts.by_region.items()}
    n_fest = {r["key"]: sum(i["group"] == "festival" for i in acts.for_region(r["key"], month)[1]) for r in rows}

    def top(pred, sort_key, value, unit, n=6):
        sel = sorted((r for r in rows if pred(r) and sort_key(r) is not None), key=sort_key)[:n]
        return [{"key": r["key"], "name": r["name"], "sido": r["sido"], "value": value(r), "unit": unit,
                 "photo": engine.region_photo(r["ri"])} for r in sel]

    if month is None:  # 여행 월 없이: 연간·앞으로 열릴 축제 기준. 혼잡도는 지역 상세에서만 보여 준다
        n_up = {r["key"]: sum(i["group"] == "festival" and i.get("schedule") == "예정" for i in acts.for_region(r["key"], None)[1]) for r in rows}
        lists = [
            {"id": "mountain", "title": "산·숲이 많은 곳",
             "basis": "산·계곡·숲·자연공원 관광지가 많은 순 (TourAPI 분류)",
             "items": top(lambda r: r["mountain_n"] > 0, lambda r: -r["mountain_n"], lambda r: r["mountain_n"], "곳")},
            {"id": "rural-activities", "title": "할 거리가 많은 시골·소도시",
             "basis": "시골·소도시 중 관광지·레포츠 수가 많은 순 (축제 제외)",
             "items": top(lambda r: r["flags"]["rural"], lambda r: -n_act.get(r["key"], 0), lambda r: n_act.get(r["key"], 0), "곳")},
            {"id": "festivals", "title": "앞으로 축제가 많이 열리는 곳",
             "basis": "2026년 일정 중 아직 끝나지 않은 축제 수가 많은 순",
             "items": top(lambda r: n_up[r["key"]] > 0, lambda r: -n_up[r["key"]], lambda r: n_up[r["key"]], "개")},
        ]
        return {"is_example": False, "month": None, "lists": lists}

    lists = [
        {"id": "quiet-sea", "title": f"{month}월, 방문객이 적은 바닷가",
         "basis": "바다 가까운 곳 중 그 달 외지인 방문자 수가 적은 순",
         "items": top(lambda r: r["flags"]["sea"], lambda r: r["visitors"], lambda r: round(r["visitors"] / 10000), "만 명")},
        {"id": "weather-mountain", "title": f"{month}월, {meta['mild']['label']} 중 산·숲이 많은 곳",
         "basis": f"{meta['mild']['basis']} 중 산·숲 관광지가 많은 순",
         "items": top(lambda r: r["flags"]["mild"] and r["mountain_n"] > 0, lambda r: -r["mountain_n"], lambda r: r["mountain_n"], "곳")},
        {"id": "calmer-than-usual", "title": f"{month}월이 평소보다 한산한 곳",
         "basis": "그 달 방문자 ÷ 최근 12개월 평균 × 100 이 낮은 순 (100 = 평소)",
         "items": top(lambda r: r["congestion_index"] is not None and r["congestion_index"] < 100,
                      lambda r: r["congestion_index"], lambda r: r["congestion_index"], ""),
         "empty": f"{month}월은 평소(100)보다 한산한 시군구가 없습니다. 전국이 평소보다 붐비는 달입니다."},
        {"id": "rural-activities", "title": "할 거리가 많은 시골·소도시",
         "basis": "시골·소도시 중 관광지·레포츠 수가 많은 순 (축제 제외)",
         "items": top(lambda r: r["flags"]["rural"], lambda r: -n_act.get(r["key"], 0), lambda r: n_act.get(r["key"], 0), "곳")},
        {"id": "festivals", "title": f"{month}월에 축제가 열리는 곳",
         "basis": f"2026년 {month}월에 기간이 걸친 축제 수가 많은 순",
         "items": top(lambda r: n_fest[r["key"]] > 0, lambda r: -n_fest[r["key"]], lambda r: n_fest[r["key"]], "개")},
    ]
    return {"is_example": False, "month": month, "lists": lists}


@app.get("/api/search")
def search_names(q: str = Query(..., min_length=1, max_length=40), limit: int = Query(20, ge=1, le=50)):
    """읍·면·동과 장소(관광지·레포츠·음식점·축제) 이름 검색. 이름 앞에서 맞는 것 → 안에서 맞는 것 → 초성으로 맞는 것 순."""
    return {"q": q, **search.find(q, limit)}


@app.get("/api/festivals")
def festivals(start: Optional[date] = None, days: int = Query(7, ge=1, le=31), limit: int = Query(12, ge=1, le=50)):
    """start(기본 오늘)부터 days일 안에 열리는 축제. 두 달 넘게 하는 상설 행사는 뺀다. 누르면 그 지역 상세로 간다."""
    s = start or date.today()
    e = s + timedelta(days=days - 1)
    items = acts.festivals_between(s.strftime("%Y%m%d"), e.strftime("%Y%m%d"))
    for f in items:
        st = regions.static.get(f["region_key"])
        f["region"] = {"key": f["region_key"], "name": st["name"], "sido": st["sido"]} if st else None
    items = [f for f in items if f["region"]]
    return {"is_example": False, "start": s.isoformat(), "end": e.isoformat(), "total": len(items), "items": items[:limit],
            "basis": "한국관광공사 TourAPI 축제 일정 (2026년). 두 달 넘게 하는 상설 행사는 제외"}


@app.get("/api/regions/{key}/profile")
def region_profile(key: str, month: Optional[int] = Query(None, ge=1, le=12)):
    """지역 상세: 조건 값, 12개월 날씨·방문자, 읍·면·동 경계와 활동지가 몰린 동네 Top 5."""
    row = next((r for r in regions.month_table(month) if r["key"] == key), None)
    if row is None:
        raise HTTPException(404, "시군구를 찾을 수 없습니다.")
    k = tuple(key.split("_", 1))
    months = []
    for m in range(1, 13):
        cg, cl = engine.ctx.congestion(k, m), engine.ctx.climate(k, m)
        months.append({"month": m, "temp_c": cl["temp_c"] if cl else None, "rain_days": cl["rain_days"] if cl else None,
                       "visitors": cg["visitors"] if cg else None, "congestion_index": cg["index"] if cg else None,
                       "basis": cg["basis"] if cg else None, "basis_month": cg["basis_month"] if cg else None})
    return {"is_example": False, "month": month,
            "region": {x: v for x, v in row.items() if x != "ri"}, "photo": engine.region_photo(row["ri"]),
            "filters": regions.filter_meta(month), "months": months,
            "neighborhoods": hoods.for_region(key), "focus": hoods.focus(key), "food": acts.food_summary(key),
            "notes": ["비 예보: 오늘부터 16일 안은 Open-Meteo 일기예보, 그 밖은 Open-Meteo 2021~2025년 같은 날짜 기록 (CC BY 4.0)",
                      "방문자: 한국관광공사 외지인 방문자 수. 2026-10은 월 단위 예측 모델(ridge, 2025년 검증 WAPE 5.6%) 값, 나머지 달은 2025-09~2026-08 실측",
                      "동네 순위: 읍·면·동 안의 관광지·레포츠 수 (축제 제외)", DONG_CREDIT]}


@app.get("/api/regions/{key}/cost")
def region_cost(key: str):
    """1인 여행 경비 추정 (당일·1박). 시군구 표본이 적으면 시도 값 (level='sido'). 표가 없으면 404."""
    if key not in regions.static:
        raise HTTPException(404, "시군구를 찾을 수 없습니다.")
    c = cost.for_region(key)
    if c is None:
        raise HTTPException(404, "경비 표가 없습니다. src/cost/build_cost_table.py 를 먼저 실행해 주세요.")
    return {"is_example": False, **c}


@app.get("/api/legs")
def course_legs(pts: str = Query(..., max_length=600)):
    """코스 정류장 사이 이동 시간. pts = '위도,경도;위도,경도;…' (2~15곳, 한국 안). 자동차는 모든 구간, 도보는 직선 2km 이하만."""
    try:
        points = [tuple(float(v) for v in p.split(",")) for p in pts.split(";")]
    except ValueError:
        raise HTTPException(400, "좌표 형식이 올바르지 않습니다.")
    if not 2 <= len(points) <= 15 or any(len(p) != 2 or not (33 <= p[0] <= 39 and 124 <= p[1] <= 132) for p in points):
        raise HTTPException(400, "좌표는 한국 안의 2~15곳이어야 합니다.")
    try:
        legs = travel.legs(points)
    except TravelError as e:
        raise HTTPException(503, str(e))
    return {"is_example": False, "legs": legs,
            "note": "카카오 길찾기 조회 시점 기준 (자동차는 실시간 교통 반영, 도보는 직선 2km 이하 구간만)"}


def _locate_missing(course):
    """관광공사 자료로 위치를 못 찾은 정류장(코스의 약 6%)을 카카오 장소 검색으로 보충한다 (approx=True, 메모리 캐시만)."""
    got = [(s["lat"], s["lon"]) for s in course["stops"] if s["lat"] is not None]
    if not got or all(s["lat"] is not None for s in course["stops"]):
        return course
    near = (sum(a for a, _ in got) / len(got), sum(b for _, b in got) / len(got))
    stops = []
    for s in course["stops"]:
        if s["lat"] is None:
            try:
                ll = travel.find_place(s["name"], near)
            except TravelError:
                ll = None
            if ll:
                s = {**s, "lat": ll[0], "lon": ll[1], "approx": True}
        stops.append(s)
    return {**course, "stops": stops}


@app.get("/api/regions/{key}/courses")
def region_courses(key: str, limit: int = Query(20, ge=1, le=100)):
    """그 시군구를 지나는 한국관광공사 공식 여행코스. 들르는 곳이 그 시군구에 많은 코스부터."""
    if key not in regions.static:
        raise HTTPException(404, "시군구를 찾을 수 없습니다.")
    rows = courses.for_region(key)
    return {"is_example": False, "total": len(rows), "items": [_locate_missing(c) for c in rows[:limit]],
            "coverage": {"loaded": courses.n_loaded, "listed": courses.n_total},
            "notes": ["코스: 한국관광공사 TourAPI 여행코스 (들르는 곳·순서·설명·총거리·소요시간은 원문 그대로)",
                      "지도 위치와 사진은 받아 둔 관광지·레포츠·음식점·축제와 같은 곳만 표시 (문화시설·쇼핑 등은 이름·설명만)",
                      "선은 들르는 순서를 직선으로 이은 것이며 실제 길이 아닙니다"]}


@app.get("/api/regions/{key}/rain")
def region_rain(key: str, start: date, end: date):
    """고른 기간(최대 14일)에 비가 올까. 오늘부터 16일 안이면 일기예보, 그 밖이면 2021~2025년 같은 날짜 기록."""
    try:
        return rain.check(tuple(key.split("_", 1)), start, end)
    except RainError as e:
        raise HTTPException(e.status, str(e))


@app.get("/api/regions/{key}/dongs/{code}/activities")
def dong_activities(key: str, code: str):
    """동네(읍·면·동) 안의 관광지·레포츠와 음식점 위치. 동네를 누르면 지도에 묶음별 색 점으로 찍는다."""
    a, f = hoods.act_ids(key, code), hoods.food_ids(key, code)
    if a is None:
        raise HTTPException(404, "동네를 찾을 수 없습니다.")
    rows = [acts.by_id[i] for i in a + f if i in acts.by_id]
    groups = Counter(r["group"] for r in rows)
    return {"is_example": False, "code": code,
            "groups": [{"key": k, "label": label, "count": groups.get(k, 0)} for k, label in ACT_GROUPS if k != "festival"],
            "items": [{k: r[k] for k in ("id", "name", "group", "kind", "lat", "lon", "image_url", "license", "address")} | {"menu": r.get("menu")} for r in rows]}


@app.get("/api/regions/{key}/dongs/{code}/food")
def dong_food(key: str, code: str):
    """동네(읍·면·동) 안의 음식점: 대표사진(공공누리 1·3유형만)과 대표메뉴. 대표메뉴가 있는 곳, 사진이 있는 곳 순."""
    ids = hoods.food_ids(key, code)
    if ids is None:
        raise HTTPException(404, "동네를 찾을 수 없습니다.")
    rows = [acts.by_id[i] for i in ids if i in acts.by_id]
    rows.sort(key=lambda r: (r.get("menu") is None, r["image_url"] is None, r["name"]))
    return {"is_example": False, "code": code, "total": len(rows), "with_menu": sum(r.get("menu") is not None for r in rows),
            "items": [{k: r[k] for k in ("id", "name", "kind", "address", "image_url", "license", "lat", "lon")} | {"menu": r.get("menu")} for r in rows],
            "note": "한국관광공사에 등록된 음식점입니다. 평점이나 맛 순위가 아닙니다. 대표메뉴는 관광공사에 등록된 내용입니다."}


@app.get("/api/activities", response_model=ActivitiesResponse)
def activities(sigungu_key: str, month: Optional[int] = Query(None, ge=1, le=12), attraction_id: Optional[str] = None):
    if sigungu_key not in engine.region_keys:
        raise HTTPException(404, "시군구를 찾을 수 없습니다.")
    origin = None
    it = engine.I["items"].get(attraction_id) if attraction_id else None
    if it:
        try:
            origin = (float(it["mapy"]), float(it["mapx"]))
        except (KeyError, ValueError):
            origin = None
    groups, items = acts.for_region(sigungu_key, month, origin)
    return {"sigungu_key": sigungu_key, "month": month,
            "anchor": {"id": it["contentid"], "name": it["title"], "lat": origin[0], "lon": origin[1]} if origin else None,
            "groups": groups, "items": items,
            "notes": ["묶음은 한국관광공사 TourAPI 분류(관광지·레포츠·축제)로 나눴습니다.",
                      "정렬은 사진이 닮은 관광지에서 가까운 순(직선거리)입니다.",
                      "먹거리는 한국관광공사에 등록된 음식점·카페입니다. 평점이나 맛 순위가 아닙니다.",
                      "축제는 2026년 일정입니다. 이미 끝난 축제는 지난 개최 기록이며 다음 일정은 미정입니다."]}


@app.get("/images/tour/{cid}")
def tour_image(cid: str, full: bool = False):
    """활동 목록 사진 (공공누리 1·3유형만). full=1 이면 원본 크기 (사진 크게 보기용)."""
    url = acts.photo_url(cid, full)
    if not url:
        raise HTTPException(404)
    cached = TOUR_THUMB / f"{cid}{'_full' if full else ''}.jpg"
    if cid in MISSING_PHOTOS:
        raise HTTPException(404)
    if not cached.exists():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": cp.UA})
            cached.write_bytes(urllib.request.urlopen(req, timeout=15).read())
        except urllib.error.HTTPError as e:
            if e.code == 404:  # 목록에는 있지만 원본이 지워진 사진 — 다시 묻지 않는다
                MISSING_PHOTOS.add(cid)
                raise HTTPException(404)
            raise HTTPException(502, "사진을 받지 못했습니다.")
        except Exception:
            raise HTTPException(502, "사진을 받지 못했습니다.")
    return FileResponse(cached, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


def _extra_items(cid):
    """저장해 둔 추가 사진 원문에서 공공누리 1·3유형만. 원문이 없으면 None."""
    for d in EXTRA_DIRS:
        for f in (d / f"{cid}.json", d / f"{cid}_Y.json"):
            if f.exists():
                it = ((json.loads(f.read_text(encoding="utf-8"))["response"]["body"].get("items") or {}).get("item")) or []
                it = [it] if isinstance(it, dict) else it
                return [x for x in it if x.get("cpyrhtDivCd") in ("Type1", "Type3") and (x.get("originimgurl") or x.get("smallimageurl"))]
    return None


def _tour_get(op, params, quota_msg, fail_msg):
    """TourAPI 를 한 번 부른다. .env 의 키를 차례로 쓰고, 하루 한도 초과면 다음 키로. 모두 안 되면 503."""
    import urllib.parse
    sys.path.insert(0, str(ROOT / "src/collect"))
    from tour_attractions import is_quota_error, load_api_keys
    q = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json", **params})
    for key in load_api_keys():
        try:
            data = json.loads(urllib.request.urlopen(f"https://apis.data.go.kr/B551011/KorService2/{op}?serviceKey={key}&{q}", timeout=20).read())
        except urllib.error.HTTPError as e:
            if e.code == 429 or is_quota_error(e.read()[:300].decode("utf-8", "replace")):
                continue
            raise HTTPException(503, fail_msg)
        except Exception:
            raise HTTPException(503, fail_msg)
        if data.get("response", {}).get("header", {}).get("resultCode") == "0000":
            return data
        if not is_quota_error(json.dumps(data, ensure_ascii=False)):
            raise HTTPException(503, fail_msg)
    raise HTTPException(503, quota_msg)


DETAIL_DIR = ROOT / "data/raw/tourapi/detailCommon2"


@app.get("/api/places/{cid}/detail")
def place_detail(cid: str):
    """체험·축제 등 장소 소개글(detailCommon2 overview)·홈페이지·전화. 받아 둔 원문이 없으면 그때 한 번 부르고 저장한다."""
    if cid not in acts.by_id:
        raise HTTPException(404, "장소를 찾을 수 없습니다.")
    f = DETAIL_DIR / f"{cid}.json"
    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))
    else:
        data = _tour_get("detailCommon2", {"contentId": cid, "numOfRows": 1, "pageNo": 1},
                         "오늘 소개 조회 한도를 다 써서 불러올 수 없습니다. 내일 다시 시도해 주세요.", "소개를 불러오지 못했습니다.")
        DETAIL_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    it = ((data["response"]["body"].get("items") or {}).get("item")) or [{}]
    it = it[0] if isinstance(it, list) else it
    import re as _re
    clean = lambda x: " ".join(_re.sub(r"<[^>]+>", " ", x or "").split()) or None
    home = _re.search(r'href="([^"]+)"', it.get("homepage") or "")
    return {"id": cid, "title": it.get("title"), "overview": clean(it.get("overview")), "tel": clean(it.get("tel")),
            "homepage": home.group(1) if home else None, "source": "한국관광공사 TourAPI"}


@app.get("/api/places/{cid}/photos")
def place_photos(cid: str):
    """가게·관광지 추가 사진. 받아 둔 원문이 없으면 그때 TourAPI detailImage2 를 한 번 부르고 저장한다 (관광지 사진 수집과 하루 한도 공유)."""
    if cid not in acts.by_id:
        raise HTTPException(404, "장소를 찾을 수 없습니다.")
    items = _extra_items(cid)
    if items is None:
        data = _tour_get("detailImage2", {"contentId": cid, "imageYN": "Y", "numOfRows": 30, "pageNo": 1},
                         "오늘 사진 조회 한도를 다 써서 추가 사진을 불러올 수 없습니다. 내일 다시 시도해 주세요.", "추가 사진을 불러오지 못했습니다.")
        EXTRA_DIRS[0].mkdir(parents=True, exist_ok=True)
        (EXTRA_DIRS[0] / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        items = _extra_items(cid)
    licence = {"Type1": "공공누리 제1유형 (출처표시)", "Type3": "공공누리 제3유형 (출처표시·변경금지)"}
    return {"id": cid, "photos": [{"url": f"/images/extra/{cid}/{i}", "name": x.get("imgname"), "license": licence[x["cpyrhtDivCd"]]}
                                  for i, x in enumerate(items)], "source": "한국관광공사 TourAPI"}


@app.get("/images/extra/{cid}/{n}")
def extra_image(cid: str, n: int):
    items = _extra_items(cid) or []
    if not (0 <= n < len(items)):
        raise HTTPException(404)
    cached = EXTRA_IMG / f"{cid}_{n}.jpg"
    if not cached.exists():
        url = items[n].get("originimgurl") or items[n].get("smallimageurl")  # 받아 둔 원문에 있는 주소만 쓴다
        try:
            EXTRA_IMG.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": cp.UA}), timeout=15).read())
        except Exception:
            raise HTTPException(404)
    return FileResponse(cached, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/images/overseas/{name}")
def overseas_image(name: str):
    if name not in {p["photo_id"] for p in engine.demo_photos()}:
        raise HTTPException(404)
    return FileResponse(sc.IMG_DIR / name, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


class WebFiles(StaticFiles):
    """화면 파일. index.html 은 매번 새로 확인하게 해서(no-cache) 다시 빌드하면 바로 바뀐 화면이 보이게 한다.
    assets/ 는 파일 이름에 내용 해시가 붙어 있어 그대로 캐시해도 된다."""
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        if not path.startswith("assets/"):
            r.headers["Cache-Control"] = "no-cache"
        return r


if WEB_DIST.exists():
    app.mount("/", WebFiles(directory=WEB_DIST, html=True), name="web")
