"""시군구별 여행 조건 데이터를 내려받아 data/raw/ 에 원본 그대로 저장한다.

    climate    Open-Meteo 과거 날씨: 시군구 중심 좌표(관광지 좌표 중앙값)의 2021~2025년 MONTH 월 일별 평균기온·강수
               (무료 한도가 요청 데이터 양 기준이라 한 달·2변수만 받는다. 처음 받은 70곳은 2016~2025 전체 기간 파일이고,
                읽는 쪽에서 2021~2025 의 같은 달만 쓴다)
               → 10월: data/raw/openmeteo/archive_<시도코드>_<시군구>.json
               → 그 밖의 달: data/raw/openmeteo/m<MM>/archive_<시도코드>_<시군구>.json  (10곳씩 묶어 요청)
               읽을 때는 monthly_climate() 를 쓴다 (전체 기간 파일 70곳은 모든 달을 이미 담고 있다)
    festivals  TourAPI searchFestival2: 지정 기간에 열리는 축제
               → data/raw/tourapi/searchFestival2_<시작>_<끝>.json

실행:
    python src/collect/region_context.py climate            # 10월
    python src/collect/region_context.py climate 1 2 3      # 지정한 달들
    python src/collect/region_context.py festivals 20261001 20261031
"""

import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from calendar import monthrange
from collections import defaultdict

from tour_attractions import PROJECT_ROOT, load_api_key

RAW_LIST = PROJECT_ROOT / "data/raw/tourapi/areaBasedList2_ct12_20261002"
LDONG = PROJECT_ROOT / "data/raw/tourapi/ldongCode2_list_20261002.json"
CLIMATE_DIR = PROJECT_ROOT / "data/raw/openmeteo"
BATCH = 10


def region_centers():
    """(시도코드, 시군구명 첫 단어) → 관광지 좌표 중앙값. 구는 시로 합친다 (clip_proto.load_regions 와 같은 단위)."""
    names = {}
    for x in json.loads(LDONG.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]:
        names[(x["lDongRegnCd"], x["lDongSignguCd"])] = (x["lDongRegnCd"], x["lDongSignguNm"].split()[0])
    pts = defaultdict(list)
    for p in sorted(RAW_LIST.glob("page_*.json")):
        for it in json.loads(p.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]:
            u = names.get((it["lDongRegnCd"], it["lDongSignguCd"]))
            try:
                lat, lon = float(it["mapy"]), float(it["mapx"])
            except (TypeError, ValueError):
                continue
            if u:
                pts[u].append((lat, lon))
    return {u: (round(statistics.median(a for a, _ in v), 4), round(statistics.median(b for _, b in v), 4))
            for u, v in pts.items()}


def climate_path(sido_code, sigungu, month):
    if month == 10:
        return CLIMATE_DIR / f"archive_{sido_code}_{sigungu}.json"
    return CLIMATE_DIR / f"m{month:02d}" / f"archive_{sido_code}_{sigungu}.json"


def _has_full_range(sido_code, sigungu):
    """처음 받은 70곳: 10월 파일이 2016~2025 전체 기간을 담고 있다 (region.months 표시 없음)."""
    f = CLIMATE_DIR / f"archive_{sido_code}_{sigungu}.json"
    return f.exists() and "months" not in json.loads(f.read_text()).get("region", {})


def monthly_climate(sido_code, sigungu, month, years=("2021", "2025")):
    """2021~2025년 해당 달의 일별 평균기온·강수 목록. 없으면 None."""
    for f in (climate_path(sido_code, sigungu, month), CLIMATE_DIR / f"archive_{sido_code}_{sigungu}.json"):
        if not f.exists():
            continue
        d = json.loads(f.read_text())["daily"]
        sel = [i for i, t in enumerate(d["time"]) if years[0] <= t[:4] <= years[1] and int(t[5:7]) == month]
        if sel:
            return {k: [d[k][i] for i in sel] for k in ("time", "temperature_2m_mean", "precipitation_sum")}
    return None


def climate(month=10):
    centers = region_centers()
    todo = [(u, c) for u, c in sorted(centers.items())
            if not climate_path(u[0], u[1], month).exists() and not _has_full_range(u[0], u[1])]
    climate_path("x", "x", month).parent.mkdir(parents=True, exist_ok=True)
    print(f"[{month}월] 시군구 {len(centers)}곳, 받을 곳 {len(todo)}곳", flush=True)
    for s in range(0, len(todo), BATCH):
        chunk = todo[s:s + BATCH]
        merged = [{"daily": {"time": [], "temperature_2m_mean": [], "precipitation_sum": []}} for _ in chunk]
        for year in range(2021, 2026):  # 요청량을 줄이려고 해마다 그 한 달만 받는다
            params = urllib.parse.urlencode({
                "latitude": ",".join(str(c[0]) for _, c in chunk), "longitude": ",".join(str(c[1]) for _, c in chunk),
                "start_date": f"{year}-{month:02d}-01", "end_date": f"{year}-{month:02d}-{monthrange(year, month)[1]}",
                "timezone": "Asia/Seoul", "daily": "temperature_2m_mean,precipitation_sum",
            })
            for attempt in range(12):
                try:
                    with urllib.request.urlopen(f"https://archive-api.open-meteo.com/v1/archive?{params}", timeout=180) as r:
                        data = json.loads(r.read().decode("utf-8"))
                    break
                except Exception as e:  # 429(시간당 한도)·일시 오류는 10분 기다렸다 재시도
                    if attempt == 11:
                        raise RuntimeError(f"Open-Meteo 요청 실패 ({chunk[0][0]} 외): {e}") from None
                    print(f"  대기 10분 ({e})", flush=True)
                    time.sleep(600)
            data = data if isinstance(data, list) else [data]
            for m, d in zip(merged, data):
                for k in m["daily"]:
                    m["daily"][k] += d["daily"][k]
            time.sleep(1)
        for (u, c), d in zip(chunk, merged):
            d["region"] = {"sido_code": u[0], "sigungu": u[1], "center": c, "months": [month], "years": "2021-2025"}
            climate_path(u[0], u[1], month).write_text(json.dumps(d), encoding="utf-8")
        print(f"  {s + len(chunk)}/{len(todo)}", flush=True)


def festivals(start, end):
    key = load_api_key()
    params = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json",
                                     "numOfRows": 1000, "pageNo": 1, "eventStartDate": start, "eventEndDate": end})
    with urllib.request.urlopen(f"https://apis.data.go.kr/B551011/KorService2/searchFestival2?serviceKey={key}&{params}",
                                timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("response", {}).get("header", {}).get("resultCode") != "0000":
        raise RuntimeError(f"API 오류: {json.dumps(data, ensure_ascii=False)[:300]}")
    out = PROJECT_ROOT / f"data/raw/tourapi/searchFestival2_{start}_{end}.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    body = data["response"]["body"]
    print(f"축제 {body['totalCount']}건 → {out}")


if __name__ == "__main__":
    if sys.argv[1] == "climate":
        for m in [int(x) for x in sys.argv[2:]] or [10]:
            climate(m)
    else:
        festivals(sys.argv[2], sys.argv[3])
