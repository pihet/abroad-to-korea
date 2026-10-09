"""국민여행조사 원자료(2023~2025)로 시군구별 '1박 2일 1인 여행 경비' 표를 만든다.

진실 님 검토 보고서(references/COST/COST/여행 경비 데이터 검토 보고서.pdf, 2026-10-07)의 권고를 따른다.
    - 순수 관광·휴양 여행만 (여행유형 CASE = 1). 친지 방문·출장은 경비 성격이 달라 뺀다
    - 1인 경비 D_TRAk_ONE_COST (총경비 ÷ 비용 포함 인원 NUM), 가중치 WT_DOM
    - 대표 목적지: 숙박 여행은 가장 오래 머문 방문지, 당일 여행은 첫 방문지
    - 표시값은 가중 중앙값과 25~75% 범위 (극단값에 덜 흔들림, 극단값은 지우지 않음)
    - 시군구 표본이 MIN_N 미만이면 그 시도 값으로 대신한다 (화면에 'OO 평균'으로 표시)
    - 옛 인천 중구·동구·서구는 2026년 개편으로 새 구에 나눌 근거가 없어 인천 시도 값에만 넣는다
3년치는 물가 보정 없이 합친다 (2년 차이, 표본을 약 3배로 늘리는 쪽이 더 중요).
출발지에서 오가는 교통비가 포함된 값이라 멀리서 오면 더 들 수 있다.

실행 (pyreadstat 필요, 한 번만 돌리면 된다. 서버는 결과 CSV만 읽는다):
    pip install pyreadstat
    python src/cost/build_cost_table.py [원자료 폴더]
결과: data/interim/app/travel_cost.csv
"""

import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/model"))
import clip_proto as cp  # noqa: E402

SRC = ROOT / "references/COST/COST/전국여행조사(경비)"
FILES = {2023: "전국여행조사2023/2023년 국민여행조사 원자료_국내여행.SAV",
         2024: "전국여행조사2024/2024년 국민여행조사 국내여행 RAWDATA.sav",
         2025: "전국여행조사2025/2025년 국민여행조사 원자료(국내여행).SAV"}
OUT = ROOT / "data/interim/app/travel_cost.csv"
MIN_N = 30
# 설문 지역명의 시도 → 프로젝트 시도 (2026년 통합·명칭 변경 반영)
SIDO = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시", "광주": "전남광주통합특별시",
        "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도", "강원": "강원특별자치도",
        "충청북": "충청북도", "충북": "충청북도", "충청남": "충청남도", "충남": "충청남도", "전라북": "전북특별자치도",
        "전북": "전북특별자치도", "전라남": "전남광주통합특별시", "전남": "전남광주통합특별시", "경상북": "경상북도",
        "경북": "경상북도", "경상남": "경상남도", "경남": "경상남도", "제주": "제주특별자치도"}


def region_maps():
    """(프로젝트 시도명, 시군구 첫 단어) → 키, 시도명 → 시도 코드."""
    by_name, sido_code = {}, {}
    for code, sido, name in cp.load_regions().values():
        by_name[(sido, name)] = f"{code}_{name}"
        sido_code[sido] = code
    return by_name, sido_code


def to_project(label, by_name):
    """'강원도 강릉시' → ('강원특별자치도', '51_강릉시'). 시군구가 없으면 (시도, None)."""
    if not label:
        return None, None
    head, _, rest = label.partition(" ")
    sido = next((v for k, v in SIDO.items() if head.startswith(k)), None)
    name = rest.split()[0] if rest else ""
    return sido, by_name.get((sido, name))


def trips(path: Path, year: int) -> pd.DataFrame:
    import pyreadstat
    _, meta = pyreadstat.read_sav(path, metadataonly=True)
    ks = sorted({int(m.group(1)) for c in meta.column_names if (m := re.match(r"D_TRA(\d+)_CASE$", c))})
    js = sorted({int(m.group(1)) for c in meta.column_names if (m := re.match(r"D_TRA1_(\d+)_SPOT$", c))})
    want = ["WT_DOM"]
    for k in ks:
        want += [f"D_TRA{k}_{f}" for f in ("CASE", "S_Day", "ONE_COST")]
        for j in js:
            want += [f"D_TRA{k}_{j}_{f}" for f in ("SPOT", "SYEAR", "SMONTH", "SDAY", "EYEAR", "EMONTH", "EDAY")]
    df, _ = pyreadstat.read_sav(path, usecols=[c for c in want if c in meta.column_names])
    labels = meta.variable_value_labels.get("D_TRA1_1_SPOT", {})
    out = []
    for k in ks:
        p = f"D_TRA{k}_"
        sub = df[df[p + "CASE"] == 1]
        for _, r in sub.iterrows():
            nights = int(r[p + "S_Day"]) if pd.notna(r[p + "S_Day"]) else 0
            best, best_n = None, -1
            for j in js:
                spot = r.get(f"{p}{j}_SPOT")
                if pd.isna(spot):
                    continue
                if nights == 0:  # 당일: 첫 방문지
                    best = spot
                    break
                try:
                    d0 = date(int(r[f"{p}{j}_SYEAR"]), int(r[f"{p}{j}_SMONTH"]), int(r[f"{p}{j}_SDAY"]))
                    d1 = date(int(r[f"{p}{j}_EYEAR"]), int(r[f"{p}{j}_EMONTH"]), int(r[f"{p}{j}_EDAY"]))
                    n = (d1 - d0).days
                except (ValueError, TypeError):
                    n = 0
                if n > best_n:  # 숙박: 가장 오래 머문 방문지 (같으면 먼저 간 곳)
                    best, best_n = spot, n
            if best is not None and pd.notna(r[p + "ONE_COST"]):
                out.append({"year": year, "w": r["WT_DOM"], "nights": nights, "cost": r[p + "ONE_COST"],
                            "spot": labels.get(best)})
    return pd.DataFrame(out)


def wquant(x: pd.DataFrame, qs=(0.25, 0.5, 0.75)):
    x = x.sort_values("cost")
    c = x["w"].cumsum() / x["w"].sum()
    return [float(x["cost"].iloc[int(np.searchsorted(c.values, q))]) for q in qs]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    by_name, sido_code = region_maps()
    t = pd.concat([trips(src / f, y) for y, f in FILES.items()], ignore_index=True)
    t[["sido", "key"]] = t["spot"].apply(lambda s: pd.Series(to_project(s, by_name)))
    print(f"관광 여행 {len(t)}건 (연도별 {t.year.value_counts().sort_index().to_dict()}), "
          f"시군구 연결 {t.key.notna().mean():.1%}, 시도만 {(t.key.isna() & t.sido.notna()).sum()}건")
    rows = []
    for kind, mask in (("day", t.nights == 0), ("1night", t.nights == 1)):
        d = t[mask]
        sido_val = {s: (len(g), *wquant(g)) for s, g in d.groupby("sido")}
        for (sido, name), key in by_name.items():
            g = d[d.key == key]
            if len(g) >= MIN_N:
                n, p25, p50, p75 = len(g), *wquant(g)
                level = "sigungu"
            else:
                n, p25, p50, p75 = sido_val.get(sido, (0, None, None, None))
                level = "sido"
            rows.append({"key": key, "trip": kind, "level": level, "sido": sido, "n": n, "p25": p25, "median": p50, "p75": p75})
    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    for kind in ("day", "1night"):
        o = out[out.trip == kind]
        print(f"{kind}: 시군구 값 {int((o.level == 'sigungu').sum())}곳, 시도 값으로 대신 {int((o.level == 'sido').sum())}곳")
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
