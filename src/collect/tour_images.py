"""TourAPI 관광지별 추가 이미지(detailImage2)를 내려받아 data/raw/ 에 원본 그대로 저장한다.

개발계정은 오퍼레이션당 하루 1,000건이라 관광지 12,603곳을 하루에 다 받을 수 없다.
그래서 매일 이어서 받는 방식으로 만들었다.
    - 순서: 시군구를 돌아가며 한 곳씩 (시군구 안은 고정 난수 순서). 어느 날 멈춰도 모든 시군구가 고르게 받는다
    - 정답 쌍과 무관한 순서다 (정답 지역을 먼저 받으면 평가가 부풀려진다)
    - 이미 받은 관광지는 건너뛴다. 한도 초과 응답이 오면 멈춘다

실행:
    python src/collect/tour_images.py            # 오늘 최대 990건
    python src/collect/tour_images.py 300        # 최대 300건
    python src/collect/tour_images.py --food     # 대표 사진(firstimage)이 없는 음식점만 (2026-10-08 추가, 3,954곳)
    python src/collect/tour_images.py --ids 목록.txt  # 지정한 contentid만 (한 줄에 하나, 결과는 detailImage2/)

결과: data/raw/tourapi/detailImage2/<contentid>.json (응답 원문), 음식점은 detailImage2_ct39/
"""

import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

from tour_attractions import PROJECT_ROOT, KeyRing, is_quota_error, with_retry

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/detailImage2"
RAW_LIST = PROJECT_ROOT / "data/raw/tourapi/areaBasedList2_ct12_20261002"
OUT_DIR = PROJECT_ROOT / "data/raw/tourapi/detailImage2"
FOOD_LIST = PROJECT_ROOT / "data/raw/tourapi/areaBasedList2_ct39_20261006"
FOOD_OUT_DIR = PROJECT_ROOT / "data/raw/tourapi/detailImage2_ct39"
DEFAULT_MAX_CALLS = 990
SEED = 42


def queue(raw_list=RAW_LIST, only_without_image=False) -> list[str]:
    """시군구 라운드로빈 순서의 contentid 목록. only_without_image면 목록에 대표 사진이 없는 곳만."""
    items = []
    for p in sorted(raw_list.glob("page_*.json")):
        items += json.loads(p.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    if only_without_image:
        items = [it for it in items if not it.get("firstimage")]
    by_region = defaultdict(list)
    for it in items:
        by_region[(it["lDongRegnCd"], it["lDongSignguCd"])].append(it["contentid"])
    rng = random.Random(SEED)
    regions = sorted(by_region)
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
                                     "contentId": cid, "imageYN": "Y", "numOfRows": 50, "pageNo": 1})
    with urllib.request.urlopen(f"{BASE_URL}?serviceKey={key}&{params}", timeout=60) as r:
        body = r.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON이 아닌 응답 ({cid}): {body[:300]}") from None


def main() -> None:
    food = "--food" in sys.argv
    ids_file = sys.argv[sys.argv.index("--ids") + 1] if "--ids" in sys.argv else None
    nums = [a for a in sys.argv[1:] if a.isdigit()]
    max_calls = int(nums[0]) if nums else DEFAULT_MAX_CALLS
    ring = KeyRing(max_calls)  # 키마다 max_calls 건, 한도가 차면 다음 키
    out_dir = FOOD_OUT_DIR if food else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    source = (open(ids_file, encoding="utf-8").read().split() if ids_file else queue(FOOD_LIST, True) if food else queue())
    todo = [c for c in source if not (out_dir / f"{c}.json").exists()]
    print(f"남은 {'음식점(대표 사진 없음)' if food else '관광지'} {len(todo)}곳, 키 {len(ring.keys)}개 × 최대 {max_calls}건")
    calls = saved = 0
    for cid in todo:
        data = None
        while (key := ring.key()) is not None:
            try:
                data = with_retry(lambda: fetch(key, cid))
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace")
                if e.code == 429 or is_quota_error(body):
                    ring.next_key("하루 한도 초과"); continue
                print(f"HTTP {e.code} ({cid}): {body[:200]!r} → 멈춤")
                break
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"네트워크 오류 3회 ({cid}): {e} → 멈춤 (다시 실행하면 이어서 받음)")
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
        (out_dir / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        saved += 1
        time.sleep(0.1)
    print(f"사용한 키: {ring.summary()}")
    left = len(todo) - saved
    print(f"호출 {calls}건, 저장 {saved}곳, 남은 관광지 {left}곳 (하루 990건 기준 약 {-(-left // DEFAULT_MAX_CALLS)}일)")


if __name__ == "__main__":
    main()
