"""P1 연휴 예측 개선 실험. 기준은 HANDOFF 10장 명세 모델(p1_spec.py) + 천문연 공휴일 CSV.

비교 조건은 명세와 같다: 시군구 258개, 30일 전 시점 예측, 연휴 관련일 = h ∨ lyH ∨ longWk ∨ longLY.
과적합 방지를 위해 두 분할에서 모두 확인한다.
    A: 학습 2019~2023 → 검증 2024
    B: 학습 2019~2024 → 검증 2025
2026 은 사용하지 않는다.

추가 특징
    - 명절 매핑: 설·추석 전후 ±5일은 '작년 같은 명절의 같은 날' 값을 참고한다 (364일 전은 엉뚱한 날이 된다)
    - 연휴 길이·연휴 안 위치 (올해와 364일 전)
    - 설·추석까지 남은 날 (부호 있음, ±7 로 자름)
    - 날 유형 배수 변화 (d-30 시점까지 365일로 추정)
    - 작년 앞뒤 주, 2년 전 값
    - 지역 특징: 주말민감도·연휴민감도·방문 수준 (2019년으로만 계산)

실행: .venv/bin/python src/forecast/p1_holiday.py
결과: 콘솔 표 + data/interim/p1/holiday_improve.json
"""

import csv
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

import p1_spec as S

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.mlops.tracking import log_runs

BIG = {"설날": "seol", "추석": "chuseok"}
SPLITS = {"A (학습 2019~2023 → 검증 2024)": (set(range(2019, 2024)), 2024),
          "B (학습 2019~2024 → 검증 2025)": (set(range(2019, 2025)), 2025)}
COVID_YEARS = (2020, 2021)
SEED = 42


def shift(x, k):
    """x[i-k], 범위 밖은 0 (명세의 sh 와 같다)."""
    out = np.zeros_like(x)
    if k >= 0:
        out[k:] = x[:len(x) - k]
    else:
        out[:k] = x[-k:]
    return out


def day_features(dates, hol_names):
    """날짜별 특징 (T × F) 과 명절 매핑 인덱스 (T,)."""
    T = len(dates)
    ymd = [d.strftime("%Y%m%d") for d in dates]
    h = np.array([s in hol_names for s in ymd], dtype=float)
    off = ((dates.dayofweek >= 5) | (h == 1)).astype(float)

    # 휴무 구간 길이와 구간 안 위치
    block_len = np.zeros(T)
    block_pos = np.zeros(T)
    i = 0
    while i < T:
        if off[i]:
            j = i
            while j < T and off[j]:
                j += 1
            block_len[i:j] = j - i
            block_pos[i:j] = np.arange(j - i)
            i = j
        else:
            i += 1

    # 설·추석: 해마다 첫 명절일(전날)을 기준점으로 잡는다
    kind = {k: np.array([hol_names.get(s) == name for s in ymd]) for name, k in BIG.items()}
    starts = {}  # (kind, year) -> 첫 명절일 인덱스
    for k, mask in kind.items():
        for t in np.where(mask)[0]:
            starts.setdefault((k, dates[t].year), t)
    dist = np.full(T, 99.0)          # 가장 가까운 명절 기준점까지 부호 있는 거리
    mapped = np.full(T, -1)          # 작년 같은 명절의 같은 날 인덱스
    for (k, yr), t0 in starts.items():
        prev = starts.get((k, yr - 1))
        for off_d in range(-5, 6):
            t = t0 + off_d
            if 0 <= t < T and abs(off_d) < abs(dist[t]):
                dist[t] = off_d
                if prev is not None and 0 <= prev + off_d < T:
                    mapped[t] = prev + off_d
    near_big = (np.abs(dist) <= 5).astype(float)
    dist_c = np.clip(dist, -7, 7)
    big_day = (kind["seol"] | kind["chuseok"]).astype(float)

    # [긴 연휴] 길이가 달라도 통하는 상대 표현. 긴 연휴 = 3일 이상 이어진 휴무
    rel_pos = np.full(T, -1.0)     # 연휴 안 진행률 0~1
    days_left = np.full(T, -1.0)   # 연휴 남은 날
    pre_dist = np.zeros(T)         # 다음 긴 연휴 시작까지 1~3일 (해당 없으면 0)
    pre_len = np.zeros(T)          # 다가오는 긴 연휴 길이
    post_dist = np.zeros(T)        # 긴 연휴가 끝난 뒤 1~3일
    post_len = np.zeros(T)         # 막 끝난 긴 연휴 길이
    t = 0
    while t < T:
        if block_len[t] >= 3 and block_pos[t] == 0:
            L = int(block_len[t])
            rel_pos[t:t + L] = np.arange(L) / (L - 1)
            days_left[t:t + L] = np.arange(L)[::-1]
            for k in range(1, 4):
                if t - k >= 0 and not off[t - k]:
                    pre_dist[t - k], pre_len[t - k] = k, L
                if t + L - 1 + k < T and not off[t + L - 1 + k]:
                    post_dist[t + L - 1 + k], post_len[t + L - 1 + k] = k, L
            t += L
        else:
            t += 1
    # 위치 구간: 0 평일 / 1 연휴 전날 / 2 연휴 첫날 / 3 연휴 중간 / 4 연휴 마지막날 / 5 연휴 다음날 / 6 짧은 휴무(주말)
    bucket = np.where(off == 1, 6, 0)
    bucket = np.where(pre_dist == 1, 1, bucket)
    bucket = np.where(post_dist == 1, 5, bucket)
    bucket = np.where(rel_pos > 0, 3, bucket)
    bucket = np.where(rel_pos == 0, 2, bucket)
    bucket = np.where(rel_pos == 1, 4, bucket)

    F = {
        "h": h, "off": off, "block_len": block_len, "block_pos": block_pos,
        "big_day": big_day, "near_big": near_big, "dist_big": dist_c,
        "len_c": np.minimum(block_len, 9), "rel_pos": rel_pos, "days_left": days_left,
        "pre_dist": pre_dist, "pre_len": pre_len, "post_dist": post_dist, "post_len": post_len,
        "bucket": bucket.astype(float),
    }
    for k in ["h", "off", "block_len", "block_pos", "big_day", "near_big", "dist_big",
              "rel_pos", "days_left", "pre_dist", "pre_len", "post_dist", "post_len", "bucket"]:
        F["ly_" + k] = shift(F[k], 364)
    F["dow"] = dates.dayofweek.values.astype(float)
    F["month"] = dates.month.values.astype(float)
    return F, mapped


def build(wide, hol_names):
    a = wide.values
    dates = wide.index
    T, R = a.shape
    F, mapped = day_features(dates, hol_names)

    # 명세 그대로의 base 10 과 연휴 관련일 정의
    h, off = F["h"], F["off"]
    pre, post = shift(h, -1), shift(h, 1)
    lyH, offLY = shift(h, 364), shift(off, 364)
    longWk = off * shift(off, 1) * shift(off, -1)
    longLY = shift(longWk, 364)
    base = np.column_stack([h, pre, post, lyH, off, offLY, longWk, longLY, off - offLY, longWk - longLY])
    related = (h + lyH + longWk + longLY) > 0

    l1p = np.log1p(a)
    y19 = dates.year == 2019
    s = l1p[y19 & (off == 1)].mean(0) - l1p[y19 & (off == 0)].mean(0)            # 주말민감도 (명세)
    s_long = l1p[y19 & (F["block_len"] >= 3)].mean(0) - l1p[y19 & (off == 0)].mean(0)  # 연휴민감도
    lvl = l1p[y19].mean(0)

    cs = np.vstack([np.zeros((1, R)), np.cumsum(a, 0)])
    idx = np.arange(422, T)  # 명세와 같은 시작점 (trend 창이 데이터 범위 안)
    idx = idx[dates[idx].year <= 2025]
    win = lambda i: cs[i - 30] - cs[i - 58]
    trend = np.log((win(idx) + 1) / (win(idx - 364) + 1))
    b0 = a[idx - 364]
    b1 = b0 * np.exp(trend)

    # 명절 매핑 기준선: 명절 ±5일은 작년 같은 명절의 같은 날 × 증감
    m = mapped[idx]
    b0_hol = np.where((m >= 0)[:, None], a[np.maximum(m, 0)], b0)
    b1_hol = b0_hol * np.exp(trend)

    # 날 유형 배수 변화: 유형 = 0 평일, 1 짧은 휴무, 2 3일 이상 연휴
    typ = np.where(F["block_len"] >= 3, 2, np.where(off == 1, 1, 0))
    # 계산량을 줄이기 위해 월 1회만 갱신 (같은 달 안에서는 같은 배수)
    mult = {}
    for k in range(3):
        x = np.where((typ == k)[:, None], l1p, np.nan)
        out = np.full((T, R), np.nan)
        last_m = None
        for t in idx:
            key = (dates[t].year, dates[t].month)
            if key != last_m:
                w = x[max(0, t - 30 - 365):t - 30]
                cur = np.nanmean(w, 0)
                last_m = key
            out[t] = cur
        mult[k] = out
    lm = np.stack([mult[k] for k in range(3)])
    dmult = lm[typ[idx], idx] - lm[typ[idx - 364], idx]

    n = len(idx)
    rows = lambda v: np.repeat(v[idx], R)
    X = {
        **{k: rows(v) for k, v in F.items()},
        "s": np.tile(s, n), "s_long": np.tile(s_long, n), "lvl": np.tile(lvl, n),
        "trend": trend.ravel(),
        "dmult": dmult.ravel(),
        "l_hol": (np.log1p(b0_hol) - np.log1p(b0)).ravel(),
        "l_wm1": (l1p[idx - 371] - np.log1p(b0)).ravel(),
        "l_wp1": (l1p[idx - 357] - np.log1p(b0)).ravel(),
        "l_2y": np.where((idx >= 728)[:, None], l1p[np.maximum(idx - 728, 0)] - np.log1p(b0), np.nan).ravel(),  # 2년 전이 없으면 결측
        "covid": np.repeat(np.isin(dates[idx].year, COVID_YEARS).astype(float), R),
    }
    B = base[idx]
    spec_X = np.concatenate([
        np.repeat(B, R, 0), (B[:, None, :] * s[None, :, None]).reshape(n * R, -1),
        np.repeat(np.eye(7)[dates[idx].dayofweek], R, 0), np.repeat(np.eye(12)[dates[idx].month - 1], R, 0),
    ], 1)
    near_big_rows = rows(F["near_big"]) == 1
    long4 = (F["block_len"] >= 4) | ((F["pre_dist"] == 1) & (F["pre_len"] >= 4)) | ((F["post_dist"] == 1) & (F["post_len"] >= 4))
    return {
        "y": a[idx].ravel(), "b0": b0.ravel(), "b1": b1.ravel(), "b1_hol": b1_hol.ravel(),
        "year": np.repeat(dates[idx].year, R), "n_regions": R, "related": np.repeat(related[idx], R), "near_big": near_big_rows,
        "long4": np.repeat(long4[idx], R), "X": X, "spec_X": spec_X,
    }


def evaluate(D, train_years, val_year):
    yr = D["year"]
    tr, va = np.isin(yr, list(train_years)), yr == val_year
    y, rel, big, lg = D["y"][va], D["related"][va], D["near_big"][va], D["long4"][va]
    preds = {"B0": D["b0"][va], "B1": D["b1"][va], "B1_hol (명절 매핑 기준선, 학습 없음)": D["b1_hol"][va]}

    # 명세 ridge (같은 행 집합에서 다시 학습)
    tgt = np.log1p(D["y"]) - np.log1p(D["b1"])
    Xs = S.with_intercept(D["spec_X"])
    beta = S.ridge_fit(Xs[tr], tgt[tr])
    preds["명세 ridge (B1 잔차)"] = np.expm1(np.log1p(D["b1"][va]) + Xs[va] @ beta)

    # 명세 ridge, 기준선만 B1_hol 로
    tgt_h = np.log1p(D["y"]) - np.log1p(D["b1_hol"])
    beta = S.ridge_fit(Xs[tr], tgt_h[tr])
    preds["명세 ridge (B1_hol 잔차)"] = np.expm1(np.log1p(D["b1_hol"][va]) + Xs[va] @ beta)

    # 부스팅: B1_hol 잔차, 전체 특징
    names = list(D["X"])
    Xh = np.column_stack([D["X"][k] for k in names])
    cat = [names.index("dow"), names.index("month")]

    # 시군구별 연휴 편향: 학습 행에서 '연휴 관련일 / 설·추석 ±5일'의 평균 잔차 (분할마다 학습 행으로만 계산)
    R = D["n_regions"]
    reg = np.tile(np.arange(R), len(yr) // R)
    def region_bias(mask):
        m = tr & mask & ~np.isin(yr, COVID_YEARS)
        sums = np.bincount(reg[m], weights=tgt_h[m], minlength=R)
        cnts = np.bincount(reg[m], minlength=R)
        return (sums / np.maximum(cnts, 1))[reg]
    Xh2 = np.column_stack([Xh, region_bias(D["related"]), region_bias(D["near_big"]), region_bias(np.ones_like(tr))])
    # [긴 연휴] 시군구 연휴 프로필: (시군구, 위치 구간)별 학습 행 평균 잔차 → 오늘 구간·작년 같은 요일 구간 값과 차이
    bk_now, bk_ly = D["X"]["bucket"].astype(int), D["X"]["ly_bucket"].astype(int)
    m = tr & ~np.isin(yr, COVID_YEARS)
    key = reg * 7 + bk_now
    enc = np.bincount(key[m], weights=tgt_h[m], minlength=R * 7) / np.maximum(np.bincount(key[m], minlength=R * 7), 1)
    prof_now, prof_ly = enc[reg * 7 + bk_now], enc[reg * 7 + bk_ly]
    Xh3 = np.column_stack([Xh2, prof_now, prof_ly, prof_now - prof_ly])
    new_cols = ["len_c", "rel_pos", "days_left", "pre_dist", "pre_len", "post_dist", "post_len", "bucket"]
    new_cols += ["ly_" + c for c in new_cols if c != "len_c"]
    keep = [i for i, k in enumerate(names) if k not in new_cols]   # 긴 연휴 특징을 뺀 기존 특징셋 (비교용)
    Xh2_old = np.column_stack([Xh[:, keep], Xh2[:, Xh.shape[1]:]])
    cat_old = [keep.index(c) for c in cat]

    fit_sec = {}
    for label, Xm, cats in [("lgbm 기존 특징 (10-2)", Xh2_old, cat_old), ("lgbm + 긴 연휴 특징·프로필", Xh3, cat)]:
        t0 = time.time()
        mdl = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=63, min_child_samples=100,
                                random_state=SEED, verbose=-1)
        mdl.fit(Xm[tr], tgt_h[tr], categorical_feature=cats)
        fit_sec[label] = time.time() - t0
        preds[label] = np.expm1(np.log1p(D["b1_hol"][va]) + mdl.predict(Xm[va]))
        r_ = preds["명세 ridge (B1 잔차)"]
        preds[f"앙상블: 명세 ridge + {label} 50:50"] = np.expm1((np.log1p(r_) + np.log1p(preds[label])) / 2)
    print("  학습 시간: " + ", ".join(f"{k} {v:.0f}초" for k, v in fit_sec.items()))
    return {k: {"전체": S.wape(y, p), "연휴 관련일": S.wape(y[rel], p[rel]), "설·추석 ±5일": S.wape(y[big], p[big]),
                "긴 연휴 4일+ 전후": S.wape(y[lg], p[lg])}
            for k, p in preds.items()}, int(va.sum()), int(rel.sum()), int(big.sum()), int(lg.sum())


def main():
    hol_names = {r["date"]: r["name"] for r in csv.DictReader(open(S.KASI_CSV, encoding="utf-8")) if r["is_holiday"] == "Y"}
    wide = S.load_daily()
    D = build(wide, hol_names)
    out = {}
    for label, (ty, vy) in SPLITS.items():
        res, n, nr, nb, nl = evaluate(D, ty, vy)
        out[label] = res
        print(f"\n== {label} | 검증 {n}행, 연휴 관련일 {nr}행, 설·추석 ±5일 {nb}행, 긴 연휴 4일+ 전후 {nl}행 ==")
        print("| 모델 | 전체 | 연휴 관련일 | 설·추석 ±5일 | 긴 연휴 4일+ 전후 |\n|---|---|---|---|---|")
        for k, v in res.items():
            print(f"| {k} | {v['전체']:.1%} | {v['연휴 관련일']:.1%} | {v['설·추석 ±5일']:.1%} | {v['긴 연휴 4일+ 전후']:.1%} |")
    S.OUT.mkdir(parents=True, exist_ok=True)
    (S.OUT / "holiday_improve.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    runs = []
    for split, models in out.items():
        train_years, val_year = SPLITS[split]
        for index, (model, metrics) in enumerate(models.items(), 1):
            runs.append({
                "name": f"split-{val_year}-{index}",
                "params": {
                    "split": split,
                    "train_years": sorted(train_years),
                    "validation_year": val_year,
                    "model": model,
                    "seed": SEED,
                    "regions": D["n_regions"],
                },
                "metrics": {
                    "wape": metrics["전체"],
                    "holiday_wape": metrics["연휴 관련일"],
                    "seollal_chuseok_wape": metrics["설·추석 ±5일"],
                    "long_holiday_wape": metrics["긴 연휴 4일+ 전후"],
                },
            })
    log_runs("congestion-holiday-experiments", runs, out)


if __name__ == "__main__":
    main()
