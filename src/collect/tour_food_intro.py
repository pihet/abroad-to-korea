"""TourAPI 음식점(contentTypeId=39) 소개 정보(detailIntro2)를 내려받아 data/raw/ 에 원본 그대로 저장한다.

대표메뉴(firstmenu)·취급메뉴(treatmenu)·영업시간·쉬는 날이 들어 있다. 시군구별 "지역 먹거리"를 셀 때 쓴다.
개발계정은 오퍼레이션당 하루 1,000건이라 13,402곳을 매일 이어서 받는다 (사진 detailImage2 와 한도가 따로다).
    - 순서: 시군구를 돌아가며 한 곳씩 (tour_images.py 와 같은 방식). 어느 날 멈춰도 모든 시군구가 고르게 받는다
    - 이미 받은 음식점은 건너뛴다. 한도 초과 응답이 오면 멈춘다

실행:
    python src/collect/tour_food_intro.py            # 오늘 최대 990건
    python src/collect/tour_food_intro.py 300        # 최대 300건

결과: data/raw/tourapi/detailIntro2_ct39/<contentid>.json (응답 원문)
"""

import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

from tour_attractions import PROJECT_ROOT, KeyRing, is_quota_error

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/detailIntro2"
OUT_DIR = PROJECT_ROOT / "data/raw/tourapi/detailIntro2_ct39"
DEFAULT_MAX_CALLS = 990
SEED = 42


def raw_list():
    dirs = sorted((PROJECT_ROOT / "data/raw/tourapi").glob("areaBasedList2_ct39_*"))
    if not dirs:
        sys.exit("음식점 목록이 없습니다. 먼저 python src/collect/tour_attractions.py 39 를 실행하세요.")
    return dirs[-1]


def queue() -> list[str]:
    """시군구 라운드로빈 순서의 contentid 목록."""
    items = []
    for p in sorted(raw_list().glob("page_*.json")):
        items += json.loads(p.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    by_region = defaultdict(list)
    for it in items:
        by_region[(it.get("lDongRegnCd"), it.get("lDongSignguCd"))].append(it["contentid"])
    rng = random.Random(SEED)
    regions = sorted(by_region, key=str)
    for r in regions:
        rng.shuffle(by_region[r])
    order = []
    while any(by_region[r] for r in regions):
        for r in regions:
            if by_region[r]:
                order.append(by_region[r].pop())
    return order


def fetch(key: str, cid: str) -> dict:
    params = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json",
                                     "contentId": cid, "contentTypeId": 39, "numOfRows": 10, "pageNo": 1})
    with urllib.request.urlopen(f"{BASE_URL}?serviceKey={key}&{params}", timeout=60) as r:
        body = r.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON이 아닌 응답 ({cid}): {body[:300]}") from None


def main() -> None:
    max_calls = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAX_CALLS
    ring = KeyRing(max_calls)  # 키마다 max_calls 건, 한도가 차면 다음 키
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    todo = [c for c in queue() if not (OUT_DIR / f"{c}.json").exists()]
    print(f"남은 음식점 {len(todo)}곳, 키 {len(ring.keys)}개 × 최대 {max_calls}건", flush=True)
    calls = saved = 0
    for cid in todo:
        data = None
        while (key := ring.key()) is not None:
            try:
                data = fetch(key, cid)
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace")
                if e.code == 429 or is_quota_error(body):
                    ring.next_key("하루 한도 초과"); continue
                print(f"HTTP {e.code} ({cid}): {body[:200]!r} → 멈춤")
                break
            calls += 1
            ring.spent()
            if data.get("response", {}).get("header", {}).get("resultCode") != "0000":
                text = json.dumps(data, ensure_ascii=False)
                if is_quota_error(text):  # 한도 초과 등은 response 대신 OpenAPI_ServiceResponse 로 온다
                    data = None; ring.next_key("하루 한도 초과"); continue
                print(f"API 오류 ({cid}): {text[:200]} → 멈춤")
                data = None
            break
        if data is None:
            break
        (OUT_DIR / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        saved += 1
        time.sleep(0.1)
    print(f"사용한 키: {ring.summary()}")
    left = len(todo) - saved
    print(f"호출 {calls}건, 저장 {saved}곳, 남은 음식점 {left}곳 (하루 990건 기준 약 {-(-left // DEFAULT_MAX_CALLS)}일)")


if __name__ == "__main__":
    main()
