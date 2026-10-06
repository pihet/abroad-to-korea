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
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from collections import Counter

from .activities import GROUPS as ACT_GROUPS, Activities
from .neighborhoods import CREDIT as DONG_CREDIT, Neighborhoods
from .regions import Regions
from .context import DATA_SOURCES, ORIGINS, ROOT
from .recommender import PRIORITIES, Engine, cp, sc
from .schemas import ActivitiesResponse, AnalyzeResponse, Crop, Feedback, RecommendRequest, RecommendResponse

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
    global engine, acts, regions, hoods
    t = time.time()
    engine = Engine()
    acts = Activities()
    regions = Regions(engine, acts)
    hoods = Neighborhoods(acts, {s['sido']: s['key'].split('_')[0] for s in regions.static.values()})
    KR_FULL.mkdir(parents=True, exist_ok=True)
    TOUR_THUMB.mkdir(parents=True, exist_ok=True)
    print(f"[startup] 모델·인덱스 준비 {time.time() - t:.0f}초", flush=True)
    yield


app = FastAPI(title="닮은꼴 국내 여행지 API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": engine is not None}


SHOWCASE_PHOTO = "kyoto__fushimi__1.jpg"
_showcase = None


@app.get("/api/showcase")
def showcase():
    """첫 화면 예시: 해외 사진 한 장을 실제로 추천에 넣은 결과 1위 (지어낸 짝이 아님). 처음 요청 때 한 번 계산해 둔다."""
    global _showcase
    if _showcase is None:
        photo = next(p for p in engine.demo_photos() if p["photo_id"] == SHOWCASE_PHOTO)
        img, _ = engine.open_image((sc.IMG_DIR / SHOWCASE_PHOTO).read_bytes())
        qid, _ = engine.analyze(img)
        top = engine.recommend(qid, None, "visual", None, None, 1, 0)["candidates"][0]
        _showcase = {"is_example": True, "note": "실제 추천 결과 1위 (예시 사진으로 계산)", "overseas": photo,
                     "domestic": {"sigungu": top["sigungu"], "attraction": top["attraction"],
                                  "similarity": top["visual"]["similarity"], "visual_rank": top["visual_rank"]}}
    return _showcase


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
        raise HTTPException(400, BAD_IMAGE)
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


@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
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
def region_table(month: Optional[int] = Query(None, ge=1, le=12), origin: Optional[str] = None):
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
            "notes": ["날씨: Open-Meteo 2021~2025년 같은 달 평균",
                      "방문자: 한국관광공사 외지인 방문자 수. 2026-10은 월 단위 예측 모델(ridge, 2025년 검증 WAPE 5.6%) 값, 나머지 달은 2025-09~2026-08 실측",
                      "동네 순위: 읍·면·동 안의 관광지·레포츠 수 (축제 제외)", DONG_CREDIT]}


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
            "note": "한국관광공사에 등록된 음식점입니다. 평점이나 맛 순위가 아닙니다. 대표메뉴는 매일 수집 중입니다."}


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


def _extra_items(cid):
    """저장해 둔 추가 사진 원문에서 공공누리 1·3유형만. 원문이 없으면 None."""
    for d in EXTRA_DIRS:
        for f in (d / f"{cid}.json", d / f"{cid}_Y.json"):
            if f.exists():
                it = ((json.loads(f.read_text(encoding="utf-8"))["response"]["body"].get("items") or {}).get("item")) or []
                it = [it] if isinstance(it, dict) else it
                return [x for x in it if x.get("cpyrhtDivCd") in ("Type1", "Type3") and (x.get("originimgurl") or x.get("smallimageurl"))]
    return None


@app.get("/api/places/{cid}/photos")
def place_photos(cid: str):
    """가게·관광지 추가 사진. 받아 둔 원문이 없으면 그때 TourAPI detailImage2 를 한 번 부르고 저장한다 (관광지 사진 수집과 하루 한도 공유)."""
    if cid not in acts.by_id:
        raise HTTPException(404, "장소를 찾을 수 없습니다.")
    items = _extra_items(cid)
    if items is None:
        import urllib.parse
        sys.path.insert(0, str(ROOT / "src/collect"))
        from tour_attractions import load_api_key
        q = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json", "contentId": cid,
                                    "imageYN": "Y", "numOfRows": 30, "pageNo": 1})
        try:
            body = urllib.request.urlopen(f"https://apis.data.go.kr/B551011/KorService2/detailImage2?serviceKey={load_api_key()}&{q}", timeout=20).read()
            data = json.loads(body)
        except urllib.error.HTTPError as e:
            raise HTTPException(503, "오늘 사진 조회 한도를 다 써서 추가 사진을 불러올 수 없습니다. 내일 다시 시도해 주세요." if e.code == 429 else "추가 사진을 불러오지 못했습니다.")
        except Exception:
            raise HTTPException(503, "추가 사진을 불러오지 못했습니다.")
        if data.get("response", {}).get("header", {}).get("resultCode") != "0000":
            raise HTTPException(503, "오늘 사진 조회 한도를 다 써서 추가 사진을 불러올 수 없습니다. 내일 다시 시도해 주세요.")
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


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
