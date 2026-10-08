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


def test_feedback(client, qid, monkeypatch):
    # DB 주소가 설정돼 있으면 피드백은 DB로 간다. 이 테스트는 파일 저장만 확인하고 실제 DB에는 쓰지 않는다 (DB 저장은 test_infrastructure)
    monkeypatch.setattr(main, "session_factory", lambda: None)
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
    assert {f["key"] for f in d["filters"]} == {"sea", "mountain", "calm", "city", "rural", "mild"}
    assert all(f["basis"] for f in d["filters"])
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


def test_search_from_domestic_photo_excludes_source(client):
    """#14: 국내 관광지 사진으로 다시 찾으면 그 시군구가 1위로 나오던 문제."""
    d = client.get("/api/regions", params={"month": 10}).json()
    src = next(r for r in d["regions"] if r["key"] == "47_울릉군")["photo"]
    img = client.get(src["image_url"]).content

    plain = client.post("/api/analyze", files={"image": ("a.jpg", img, "image/jpeg")}).json()
    assert plain["excluded_sigungu"] is None
    assert rec(client, plain["query_id"])["candidates"][0]["sigungu"]["key"] == "47_울릉군"  # 문제 재현

    a = client.post("/api/analyze", files={"image": ("a.jpg", img, "image/jpeg")},
                    data={"source_attraction_id": src["attraction_id"]}).json()
    assert a["excluded_sigungu"]["key"] == "47_울릉군"
    n_sea = sum(r["flags"]["sea"] for r in d["regions"])
    assert rec(client, a["query_id"], filters=["sea"])["query"]["allowed_regions"] == n_sea - 1  # 울릉군은 바다 가까운 곳
    for kw in ({}, {"filters": ["sea"]}):
        r = rec(client, a["query_id"], limit=30, **kw)
        assert r["query"]["excluded_sigungu"]["key"] == "47_울릉군"
        assert r["candidates"] and all(c["sigungu"]["key"] != "47_울릉군" for c in r["candidates"])
    bad = client.post("/api/analyze", files={"image": ("a.jpg", img, "image/jpeg")}, data={"source_attraction_id": "0"})
    assert bad.status_code == 404


def _heic_bytes():
    import pillow_heif  # 전역 등록(register_heif_opener) 없이 만든다. 등록하면 서버 쪽 지원 여부를 가린다
    b = io.BytesIO()
    pillow_heif.from_pillow(Image.open(ROOT / "data/interim/clip/scenes" / DEMO)).save(b)
    return b.getvalue()


def test_heic_upload(client):
    """#4: 아이폰 HEIC 사진을 분석하고, 화면 미리보기용 JPEG 로 바꿀 수 있어야 한다."""
    heic = _heic_bytes()
    a = client.post("/api/analyze", files={"image": ("IMG_0001.HEIC", heic, "image/heic")})
    assert a.status_code == 200, a.text
    assert a.json()["image"]["width"] == 960
    c = client.post("/api/convert", files={"image": ("IMG_0001.HEIC", heic, "image/heic")})
    assert c.status_code == 200 and c.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(c.content)).size == (960, 640)
    assert client.post("/api/convert", files={"image": ("x.heic", b"nope", "image/heic")}).status_code == 400



def test_city_rural(client):
    """#13: 주민등록 인구 중 '동' 지역 비율 50% 이상이면 도시, 아니면 시골·소도시."""
    d = client.get("/api/regions", params={"month": 10}).json()
    by = {r["key"]: r for r in d["regions"]}
    assert all(r["urban_share"] is not None for r in d["regions"])  # 230곳 모두 인구 자료가 있다
    assert all(r["flags"]["city"] != r["flags"]["rural"] for r in d["regions"])  # 둘 중 하나만
    assert by["11_종로구"]["flags"]["city"] and by["47_울릉군"]["flags"]["rural"]
    assert by["36110_세종특별자치시"]["urban_share"] > 0  # 시군구 이름이 없는 세종도 연결된다
    for r in d["regions"]:
        assert r["flags"]["city"] == (r["urban_share"] >= 0.5)


def test_region_profile(client):
    d = client.get("/api/regions/51_양양군/profile", params={"month": 10}).json()
    assert d["is_example"] is False and d["region"]["name"] == "양양군"
    assert [m["month"] for m in d["months"]] == list(range(1, 13))
    assert all(m["temp_c"] is not None and m["congestion_index"] is not None for m in d["months"])
    assert d["months"][9]["basis"] == "forecast" and d["months"][0]["basis"] == "actual"
    ranked = sorted((h for h in d["neighborhoods"] if h["rank"]), key=lambda h: h["rank"])
    assert [h["rank"] for h in ranked] == list(range(1, len(ranked) + 1)) and 0 < len(ranked) <= 5
    totals = [h["total"] for h in ranked]
    assert totals == sorted(totals, reverse=True) and all(h["geometry"]["type"].endswith("Polygon") for h in d["neighborhoods"])
    assert any("CC BY 4.0" in n for n in d["notes"])
    assert client.get("/api/regions/99_없음/profile", params={"month": 10}).status_code == 404


def test_rankings(client):
    for m in (1, 10):
        lists = {l["id"]: l for l in client.get("/api/rankings", params={"month": m}).json()["lists"]}
        assert all(l["basis"] for l in lists.values())
        calm = lists["calmer-than-usual"]
        assert all(i["value"] < 100 for i in calm["items"])  # '평소보다 한산' = 혼잡도 100 미만만
        if not calm["items"]:
            assert calm["empty"]
        sea = [i["value"] for i in lists["quiet-sea"]["items"]]
        assert sea == sorted(sea)


def test_without_travel_month(client, qid):
    """화면에서 여행 월 선택을 뺐다: 월 없이 요청하면 월평균·연간 기준."""
    r = client.post("/api/recommend", json={"query_id": qid, "priority": "crowd", "limit": 30}).json()
    assert r["query"]["month"] is None and r["candidates"]
    for c in r["candidates"]:
        assert c["climate"] is None and c["congestion"]["basis"] == "annual" and c["congestion"]["index"] is None
    assert client.post("/api/recommend", json={"query_id": qid, "priority": "season"}).status_code == 400
    assert client.post("/api/recommend", json={"query_id": qid, "filters": ["mild"]}).status_code == 400
    lists = client.get("/api/rankings").json()["lists"]
    assert [l["id"] for l in lists] == ["mountain", "rural-activities", "festivals"]
    p = client.get("/api/regions/51_양양군/profile").json()
    assert p["month"] is None and len(p["months"]) == 12
    a = client.get("/api/activities", params={"sigungu_key": "51_양양군"}).json()
    fest = [i for i in a["items"] if i["group"] == "festival"]
    assert len(fest) >= 2 and {f["schedule"] for f in fest} <= {"예정", "지난 개최 기록"}


def test_food(client):
    a = client.get("/api/activities", params={"sigungu_key": "50_제주시"}).json()
    groups = {g["key"]: g["count"] for g in a["groups"]}
    assert groups["food"] > 0
    assert any("평점" in n for n in a["notes"])  # 맛 순위가 아니라고 밝힌다
    p = client.get("/api/regions/50_제주시/profile").json()
    f = p["food"]
    assert f["n_places"] == groups["food"] and 0 <= f["n_menus"] <= f["n_places"]
    assert all(w["places"] >= 2 for w in f["top"]) and (f["top"] == [] or f["n_menus"] >= 5)
    lists = {l["id"]: l for l in client.get("/api/rankings").json()["lists"]}
    before = {i["key"]: i["value"] for i in lists["rural-activities"]["items"]}
    assert before.get("41_가평군") == 207  # 음식점은 '할 거리' 수에 넣지 않는다


def test_menu_words():
    from app.activities import _menu_words
    assert _menu_words("소고기국밥(1인분) 9,000원, 수육") == ["소고기국밥", "수육"]
    assert _menu_words("등갈비찜 2인분 외") == ["등갈비찜"]


def test_dong_food(client):
    p = client.get("/api/regions/50_제주시/profile").json()
    dong = max(p["neighborhoods"], key=lambda n: n["n_food"])
    d = client.get(f"/api/regions/50_제주시/dongs/{dong['code']}/food").json()
    assert d["total"] == dong["n_food"] > 0 and "평점" in d["note"]
    menus = [i["menu"] is not None for i in d["items"]]
    assert menus == sorted(menus, reverse=True)  # 대표메뉴 있는 곳이 먼저
    assert all((i["image_url"] is None) == (i["license"] is None) for i in d["items"])
    assert client.get("/api/regions/50_제주시/dongs/0000000000/food").status_code == 404


def test_dong_activities(client):
    p = client.get("/api/regions/51_양양군/profile").json()
    dong = next(n for n in p["neighborhoods"] if n["rank"] == 1)
    d = client.get(f"/api/regions/51_양양군/dongs/{dong['code']}/activities").json()
    counts = {g["key"]: g["count"] for g in d["groups"]}
    assert sum(v for k, v in counts.items() if k != "food") == dong["total"]  # 동네 순위 수와 같다
    assert counts["food"] == dong["n_food"] and len(d["items"]) == dong["total"] + dong["n_food"]
    assert "festival" not in counts
    assert all("address" in i and (i["image_url"] is None) == (i["license"] is None) for i in d["items"])  # 점 말풍선용
    assert client.get("/api/regions/51_양양군/dongs/0000000000/activities").status_code == 404


def test_place_photos_cached():
    """표본 조사로 받아 둔 음식점은 외부 호출 없이 추가 사진이 나온다 (공공누리 1·3유형만)."""
    with TestClient(main.app) as c:
        r = c.get("/api/places/2844953/photos")
        if r.status_code == 404:  # 표본 원문이 없는 환경
            pytest.skip("표본 원문 없음")
        d = r.json()
        assert len(d["photos"]) == 3 and all("공공누리" in p["license"] for p in d["photos"])
        assert c.get("/images/extra/2844953/99").status_code == 404
        assert c.get("/api/places/0/photos").status_code == 404


def test_region_rain_history(client):
    """16일보다 먼 날짜는 2021~2025년 같은 날짜 기록 (네트워크 없이 확인되는 경로)."""
    r = client.get("/api/regions/51_양양군/rain", params={"start": "2027-12-24", "end": "2027-12-27"})
    assert r.status_code == 200
    d = r.json()
    assert d["basis"] == "history" and d["n_years"] == 5 and len(d["days"]) == 4
    assert all(0 <= x["rainy_years"] <= x["years"] == 5 for x in d["days"])
    assert 0 <= d["years_with_rain"] <= 5
    bad = client.get("/api/regions/51_양양군/rain", params={"start": "2027-12-27", "end": "2027-12-24"})
    assert bad.status_code == 400 and "빠릅니다" in bad.json()["detail"]
    assert client.get("/api/regions/51_양양군/rain", params={"start": "2027-12-01", "end": "2027-12-20"}).status_code == 400
    assert client.get("/api/regions/99_없음/rain", params={"start": "2027-12-24", "end": "2027-12-25"}).status_code == 404


def test_festivals_this_week(client):
    """고른 7일에 걸친 축제만, 두 달 넘는 상설 행사는 빼고, 이 기간에 시작하는 축제를 먼저."""
    from datetime import date
    d = client.get("/api/festivals", params={"start": "2026-10-07", "days": 7, "limit": 50}).json()
    assert d["start"] == "2026-10-07" and d["end"] == "2026-10-13" and d["items"]
    for f in d["items"]:
        assert f["end"] >= "2026-10-07" and f["start"] <= "2026-10-13"
        assert (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days + 1 <= 62
        assert f["region"]["key"] == f["region_key"]
    flags = [f["starts_in_range"] for f in d["items"]]
    assert flags == sorted(flags, reverse=True)  # 이번 주 시작이 먼저
    assert client.get("/api/festivals", params={"days": 40}).status_code == 422


def test_region_courses(client):
    """공식 여행코스: 들르는 순서가 1부터 빈틈없이, 같은 곳 중복 없이, 그 시군구를 지나는 코스만."""
    d = client.get("/api/regions/51_고성군/courses").json()
    if d["coverage"]["loaded"] == 0:
        pytest.skip("여행코스 상세(detailInfo2_ct25)를 아직 받지 않음")
    assert d["notes"] and d["total"] == len(d["items"]) or d["total"] > len(d["items"])
    for c in d["items"]:
        assert [s["order"] for s in c["stops"]] == list(range(1, len(c["stops"]) + 1))
        ids = [s["id"] or s["name"] for s in c["stops"]]
        assert len(ids) == len(set(ids))
        assert c["regions"].get("51_고성군", 0) >= 1
        assert all(s["image_url"] is None or s["license"] for s in c["stops"])  # 사진은 라이선스 확인된 것만
    counts = [c["regions"]["51_고성군"] for c in d["items"]]
    assert counts == sorted(counts, reverse=True)
    assert client.get("/api/regions/99_없음/courses").status_code == 404


def test_search_names(client):
    """읍·면·동과 장소 이름 검색: 맞는 것만, 이름 앞에서 맞는 것이 먼저, 결과마다 시군구가 붙는다."""
    d = client.get("/api/search", params={"q": "석촌"}).json()
    assert any(x["name"] == "석촌동" and x["region_name"] == "송파구" for x in d["dongs"])
    p = client.get("/api/search", params={"q": "화암사"}).json()["places"]
    assert p and all("화암사" in x["name"].replace(" ", "") for x in p) and all(x["region_key"] and x["sido"] for x in p)
    for rows in client.get("/api/search", params={"q": "서면"}).json().values():
        if isinstance(rows, list) and rows:
            starts = [x["name"].replace(" ", "").startswith("서면") for x in rows]
            assert starts == sorted(starts, reverse=True)
    assert client.get("/api/search", params={"q": ""}).status_code == 422
