"""FastAPI 서버: 추천 API + 사진 제공 + 빌드된 프론트(web/dist).

실행 (저장소 루트에서):
    .venv/bin/uvicorn app.main:app --port 8000
    → http://localhost:8000  (web/dist 가 있으면 화면, 없으면 /docs 에서 API 확인)
"""

import json
import time
from contextlib import asynccontextmanager
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .activities import Activities
from .regions import Regions
from .context import DATA_SOURCES, ORIGINS, ROOT
from .recommender import PRIORITIES, Engine, cp, sc
from .schemas import ActivitiesResponse, AnalyzeResponse, Crop, Feedback, RecommendRequest, RecommendResponse

MAX_UPLOAD = 15 * 1024 * 1024
APP_DATA = ROOT / "data/interim/app"
KR_FULL = APP_DATA / "kr_full"       # TourAPI 원본 사진 캐시 (처음 요청 때 받는다)
TOUR_THUMB = APP_DATA / "tour_thumb"  # 활동 목록 썸네일 캐시
FEEDBACK = APP_DATA / "feedback.jsonl"
WEB_DIST = ROOT / "web/dist"

engine: Optional[Engine] = None
acts: Optional[Activities] = None
regions: Optional[Regions] = None
MISSING_PHOTOS: set[str] = set()


@asynccontextmanager
async def lifespan(_app):
    global engine, acts, regions
    t = time.time()
    engine = Engine()
    acts = Activities()
    regions = Regions(engine, acts)
    KR_FULL.mkdir(parents=True, exist_ok=True)
    TOUR_THUMB.mkdir(parents=True, exist_ok=True)
    print(f"[startup] 모델·인덱스 준비 {time.time() - t:.0f}초", flush=True)
    yield


app = FastAPI(title="닮은꼴 국내 여행지 API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": engine is not None}


@app.get("/api/demo-photos")
def demo_photos():
    return {"is_example": False, "photos": engine.demo_photos()}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(image: Optional[UploadFile] = File(None), demo_photo_id: Optional[str] = Form(None),
                  crop: Optional[str] = Form(None), source_attraction_id: Optional[str] = Form(None)):
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
        raise HTTPException(400, "사진 파일을 열 수 없습니다. JPG·PNG·WEBP 사진인지 확인해 주세요 (아이폰 HEIC는 아직 지원하지 않습니다).")
    exclude = None
    if source_attraction_id:  # 국내 관광지 사진으로 다시 찾기: 그 시군구는 후보에서 뺀다
        exclude = engine.region_of(source_attraction_id)
        if exclude is None:
            raise HTTPException(404, "출발 관광지를 찾을 수 없습니다.")
    qid, tags = engine.analyze(img, exclude)
    return {"query_id": qid, "scene_tags": tags, "image": meta, "excluded_sigungu": _sigungu(exclude)}


def _sigungu(ri):
    if ri is None:
        return None
    key = engine.region_keys[ri]
    return {"key": key, "name": key.split("_", 1)[1]}


@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    if req.query_id not in engine.cache:
        raise HTTPException(404, "분석 결과가 만료됐습니다. 사진을 다시 분석해 주세요.")
    if req.sido and req.sido not in {s["sido"] for s in regions.static.values()}:
        raise HTTPException(400, "시도 이름이 올바르지 않습니다.")
    allowed = regions.allowed(req.travel_month, req.filters, req.sido)
    exclude = engine.cache[req.query_id]["exclude"]
    if allowed is not None and exclude is not None:  # 필터 개수도 출발 시군구를 뺀 수로 보여 준다
        allowed = allowed - {exclude}
    r = engine.recommend(req.query_id, req.travel_month, req.priority, req.origin, req.kept_tags, req.limit, req.offset,
                         allowed)
    q = engine.cache[req.query_id]
    return {
        "query": {"query_id": req.query_id, "scene_tags": [t["tag"] for t in q["tags"]], "kept_tags": req.kept_tags,
                  "month": req.travel_month, "priority": req.priority, "origin": req.origin,
                  "filters": req.filters, "sido": req.sido, "allowed_regions": None if allowed is None else len(allowed),
                  "excluded_sigungu": _sigungu(q["exclude"])},
        "model": {"visual": "CLIP ViT-B/32 (frozen) · 관광지별 최고 1장 → 시군구 vote100 → 상위 30곳",
                  "rerank": "30곳 안에서만 재정렬 · 시각 가중치 0.5 이상 · 단일 종합점수 없음",
                  "priorities": list(PRIORITIES)},
        "total_candidates": r["total"], "candidates": r["candidates"], "data_sources": DATA_SOURCES,
    }


@app.post("/api/feedback")
def feedback(fb: Feedback):
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
def region_table(month: int = Query(ge=1, le=12), origin: Optional[str] = None):
    """시군구별 조건 값·필터 통과 여부·대표 사진. 조건 칩의 곳 수와 '사진 없이 둘러보기'에 쓴다."""
    if origin is not None and origin not in ORIGINS:
        raise HTTPException(400, "출발지가 올바르지 않습니다.")
    rows = []
    for r in regions.month_table(month):
        k = tuple(r["key"].split("_", 1))
        rows.append({**{x: v for x, v in r.items() if x != "ri"}, "photo": engine.region_photo(r["ri"]),
                     "distance_km": engine.ctx.distance(k, origin) if origin else None})
    return {"is_example": False, "month": month,
            "filters": regions.filter_meta(month),
            "sidos": sorted({r["sido"] for r in rows}), "regions": rows}


@app.get("/api/activities", response_model=ActivitiesResponse)
def activities(sigungu_key: str, month: int = Query(ge=1, le=12), attraction_id: Optional[str] = None):
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
                      "축제는 2026년 일정입니다. 이미 끝난 축제는 지난 개최 기록이며 다음 일정은 미정입니다."]}


@app.get("/images/tour/{cid}")
def tour_image(cid: str):
    url = acts.photo_url(cid)  # 활동 목록에 있는 공공누리 1·3유형 사진만
    if not url:
        raise HTTPException(404)
    cached = TOUR_THUMB / f"{cid}.jpg"
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


@app.get("/images/overseas/{name}")
def overseas_image(name: str):
    if name not in {p["photo_id"] for p in engine.demo_photos()}:
        raise HTTPException(404)
    return FileResponse(sc.IMG_DIR / name, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
