"""TourAPI(KorService2) 관광지(contentTypeId=12) 전체 목록을 내려받아 data/raw/에 원본 그대로 저장한다.

실행:
    python src/collect/tour_attractions.py

필요:
    .env 또는 환경변수에 TOUR_API_KEY (공공데이터포털에 표시된 인증키를 그대로. 다시 인코딩하지 않는다)

결과:
    data/raw/tourapi/areaBasedList2_ct12_<YYYYMMDD>/page_001.json ...  (응답 원문)
    data/raw/tourapi/areaBasedList2_ct12_<YYYYMMDD>/manifest.json      (수집 조건, 건수, 시각)

같은 날짜 폴더가 이미 있으면 덮어쓰지 않고 멈춘다 (data/raw/ 는 수정 금지).
표준 라이브러리만 사용한다.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/areaBasedList2"
CONTENT_TYPE_ID = 12  # 관광지
ROWS_PER_PAGE = 1000
REQUEST_INTERVAL_SEC = 0.5
MAX_RETRIES = 3

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_api_key() -> str:
    """환경변수 또는 프로젝트 루트 .env 에서 TOUR_API_KEY 를 읽는다."""
    try:
        from dotenv import load_dotenv  # requirements.txt 의 python-dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("TOUR_API_KEY", "").strip()
    if not key:
        sys.exit("TOUR_API_KEY 가 없습니다. .env.example 을 복사해 .env 를 만들고 값을 채우세요.")
    return key


def build_url(key: str, page_no: int) -> str:
    """인증키는 포털 표시값이 이미 인코딩된 형태이므로 그대로 붙이고, 나머지 파라미터만 인코딩한다."""
    params = urllib.parse.urlencode(
        {
            "MobileOS": "ETC",
            "MobileApp": "samsungproj",
            "_type": "json",
            "numOfRows": ROWS_PER_PAGE,
            "pageNo": page_no,
            "contentTypeId": CONTENT_TYPE_ID,
        }
    )
    return f"{BASE_URL}?serviceKey={key}&{params}"


def fetch_page(key: str, page_no: int) -> dict:
    """한 페이지를 받아 JSON으로 돌려준다. API 오류 응답이면 원인을 담아 예외를 낸다."""
    url = build_url(key, page_no)
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                body = resp.read().decode("utf-8")
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            # 인증 오류 등은 재시도해도 같으므로 바로 원인을 보여준다
            raise RuntimeError(f"HTTP {e.code} (page {page_no}): {body[:300]}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            time.sleep(5 * attempt)
    else:
        raise RuntimeError(f"page {page_no} 요청 실패: {last_error}")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON이 아닌 응답 (page {page_no}): {body[:300]}") from None

    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "0000":
        raise RuntimeError(f"API 오류 (page {page_no}): {json.dumps(data, ensure_ascii=False)[:300]}")
    return data


def main() -> None:
    key = load_api_key()
    today = datetime.now().strftime("%Y%m%d")
    out_dir = PROJECT_ROOT / "data" / "raw" / "tourapi" / f"areaBasedList2_ct{CONTENT_TYPE_ID}_{today}"
    if out_dir.exists():
        sys.exit(f"이미 수집된 폴더가 있습니다: {out_dir}\n원본은 덮어쓰지 않습니다. 다시 받으려면 폴더를 직접 옮긴 뒤 실행하세요.")

    first = fetch_page(key, 1)  # 인증 오류면 여기서 멈추므로 빈 폴더가 남지 않는다
    out_dir.mkdir(parents=True)
    body = first["response"]["body"]
    total = int(body["totalCount"])
    pages = (total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE
    print(f"전체 {total}건, {pages}페이지")

    n_items = 0
    for page_no in range(1, pages + 1):
        data = first if page_no == 1 else fetch_page(key, page_no)
        items = data["response"]["body"]["items"]
        n = len(items["item"]) if items else 0
        n_items += n
        (out_dir / f"page_{page_no:03d}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"  page {page_no}/{pages}: {n}건")
        time.sleep(REQUEST_INTERVAL_SEC)

    manifest = {
        "endpoint": BASE_URL,
        "contentTypeId": CONTENT_TYPE_ID,
        "numOfRows": ROWS_PER_PAGE,
        "totalCount": total,
        "pages": pages,
        "items_saved": n_items,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    if n_items != total:
        print(f"경고: 저장 건수({n_items})가 totalCount({total})와 다릅니다.")
    print(f"완료: {out_dir}")


if __name__ == "__main__":
    main()
