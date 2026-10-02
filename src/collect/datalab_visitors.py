"""관광 빅데이터 지역별 방문자수(기초 지자체, 일 단위)를 월별로 내려받아 data/raw/에 원본 그대로 저장한다.

실행:
    python src/collect/datalab_visitors.py                 # 2018-01 ~ 2026-08
    python src/collect/datalab_visitors.py 202501 202512   # 기간 지정 (YYYYMM)

필요:
    .env 또는 환경변수에 TOUR_API_KEY (TourAPI와 같은 키, 다시 인코딩하지 않는다)

결과:
    data/raw/datalab/locgoRegnVisitrDDList/<YYYYMM>.json.gz  (응답 원문, gzip)

한 달치(약 2.5만 행)를 numOfRows=50000 한 번으로 받는다. 이미 받은 달은 건너뛴다 (원본 덮어쓰기 금지).
"""

import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from calendar import monthrange
from pathlib import Path

from tour_attractions import PROJECT_ROOT, load_api_key

BASE_URL = "https://apis.data.go.kr/B551011/DataLabService/locgoRegnVisitrDDList"
ROWS = 50000
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "datalab" / "locgoRegnVisitrDDList"
DEFAULT_START, DEFAULT_END = "201801", "202608"


def months(start: str, end: str):
    y, m = int(start[:4]), int(start[4:])
    while f"{y}{m:02d}" <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_month(key: str, y: int, m: int) -> dict:
    params = urllib.parse.urlencode({
        "MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json",
        "numOfRows": ROWS, "pageNo": 1,
        "startYmd": f"{y}{m:02d}01", "endYmd": f"{y}{m:02d}{monthrange(y, m)[1]:02d}",
    })
    url = f"{BASE_URL}?serviceKey={key}&{params}"
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} ({y}-{m:02d}): {e.read()[:300]!r}") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == 3:
                raise RuntimeError(f"{y}-{m:02d} 요청 실패: {e}") from None
            time.sleep(10 * attempt)
    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "0000":
        raise RuntimeError(f"API 오류 ({y}-{m:02d}): {json.dumps(data, ensure_ascii=False)[:300]}")
    body = data["response"]["body"]
    n_items = len(body["items"]["item"]) if body["items"] else 0
    if n_items != int(body["totalCount"]):
        raise RuntimeError(f"{y}-{m:02d}: 받은 행({n_items})이 totalCount({body['totalCount']})와 다름. numOfRows 확인")
    return data


def main() -> None:
    start, end = (sys.argv[1], sys.argv[2]) if len(sys.argv) == 3 else (DEFAULT_START, DEFAULT_END)
    key = load_api_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for y, m in months(start, end):
        path = OUT_DIR / f"{y}{m:02d}.json.gz"
        if path.exists():
            continue
        data = fetch_month(key, y, m)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"{y}-{m:02d}: {data['response']['body']['totalCount']}행", flush=True)
        time.sleep(0.5)
    print(f"완료: {OUT_DIR}")


if __name__ == "__main__":
    main()
