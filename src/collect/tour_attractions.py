"""TourAPI(KorService2) 관광지(contentTypeId=12) 전체 목록을 내려받아 data/raw/에 원본 그대로 저장한다.

실행:
    python src/collect/tour_attractions.py        # 관광지(12)
    python src/collect/tour_attractions.py 28     # 다른 콘텐츠 유형 (28 레포츠, 14 문화시설 ...)

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
CONTENT_TYPE_ID = 12  # 기본 관광지. 실행 인자로 바꾼다 (28 레포츠)
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
        sys.exit("TOUR_API_KEY 가 없습니다. 저장소 루트의 .env에 값을 채우세요.")
    return key


def load_api_keys() -> list[str]:
    """TOUR_API_KEY, TOUR_API_KEY_2, TOUR_API_KEY_3 … 순서대로 (조원 키를 더하면 하루에 더 받는다)."""
    keys = [load_api_key()]
    for i in range(2, 10):
        k = os.environ.get(f"TOUR_API_KEY_{i}", "").strip()
        if k:
            keys.append(k)
    return keys


def is_quota_error(text: str) -> bool:
    """하루 호출 한도 초과 응답인가 (HTTP 429 본문 또는 OpenAPI_ServiceResponse)."""
    return "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in text


def with_retry(fn, tries: int = 3):
    """시간 초과 같은 일시적 네트워크 오류는 잠깐 쉬고 다시 시도한다 (HTTP 오류는 바로 올린다)."""
    import urllib.error
    for i in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


class KeyRing:
    """인증키 여러 개를 차례로 쓴다. 키마다 하루 per_key 건까지, 한도 초과 응답이 오면 바로 다음 키로."""

    def __init__(self, per_key: int):
        self.keys, self.per_key, self.i = load_api_keys(), per_key, 0
        self.used = [0] * len(self.keys)

    def key(self):
        """지금 쓸 키. 남은 키가 없으면 None."""
        while self.i < len(self.keys) and self.used[self.i] >= self.per_key:
            self.i += 1
        return self.keys[self.i] if self.i < len(self.keys) else None

    def spent(self):
        self.used[self.i] += 1

    def next_key(self, why: str):
        print(f"키 {self.i + 1}/{len(self.keys)} {why} → 다음 키", flush=True)
        self.i += 1

    def summary(self) -> str:
        return " · ".join(f"키{n + 1} {u}건" for n, u in enumerate(self.used))


def build_url(key: str, page_no: int, content_type: int = CONTENT_TYPE_ID) -> str:
    """인증키는 포털 표시값이 이미 인코딩된 형태이므로 그대로 붙이고, 나머지 파라미터만 인코딩한다."""
    params = urllib.parse.urlencode(
        {
            "MobileOS": "ETC",
            "MobileApp": "samsungproj",
            "_type": "json",
            "numOfRows": ROWS_PER_PAGE,
            "pageNo": page_no,
            "contentTypeId": content_type,
        }
    )
    return f"{BASE_URL}?serviceKey={key}&{params}"


def fetch_page(key: str, page_no: int, content_type: int = CONTENT_TYPE_ID) -> dict:
    """한 페이지를 받아 JSON으로 돌려준다. API 오류 응답이면 원인을 담아 예외를 낸다."""
    url = build_url(key, page_no, content_type)
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
    ct = int(sys.argv[1]) if len(sys.argv) > 1 else CONTENT_TYPE_ID
    key = load_api_key()
    today = datetime.now().strftime("%Y%m%d")
    out_dir = PROJECT_ROOT / "data" / "raw" / "tourapi" / f"areaBasedList2_ct{ct}_{today}"
    if out_dir.exists():
        sys.exit(f"이미 수집된 폴더가 있습니다: {out_dir}\n원본은 덮어쓰지 않습니다. 다시 받으려면 폴더를 직접 옮긴 뒤 실행하세요.")

    first = fetch_page(key, 1, ct)  # 인증 오류면 여기서 멈추므로 빈 폴더가 남지 않는다
    out_dir.mkdir(parents=True)
    body = first["response"]["body"]
    total = int(body["totalCount"])
    pages = (total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE
    print(f"전체 {total}건, {pages}페이지")

    n_items = 0
    for page_no in range(1, pages + 1):
        data = first if page_no == 1 else fetch_page(key, page_no, ct)
        items = data["response"]["body"]["items"]
        n = len(items["item"]) if items else 0
        n_items += n
        (out_dir / f"page_{page_no:03d}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"  page {page_no}/{pages}: {n}건")
        time.sleep(REQUEST_INTERVAL_SEC)

    manifest = {
        "endpoint": BASE_URL,
        "contentTypeId": ct,
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
