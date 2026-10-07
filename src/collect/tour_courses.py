"""TourAPI 여행코스(contentTypeId=25)의 코스 구성(detailInfo2)과 소개(detailIntro2)를 내려받아 원본 그대로 저장한다.

- detailInfo2: 코스에 들르는 곳 (순서 subnum, 이름 subname, 관광지 id subcontentid, 설명 subdetailoverview)
- detailIntro2: 코스 총거리(distance), 소요시간(taketime), 테마(theme)
개발계정은 오퍼레이션당 하루 1,000건이라 1,068개 코스를 이틀에 나눠 받는다. 받은 코스는 건너뛰고, 한도 초과면 멈춘다.
detailIntro2 는 음식점 대표메뉴(tour_food_intro.py)와 한도를 같이 쓰므로, 같은 날 둘 다 돌리면 먼저 돈 쪽이 한도를 쓴다.

실행 (먼저 목록: python src/collect/tour_attractions.py 25):
    python src/collect/tour_courses.py              # 구성·소개 각각 오늘 최대 990건
    python src/collect/tour_courses.py info 300     # 구성만 최대 300건

결과: data/raw/tourapi/detailInfo2_ct25/<contentid>.json, data/raw/tourapi/detailIntro2_ct25/<contentid>.json
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from tour_attractions import PROJECT_ROOT, KeyRing, is_quota_error

BASE = "https://apis.data.go.kr/B551011/KorService2"
RAW = PROJECT_ROOT / "data/raw/tourapi"
OPS = {"info": ("detailInfo2", RAW / "detailInfo2_ct25"), "intro": ("detailIntro2", RAW / "detailIntro2_ct25")}
DEFAULT_MAX_CALLS = 990


def course_ids() -> list[str]:
    dirs = sorted(RAW.glob("areaBasedList2_ct25_*"))
    if not dirs:
        sys.exit("여행코스 목록이 없습니다. 먼저 python src/collect/tour_attractions.py 25 를 실행하세요.")
    ids = []
    for p in sorted(dirs[-1].glob("page_*.json")):
        ids += [it["contentid"] for it in json.loads(p.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]]
    return ids


def fetch(key: str, op: str, cid: str) -> dict:
    params = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json",
                                     "contentId": cid, "contentTypeId": 25, "numOfRows": 50, "pageNo": 1})
    with urllib.request.urlopen(f"{BASE}/{op}?serviceKey={key}&{params}", timeout=60) as r:  # 키는 포털 값 그대로 붙인다
        body = r.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON이 아닌 응답 ({op} {cid}): {body[:300]}") from None


def fetch_retry(key: str, op: str, cid: str, tries: int = 3) -> dict:
    """시간 초과 같은 일시적 네트워크 오류는 잠깐 쉬고 다시 시도한다 (HTTP 오류는 바로 올린다)."""
    for i in range(tries):
        try:
            return fetch(key, op, cid)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def run(which: str, max_calls: int) -> None:
    op, out = OPS[which]
    out.mkdir(parents=True, exist_ok=True)
    ring = KeyRing(max_calls)  # 키마다 max_calls 건, 한도가 차면 다음 키 (한도는 오퍼레이션별이라 구성·소개 따로 센다)
    todo = [c for c in course_ids() if not (out / f"{c}.json").exists()]
    print(f"[{op}] 남은 코스 {len(todo)}개, 키 {len(ring.keys)}개 × 최대 {max_calls}건", flush=True)
    saved = 0
    for cid in todo:
        data = None
        while (key := ring.key()) is not None:
            try:
                data = fetch_retry(key, op, cid)
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace")
                if e.code == 429 or is_quota_error(body):
                    ring.next_key("하루 한도 초과"); continue
                print(f"HTTP {e.code} ({cid}): {body[:200]!r} → 멈춤")
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"네트워크 오류 3회 ({cid}): {e} → 멈춤 (다시 실행하면 이어서 받음)")
            else:
                ring.spent()
                if data.get("response", {}).get("header", {}).get("resultCode") == "0000":
                    break
                text = json.dumps(data, ensure_ascii=False)
                if is_quota_error(text):
                    ring.next_key("하루 한도 초과"); data = None; continue
                print(f"API 오류 ({cid}): {text[:200]} → 멈춤")
            data = None
            break
        if data is None:
            break
        (out / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        saved += 1
        time.sleep(0.1)
    print(f"[{op}] 저장 {saved}개, 남은 코스 {len(todo) - saved}개 (사용한 키: {ring.summary()})", flush=True)


def main() -> None:
    which = [a for a in sys.argv[1:] if a in OPS] or list(OPS)
    nums = [int(a) for a in sys.argv[1:] if a.isdigit()]
    for w in which:
        run(w, nums[0] if nums else DEFAULT_MAX_CALLS)


if __name__ == "__main__":
    main()
