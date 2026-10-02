"""P1 혼잡도 예측: HANDOFF.md 10장 명세(Aside 원본 계산 설정)를 그대로 재현한다.

실행:
    .venv/bin/python src/forecast/p1_spec.py nager   # 공휴일 = Nager.Date + 수동 보정 (Aside 원본)
    .venv/bin/python src/forecast/p1_spec.py kasi    # 공휴일 = data/external/kr_holidays_2018_2027.csv (천문연 정식)

결과: 콘솔 표 + data/interim/p1/spec_<버전>.json

명세 요약 (자세한 정의는 HANDOFF 10장):
    대상   외지인(touDivCd=2), 2018-01-01~2026-08-31 결측 없는 시군구 (12xxx 신코드는 같은 이름 구코드에 더함)
    모델   ridge λ=1, 표준화 없음, 절편 벌점 제외, 정규방정식
    분할   목표 시점 연도 기준 학습 2019~2024 (코로나 포함) / 검증 2025
    월     특징 19개, 목표 log1p(a[t]), 예측 시점 t-2
    일     B1 위 잔차 보정, 특징 39개 (base 10 + base×주말민감도 10 + 요일 7 + 월 12)
"""

import csv
import gzip
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/datalab/locgoRegnVisitrDDList"
NAGER_DIR = ROOT / "data/raw/nager"
KASI_CSV = ROOT / "data/external/kr_holidays_2018_2027.csv"
OUT = ROOT / "data/interim/p1"
START, END = "2018-01-01", "2026-08-31"
TRAIN_YEARS, VAL_YEAR = set(range(2019, 2025)), 2025
NAGER_ADD = {"20250127", "20250506", "20250603", "20180613", "20220309", "20220601",
             "20240410", "20241001", "20231002", "20200415", "20200817"}
NAGER_REMOVE = {"20250717"}


# ------------------------------------------------------------------ 공통
def load_daily() -> pd.DataFrame:
    """행=날짜(2018-01-01~2026-08-31), 열=시군구. 결측 없는 시군구만."""
    rows = []
    for p in sorted(RAW.glob("*.json.gz")):
        rows += [i for i in json.load(gzip.open(p, "rt", encoding="utf-8"))["response"]["body"]["items"]["item"]
                 if i["touDivCd"] == "2"]
    df = pd.DataFrame(rows)
    old = df[df.signguCode.str[:2].isin(["46", "29"])][["signguCode", "signguNm"]].drop_duplicates()
    rename = {}
    for code, name in df[df.signguCode.str.startswith("12")][["signguCode", "signguNm"]].drop_duplicates().values:
        match = old[old.signguNm == name].signguCode.tolist()
        if len(match) == 1:
            rename[code] = match[0]
    df["code"] = df.signguCode.replace(rename)
    df["date"] = pd.to_datetime(df.baseYmd)
    df["y"] = df.touNum.astype(float)
    wide = df.pivot_table(index="date", columns="code", values="y", aggfunc="sum")  # 신코드는 구코드에 더함
    wide = wide.reindex(pd.date_range(START, END))
    return wide.loc[:, wide.notna().all()]


def ridge_fit(X: np.ndarray, y: np.ndarray, lam: float = 1.0) -> np.ndarray:
    """표준화 없이 정규방정식으로 푼다. X 첫 열은 절편(1)이며 벌점에서 제외한다."""
    P = np.eye(X.shape[1]) * lam
    P[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + P, X.T @ y)


def with_intercept(X):
    return np.column_stack([np.ones(len(X)), X])


def wape(y, p):
    return float(np.abs(p - y).sum() / y.sum())


def medape(y, p):
    return float(np.median(np.abs(p - y) / y))


# ------------------------------------------------------------------ 공휴일
def holidays_nager() -> set:
    """Nager.Date 2017~2026 (원본 응답은 data/raw/nager/ 에 캐시) + 수동 추가 − 제외."""
    NAGER_DIR.mkdir(parents=True, exist_ok=True)
    days = set()
    for y in range(2017, 2027):
        path = NAGER_DIR / f"KR_{y}.json"
        if not path.exists():
            req = urllib.request.Request(f"https://date.nager.at/api/v3/PublicHolidays/{y}/KR",
                                         headers={"User-Agent": "samsung-project2"})
            path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        days |= {h["date"].replace("-", "") for h in json.loads(path.read_text())}
    return (days | NAGER_ADD) - NAGER_REMOVE


def holidays_kasi() -> set:
    with open(KASI_CSV, encoding="utf-8") as f:
        return {r["date"] for r in csv.DictReader(f) if r["is_holiday"] == "Y"}


# ------------------------------------------------------------------ 월 단위
def monthly(wide: pd.DataFrame) -> dict:
    A = wide.resample("MS").sum()
    a, months = A.values, A.index
    R = a.shape[1]
    Xs, ys, b0s, b1s, yrs = [], [], [], [], []
    for t in range(len(months)):
        o = t - 2
        if o - 14 < 0 or months[t].year > VAL_YEAR:
            continue
        yr = months[t].year
        yoy = np.log((a[o] + a[o - 1] + a[o - 2] + 1) / (a[o - 12] + a[o - 13] + a[o - 14] + 1))
        a24 = a[t - 24] if t >= 24 else a[t - 12]
        onehot = np.zeros((R, 12))
        onehot[:, months[t].month - 1] = 1
        X = np.column_stack([
            np.log1p(a[t - 12]), np.log1p(a[o]), np.log1p(a[o - 1]), yoy, np.log1p(a24),
            np.full(R, int(yr in (2020, 2021))), np.full(R, int(yr - 1 in (2020, 2021))), onehot,
        ])
        Xs.append(X)
        ys.append(a[t])
        b0s.append(a[t - 12])
        b1s.append(a[t - 12] * np.exp(yoy))
        yrs.append(np.full(R, yr))
    X, y, b0, b1, yr = map(np.concatenate, (Xs, ys, b0s, b1s, yrs))
    tr, va = np.isin(yr, list(TRAIN_YEARS)), yr == VAL_YEAR

    rows = {"B0 작년 같은 달": b0[va], "B1 = B0 × exp(yoy)": b1[va]}
    beta = ridge_fit(with_intercept(X[tr]), np.log1p(y[tr]))
    rows["ridge (2020~2021 포함 + covid·covidLY)"] = np.expm1(with_intercept(X[va]) @ beta)
    tr_nc = tr & ~np.isin(yr, [2020, 2021])
    beta = ridge_fit(with_intercept(X[tr_nc]), np.log1p(y[tr_nc]))
    rows["(참고) ridge 2020~2021 학습 제외"] = np.expm1(with_intercept(X[va]) @ beta)
    return {"n_train": int(tr.sum()), "n_val": int(va.sum()),
            "rows": {k: [wape(y[va], p), medape(y[va], p)] for k, p in rows.items()}}


# ------------------------------------------------------------------ 일 단위
def daily(wide: pd.DataFrame, hol: set) -> dict:
    a = wide.values
    dates = wide.index
    T, R = a.shape
    h = np.array([d.strftime("%Y%m%d") in hol for d in dates], dtype=float)
    off = ((dates.dayofweek >= 5) | (h == 1)).astype(float)

    def sh(x, k):  # x[i-k], 범위 밖은 0
        out = np.zeros_like(x)
        if k >= 0:
            out[k:] = x[:len(x) - k]
        else:
            out[:k] = x[-k:]
        return out

    pre, post = sh(h, -1), sh(h, 1)                 # 다음날 공휴일 / 전날 공휴일
    lyH, offLY = sh(h, 364), sh(off, 364)
    longWk = off * sh(off, 1) * sh(off, -1)          # off(i) ∧ off(i-1) ∧ off(i+1)
    longLY = sh(longWk, 364)
    base = np.column_stack([h, pre, post, lyH, off, offLY, longWk, longLY, off - offLY, longWk - longLY])
    related = ((h + lyH + longWk + longLY) > 0)

    # 주말민감도: 2019년 휴무일 평균 log1p(y) − 평일 평균 log1p(y)
    y19 = dates.year == 2019
    ly1p = np.log1p(a)
    s = ly1p[y19 & (off == 1)].mean(0) - ly1p[y19 & (off == 0)].mean(0)

    # B1: 28일 창 Σ a[i-58..i-31] 와 그 364일 전
    cs = np.vstack([np.zeros((1, R)), np.cumsum(a, 0)])
    def win(i):  # Σ_{k=i-58}^{i-31} a[k]
        return cs[i - 30] - cs[i - 58]

    idx = np.arange(422, T)
    idx = idx[dates[idx].year <= VAL_YEAR]
    trend = np.log((win(idx) + 1) / (win(idx - 364) + 1))
    b0 = a[idx - 364]
    b1 = b0 * np.exp(trend)
    y = a[idx]

    n = len(idx)
    dow = np.zeros((n, 7)); dow[np.arange(n), dates[idx].dayofweek] = 1
    mon = np.zeros((n, 12)); mon[np.arange(n), dates[idx].month - 1] = 1
    B = base[idx]
    # 행 = (날짜, 시군구) 를 날짜 우선으로 펼침
    X = np.concatenate([
        np.repeat(B, R, axis=0),
        (B[:, None, :] * s[None, :, None]).reshape(n * R, -1),
        np.repeat(dow, R, axis=0), np.repeat(mon, R, axis=0),
    ], axis=1)
    yv, b0v, b1v = y.ravel(), b0.ravel(), b1.ravel()
    yr = np.repeat(dates[idx].year, R)
    rel = np.repeat(related[idx], R)
    target = np.log1p(yv) - np.log1p(b1v)
    tr, va = np.isin(yr, list(TRAIN_YEARS)), yr == VAL_YEAR

    beta = ridge_fit(with_intercept(X[tr]), target[tr])
    pred = np.expm1(np.log1p(b1v[va]) + with_intercept(X[va]) @ beta)

    yva, rva = yv[va], rel[va]
    res = {}
    for name, p in [("B0 작년 같은 요일(364일 전)", b0v[va]), ("B1 = B0 × exp(28일 증감)", b1v[va]),
                    ("B1 + 잔차 보정 ridge (39특징)", pred)]:
        res[name] = [wape(yva, p), wape(yva[rva], p[rva])]
    return {"n_train": int(tr.sum()), "n_val": int(va.sum()), "n_val_related": int(rva.sum()),
            "n_holidays_2018_2025": int(h[(dates.year >= 2018) & (dates.year <= 2025)].sum()), "rows": res}


def main():
    variant = sys.argv[1] if len(sys.argv) > 1 else "kasi"
    hol = {"nager": holidays_nager, "kasi": holidays_kasi}[variant]()
    wide = load_daily()
    m = monthly(wide)
    d = daily(wide, hol)
    lines = [f"== 공휴일 버전: {variant} | 시군구 {wide.shape[1]}개 ==",
             f"[월] 학습 {m['n_train']}행 / 검증 {m['n_val']}행",
             "| 모델 | WAPE | medAPE |", "|---|---|---|"]
    lines += [f"| {k} | {v[0]:.1%} | {v[1]:.1%} |" for k, v in m["rows"].items()]
    lines += [f"[일] 학습 {d['n_train']}행 / 검증 {d['n_val']}행 / 연휴 관련일 {d['n_val_related']}행 / 2018~2025 공휴일 {d['n_holidays_2018_2025']}일",
              "| 모델 | 전체 WAPE | 연휴 관련일 WAPE |", "|---|---|---|"]
    lines += [f"| {k} | {v[0]:.1%} | {v[1]:.1%} |" for k, v in d["rows"].items()]
    print("\n".join(lines))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"spec_{variant}.json").write_text(json.dumps({"monthly": m, "daily": d}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
