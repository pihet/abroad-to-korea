"""여행코스 정류장 중 위치를 모르는 곳(문화시설·쇼핑 등)의 detailCommon2 를 받아 좌표를 채운다.

코스 정류장 위치는 받아 둔 관광지·레포츠·음식점·축제 목록에서 찾는데, 그 밖의 분류(문화시설 14, 쇼핑 38 등)는
목록이 없어 지도에 못 찍었다 (2026-10-08 기준 정류장 4,901곳 중 874곳, 고유 665곳).
detailCommon2 응답에는 좌표(mapx·mapy)와 법정동 코드가 있어 이것으로 채운다. app/courses.py 가 읽는다.

실행: python src/collect/tour_course_stops.py
결과: data/raw/tourapi/detailCommon2/<contentid>.json (지역 상세의 소개글 캐시와 같은 폴더·형식)
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from tour_attractions import PROJECT_ROOT, KeyRing, is_quota_error, with_retry

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"
RAW = PROJECT_ROOT / "data/raw/tourapi"
OUT_DIR = RAW / "detailCommon2"


def _items(path):
    body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
    it = (body.get("items") or {}).get("item") or []
    return it if isinstance(it, list) else [it]


def known_ids() -> set:
    """위치를 이미 아는 contentid (관광지·레포츠·음식점 목록, 축제)."""
    ids = set()
    for d in RAW.glob("areaBasedList2_ct*"):
        if d.is_dir() and not d.name.startswith("areaBasedList2_ct25"):
            for p in d.glob("page_*.json"):
                ids |= {it["contentid"] for it in _items(p) if it.get("mapx")}
    for f in RAW.glob("searchFestival2_*.json"):
        ids |= {it["contentid"] for it in _items(f) if it.get("mapx")}
    return ids


def todo() -> list[str]:
    known = known_ids()
    stops = {s["subcontentid"] for f in (RAW / "detailInfo2_ct25").glob("*.json") for s in _items(f) if s.get("subcontentid")}
    return sorted(c for c in stops - known if not (OUT_DIR / f"{c}.json").exists())


def fetch(key: str, cid: str) -> dict:
    params = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json",
                                     "contentId": cid, "numOfRows": 1, "pageNo": 1})
    with urllib.request.urlopen(f"{BASE_URL}?serviceKey={key}&{params}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    ring = KeyRing(990)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ids = todo()
    print(f"위치를 모르는 코스 정류장 {len(ids)}곳, 키 {len(ring.keys)}개")
    saved = 0
    for cid in ids:
        data = None
        while (key := ring.key()) is not None:
            try:
                data = with_retry(lambda: fetch(key, cid))
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace")
                if e.code == 429 or is_quota_error(body):
                    ring.next_key("하루 한도 초과"); continue
                print(f"HTTP {e.code} ({cid}): {body[:200]!r} → 멈춤"); break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                print(f"오류 ({cid}): {e} → 멈춤 (다시 실행하면 이어서 받음)"); break
            ring.spent()
            if data.get("response", {}).get("header", {}).get("resultCode") != "0000":
                if is_quota_error(json.dumps(data, ensure_ascii=False)):
                    data = None; ring.next_key("하루 한도 초과"); continue
                print(f"API 오류 ({cid}): {json.dumps(data, ensure_ascii=False)[:200]} → 멈춤"); data = None
            break
        if data is None:
            break
        (OUT_DIR / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        saved += 1
        time.sleep(0.1)
    print(f"사용한 키: {ring.summary()}")
    print(f"저장 {saved}곳, 남은 {len(ids) - saved}곳")


if __name__ == "__main__":
    main()
