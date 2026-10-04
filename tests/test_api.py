"""추천 API 테스트. 실행: .venv/bin/python -m pytest tests -q  (모델 로딩 때문에 30초 안팎 걸린다)"""

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main

ROOT = Path(__file__).resolve().parents[1]
DEMO = "kyoto__fushimi__1.jpg"
KOGL_OK = {"공공누리 제1유형 (출처표시)", "공공누리 제3유형 (출처표시·변경금지)"}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    main.FEEDBACK = tmp_path_factory.mktemp("fb") / "feedback.jsonl"  # 실제 피드백 파일을 건드리지 않는다
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def qid(client):
    r = client.post("/api/analyze", data={"demo_photo_id": DEMO})
    assert r.status_code == 200, r.text
    return r.json()["query_id"]


def rec(client, qid, **kw):
    body = {"query_id": qid, "travel_month": 10, "priority": "visual", **kw}
    r = client.post("/api/recommend", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_demo_photos(client):
    assert client.get("/api/health").json()["ok"]
    photos = client.get("/api/demo-photos").json()["photos"]
    assert len(photos) >= 100
    assert all(p["artist"] and p["license"] and p["source_page"] for p in photos)
    assert any(p["photo_id"] == DEMO for p in photos)


def test_analyze_returns_tags(client):
    r = client.post("/api/analyze", data={"demo_photo_id": DEMO}).json()
    assert r["is_example"] is False and len(r["query_id"]) == 12
    assert len(r["scene_tags"]) == 6 and all(0 <= t["score"] <= 1 for t in r["scene_tags"])
    assert r["image"]["cropped"] is False


def test_recommend_contract(client, qid):
    r = rec(client, qid)
    assert r["is_example"] is False and r["total_candidates"] == 30 and len(r["candidates"]) == 5
    assert r["data_sources"]
    for k, c in enumerate(r["candidates"], 1):
        assert c["rank"] == k == c["visual_rank"]  # visual 은 Stage A 순서 그대로
        assert c["attraction"]["license"] in KOGL_OK
        assert c["attraction"]["source"] == "한국관광공사 TourAPI"
        assert c["attraction"]["image_url"].startswith("/images/kr/")
        cg = c["congestion"]
        if cg is not None:
            assert len(cg["monthly"]) == 12 and cg["basis"] == "forecast" and cg["basis_month"] == "2026-10"


def test_visual_matches_existing_vote100(client, qid):
    """대표사진 풀에서 Stage A(관광지 최고 1장 → vote100)는 기존 평가 코드의 vote100 과 같은 순위여야 한다."""
    import scene_catalog as sc
    e = main.engine
    v = e.cache[qid]["vec"]
    old = np.argsort(-sc.vote_scores(e.I, v)[0], kind="stable")[:30].tolist()
    new = [c["ri"] for c in e.cache[qid]["stage_a"]]
    assert new == old


def test_priorities_stay_within_stage_a(client, qid):
    for pr in ("crowd", "near", "season"):
        r = rec(client, qid, priority=pr, origin="부산", limit=30)
        assert len(r["candidates"]) == 30
        assert all(1 <= c["visual_rank"] <= 30 for c in r["candidates"])
        assert all(c["rerank"]["condition_component"] is not None or c["rerank"]["condition_value"] is None for c in r["candidates"])
    near = rec(client, qid, priority="near", origin="부산", limit=30)["candidates"]
    assert all(c["distance_km"] is not None for c in near)


def test_month_changes_basis(client, qid):
    mar = rec(client, qid, travel_month=3)["candidates"]
    cg = [c["congestion"] for c in mar if c["congestion"]]
    assert cg and all(x["basis"] == "actual" and x["basis_month"] == "2026-03" for x in cg)


def test_crop_and_upload(client):
    img = Image.open(ROOT / "data/interim/clip/scenes" / DEMO)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    full = client.post("/api/analyze", files={"image": ("a.jpg", buf.getvalue(), "image/jpeg")}).json()
    crop = json.dumps({"x": 0, "y": 0, "w": img.width // 2, "h": img.height // 2})
    part = client.post("/api/analyze", files={"image": ("a.jpg", buf.getvalue(), "image/jpeg")}, data={"crop": crop}).json()
    assert part["image"]["cropped"] is True and full["image"]["cropped"] is False
    e = main.engine
    assert float(e.cache[full["query_id"]]["vec"] @ e.cache[part["query_id"]]["vec"]) < 0.999


def test_rejects_bad_input(client):
    assert client.post("/api/analyze", files={"image": ("a.jpg", b"not an image", "image/jpeg")}).status_code == 400
    assert client.post("/api/analyze", data={"demo_photo_id": "../../.env"}).status_code == 404
    assert client.post("/api/recommend", json={"query_id": "nope", "travel_month": 10}).status_code == 404
    assert client.post("/api/recommend", json={"query_id": "x", "travel_month": 13}).status_code == 422
    assert client.get("/images/kr/../../.env").status_code == 404


def test_feedback(client, qid):
    r = client.post("/api/feedback", json={"query_id": qid, "sigungu_key": "11_종로구", "attraction_id": "1", "value": 1})
    assert r.json()["ok"] and main.FEEDBACK.read_text().count("\n") == 1


def test_existing_results_unchanged():
    """기존 평가 결과·임베딩·코드가 작업 전 해시와 같아야 한다."""
    base = ROOT / "data/interim/app/baseline_hashes.txt"
    for line in base.read_text().splitlines():
        h, f = line.split(maxsplit=1)
        assert hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == h, f


def test_activities(client, qid):
    c = rec(client, qid)["candidates"][0]
    r = client.get("/api/activities", params={"sigungu_key": c["sigungu"]["key"], "month": 10,
                                               "attraction_id": c["attraction"]["id"]})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["is_example"] is False and a["anchor"]["id"] == c["attraction"]["id"]
    assert sum(g["count"] for g in a["groups"]) == len(a["items"])
    d = [i["distance_km"] for i in a["items"]]
    assert d == sorted(d)  # 닮은 관광지에서 가까운 순
    for i in a["items"]:
        assert (i["image_url"] is None) == (i["license"] is None)
        assert i["license"] in (None, *KOGL_OK)
        if i["group"] == "festival":
            assert i["period"] and i["schedule"] in ("예정", "지난 개최 기록")


def test_activities_festival_month():
    from app.activities import Activities
    A = Activities()
    for m in (3, 10):
        _, items = A.for_region("51_양양군", m)
        for f in (i for i in items if i["group"] == "festival"):
            s, e = f["period"].replace(".", "").split(" ~ ")
            assert s[:6] <= f"2026{m:02d}" <= e[:6]


def test_activities_rejects(client):
    assert client.get("/api/activities", params={"sigungu_key": "99_없는곳", "month": 10}).status_code == 404
    assert client.get("/api/activities", params={"sigungu_key": "51_양양군", "month": 13}).status_code == 422
    assert client.get("/images/tour/0000").status_code == 404


def test_regions_table(client):
    d = client.get("/api/regions", params={"month": 10, "origin": "부산"}).json()
    assert d["is_example"] is False and len(d["regions"]) == 230
    assert {f["key"] for f in d["filters"]} == {"sea", "mountain", "calm", "mild"} and all(f["basis"] for f in d["filters"])
    by = {r["key"]: r for r in d["regions"]}
    assert by["26_수영구"]["flags"]["sea"] and not by["11_서초구"]["flags"]["sea"]  # 해안선 기준
    assert all(r["distance_km"] is not None for r in d["regions"])
    assert all(r["photo"] for r in d["regions"])
    assert client.get("/api/regions", params={"month": 10, "origin": "평양"}).status_code == 400


def test_filters_restrict_candidates(client, qid):
    d = client.get("/api/regions", params={"month": 10}).json()
    ok = {r["key"] for r in d["regions"] if r["flags"]["sea"] and r["flags"]["calm"]}
    r = rec(client, qid, filters=["sea", "calm"], limit=30)
    assert r["query"]["allowed_regions"] == len(ok) and r["total_candidates"] == min(30, len(ok))
    assert {c["sigungu"]["key"] for c in r["candidates"]} <= ok
    assert [c["visual_rank"] for c in r["candidates"]] == list(range(1, len(r["candidates"]) + 1))
    gw = rec(client, qid, sido="강원특별자치도", limit=30)["candidates"]
    assert gw and all(c["sigungu"]["sido"] == "강원특별자치도" for c in gw)
    assert client.post("/api/recommend", json={"query_id": qid, "travel_month": 10, "filters": ["beach"]}).status_code == 422
    assert client.post("/api/recommend", json={"query_id": qid, "travel_month": 10, "sido": "없는도"}).status_code == 400


def test_empty_filter_result(client, qid):
    r = rec(client, qid, filters=["sea"], sido="충청북도")  # 내륙 도에는 바다 가까운 시군구가 없다
    assert r["query"]["allowed_regions"] == 0 and r["total_candidates"] == 0 and r["candidates"] == []


def test_weather_chip_follows_season(client):
    """추운 달은 따뜻한 곳, 더운 달은 시원한 곳, 그 사이는 쾌적한 곳. 어느 달이든 0곳이 아니다."""
    expect = {1: "따뜻한 곳", 4: "따뜻한 곳", 5: "날씨가 쾌적한 곳", 7: "시원한 곳", 8: "시원한 곳", 10: "따뜻한 곳"}
    for m in range(1, 13):
        d = client.get("/api/regions", params={"month": m}).json()
        chip = next(f for f in d["filters"] if f["key"] == "mild")
        if m in expect:
            assert chip["label"] == expect[m], (m, chip)
        temps = {r["key"]: r["temp_c"] for r in d["regions"]}
        on = [r["key"] for r in d["regions"] if r["flags"]["mild"]]
        assert on, m
        if chip["label"] == "따뜻한 곳":
            assert min(temps[k] for k in on) >= max(t for k, t in temps.items() if k not in on)
        if chip["label"] == "시원한 곳":
            assert max(temps[k] for k in on) <= min(t for k, t in temps.items() if k not in on)
