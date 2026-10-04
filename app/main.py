"""FastAPI 서버: 추천 API + 사진 제공 + 빌드된 프론트(web/dist).

실행 (저장소 루트에서):
    .venv/bin/uvicorn app.main:app --port 8000
    → http://localhost:8000  (web/dist 가 있으면 화면, 없으면 /docs 에서 API 확인)
"""

import json
import time
from contextlib import asynccontextmanager
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .context import DATA_SOURCES, ROOT
from .recommender import PRIORITIES, Engine, cp, sc
from .schemas import AnalyzeResponse, Crop, Feedback, RecommendRequest, RecommendResponse

MAX_UPLOAD = 15 * 1024 * 1024
APP_DATA = ROOT / "data/interim/app"
KR_FULL = APP_DATA / "kr_full"       # TourAPI 원본 사진 캐시 (처음 요청 때 받는다)
FEEDBACK = APP_DATA / "feedback.jsonl"
WEB_DIST = ROOT / "web/dist"

engine: Optional[Engine] = None


@asynccontextmanager
async def lifespan(_app):
    global engine
    t = time.time()
    engine = Engine()
    KR_FULL.mkdir(parents=True, exist_ok=True)
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
                  crop: Optional[str] = Form(None)):
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
    qid, tags = engine.analyze(img)
    return {"query_id": qid, "scene_tags": tags, "image": meta}


@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    if req.query_id not in engine.cache:
        raise HTTPException(404, "분석 결과가 만료됐습니다. 사진을 다시 분석해 주세요.")
    r = engine.recommend(req.query_id, req.travel_month, req.priority, req.origin, req.kept_tags, req.limit, req.offset)
    q = engine.cache[req.query_id]
    return {
        "query": {"query_id": req.query_id, "scene_tags": [t["tag"] for t in q["tags"]], "kept_tags": req.kept_tags,
                  "month": req.travel_month, "priority": req.priority, "origin": req.origin},
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


@app.get("/images/overseas/{name}")
def overseas_image(name: str):
    if name not in {p["photo_id"] for p in engine.demo_photos()}:
        raise HTTPException(404)
    return FileResponse(sc.IMG_DIR / name, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
