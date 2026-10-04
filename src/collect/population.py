"""행정안전부 행정동별 주민등록 인구(admmPpltnHhStus)를 읍·면·동 단위로 받아 data/raw/ 에 원본 그대로 저장한다.

도시/시골 구분(#13)에 쓴다: 시군구 인구 중 '동' 지역에 사는 비율 (통계청 동부/읍면부 구분과 같은 방식).

실행:
    python src/collect/population.py            # 기본 2026-09
    python src/collect/population.py 202609

결과: data/raw/mois_population/<YYYYMM>/sido.json, sgg_<시도코드>.json, dong_<시군구코드>.json (응답 원문)
호출 수: 시도 1 + 시군구 목록 16~17 + 읍면동 약 250 = 약 270건 (개발계정 하루 한도 안).
이미 받은 파일은 건너뛴다.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tour_attractions import PROJECT_ROOT, load_api_key  # noqa: E402

BASE_URL = "https://apis.data.go.kr/1741000/admmPpltnHhStus/selectAdmmPpltnHhStus"
DEFAULT_YM = "202609"


def fetch(key, admm_cd, lv, ym):
    q = urllib.parse.urlencode({"type": "JSON", "numOfRows": 1000, "pageNo": 1, "regSeCd": 1,
                                "admmCd": admm_cd, "lv": lv, "srchFrYm": ym, "srchToYm": ym})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{BASE_URL}?serviceKey={key}&{q}", timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    head = data["Response"]["head"]
    if head.get("resultCode") not in ("0", "3"):  # 3 = 결과 없음
        raise RuntimeError(f"API 오류 {admm_cd} lv{lv}: {head}")
    return data


def items(data):
    it = ((data["Response"].get("items") or {}).get("item")) or []
    return [it] if isinstance(it, dict) else it  # 결과가 1건이면 목록이 아니라 항목 하나로 온다


def saved(path, make):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = make()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.2)
    return data


def main():
    ym = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_YM
    key = load_api_key()
    out = PROJECT_ROOT / "data/raw/mois_population" / ym
    out.mkdir(parents=True, exist_ok=True)
    sidos = items(saved(out / "sido.json", lambda: fetch(key, "1100000000", 1, ym)))
    n_dong = 0
    for s in sidos:
        sggs = items(saved(out / f"sgg_{s['admmCd']}.json", lambda: fetch(key, s["admmCd"], 2, ym)))
        for g in sggs:
            n_dong += len(items(saved(out / f"dong_{g['admmCd']}.json", lambda: fetch(key, g["admmCd"], 3, ym))))
        print(f"  {s['ctpvNm']}: 시군구 {len(sggs)}곳", flush=True)
    print(f"완료 {ym}: 시도 {len(sidos)}, 읍면동 {n_dong} → {out}")


if __name__ == "__main__":
    main()
