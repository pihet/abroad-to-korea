"""TourAPI 대표 사진이 없는 음식점을 네이버 이미지 검색 API로 찾아 응답 원문을 저장한다.

사진 파일은 받지 않는다. 화면은 네이버가 준 썸네일 주소로 바로 띄우고, 어떤 결과를 쓸지는
app/activities.py 의 naver_pick() 이 고른다 (가게 이름이 제목에 있고 출처가 가게 사진 위주인 곳만).

- 검색어: "가게 이름 시군구" (예: "연포갈비 수원시"), 상위 5개
- 네이버 검색 API 하루 25,000건, 초당 10건 제한 → 0.12초 간격
- 이미 받은 음식점은 건너뛴다

실행:
    python src/collect/naver_food_images.py          # 남은 음식점 전부
    python src/collect/naver_food_images.py 50       # 50곳만 (확인용)

필요: .env 의 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET (developers.naver.com 의 '검색' API)
결과: data/raw/naver_image/<contentid>.json (응답 원문 + 검색어)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from tour_attractions import PROJECT_ROOT, with_retry

API = "https://openapi.naver.com/v1/search/image"
FOOD_LIST = PROJECT_ROOT / "data/raw/tourapi/areaBasedList2_ct39_20261006"
OUT_DIR = PROJECT_ROOT / "data/raw/naver_image"


def load_env() -> dict:
    """키 두 개만 .env 에서 읽는다 (.env 전체를 셸로 불러오면 다른 줄 때문에 실패할 수 있다)."""
    env = {k: os.environ.get(k, "") for k in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")}
    path = PROJECT_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() in env and not env[k.strip()]:
                env[k.strip()] = v.strip().strip('"').strip("'")
    if not all(env.values()):
        sys.exit(".env 에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 를 넣어 주세요.")
    return env


def targets() -> list[dict]:
    items = []
    for p in sorted(FOOD_LIST.glob("page_*.json")):
        items += json.loads(p.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    return [it for it in items if not it.get("firstimage")]


def query_of(it: dict) -> str:
    sigungu = (it.get("addr1", "").split() + ["", ""])[1]
    return f"{it['title']} {sigungu}".strip()


def search(env: dict, q: str) -> dict:
    url = f"{API}?{urllib.parse.urlencode({'query': q, 'display': 5, 'filter': 'medium'})}"
    req = urllib.request.Request(url, headers={"X-Naver-Client-Id": env["NAVER_CLIENT_ID"],
                                               "X-Naver-Client-Secret": env["NAVER_CLIENT_SECRET"]})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    env = load_env()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    todo = [it for it in targets() if not (OUT_DIR / f"{it['contentid']}.json").exists()][:limit]
    print(f"남은 음식점 {len(todo)}곳")
    saved = 0
    for it in todo:
        q = query_of(it)
        try:
            data = with_retry(lambda: search(env, q))
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code} ({it['contentid']}): {e.read()[:200]!r} → 멈춤 (다시 실행하면 이어서 받음)")
            break
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"네트워크 오류 3회 ({it['contentid']}): {e} → 멈춤")
            break
        (OUT_DIR / f"{it['contentid']}.json").write_text(json.dumps({"query": q, **data}, ensure_ascii=False), encoding="utf-8")
        saved += 1
        if saved % 500 == 0:
            print(f"  {saved}곳")
        time.sleep(0.12)
    print(f"저장 {saved}곳, 남은 {len(todo) - saved}곳")


if __name__ == "__main__":
    main()
