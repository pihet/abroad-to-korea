"""P1 혼잡도 예측 재현: 시군구별 외지인 방문자 수를 월·일 단위로 예측한다.

데이터: data/raw/datalab/locgoRegnVisitrDDList/*.json.gz (src/collect/datalab_visitors.py 로 수집)
분할:   학습 2019~2024 / 검증 2025. 2026 은 최종 테스트용으로 남겨 두고 여기서는 쓰지 않는다.

월 단위: 대상 월 t 를 t-2 월 말 시점 정보로 예측
    B0 = 작년 같은 달
    B1 = B0 × (최근 3개월 합 / 그 1년 전 3개월 합)
    ridge = log(y) 를 B0·최근값·증감·월·코로나 플래그로 회귀 (HANDOFF 7장 P1 재현)
    hgb   = log(y / B1) 잔차를 그래디언트 부스팅으로 보정 (개선 시도)
    [개선] B1_cal = 지난 12개월의 날 유형별 방문 배수로 대상 월의 날짜 구성을 반영한 기준선 (학습 없음)

일 단위: 대상일 d 를 d-30 일 시점 정보로 예측
    B0 = 364일 전(같은 요일)
    B1 = B0 × (d-30 까지 최근 28일 합 / 그 364일 전 28일 합)
    B1+보정 = log(y / B1) 잔차를 달력 특징(공휴일·연휴·요일·월, 작년 같은 날의 달력 포함)과
             지역 주말민감도 상호작용으로 보정 (ridge 재현, hgb 개선 시도)
    [개선] hgb + 날 유형 배수 변화(올해 그날 vs 작년 같은 요일), 작년 앞뒤 주, 2년 전 값

실행:  .venv/bin/python src/forecast/p1_congestion.py
결과:  콘솔 표 + data/interim/p1/results.json
"""

import gzip
import json
from pathlib import Path

import holidays
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/datalab/locgoRegnVisitrDDList"
OUT = ROOT / "data/interim/p1"
TRAIN_YEARS = range(2019, 2025)
VAL_YEAR = 2025
LAST_DAY = "2025-12-31"  # 2026 은 사용하지 않는다
COVID = ("2020-02-01", "2022-12-31")
SEED = 42


# ------------------------------------------------------------------ 데이터
def load_daily() -> pd.DataFrame:
    """외지인(touDivCd=2) 일별 방문자 수, 행=날짜, 열=시군구코드.

    2026-07 전남·광주 신코드(12xxx)는 이름이 같은 기존 코드(46xxx, 29xxx)로 합친다.
    전 기간(2018-01-01 ~ 2025-12-31) 결측 없는 시군구만 남긴다.
    """
    rows = []
    for p in sorted(RAW.glob("*.json.gz")):
        items = json.load(gzip.open(p, "rt", encoding="utf-8"))["response"]["body"]["items"]["item"]
        rows += [i for i in items if i["touDivCd"] == "2"]
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
    wide = df.pivot_table(index="date", columns="code", values="y", aggfunc="sum")
    wide = wide.loc[:LAST_DAY]
    wide = wide.loc[:, wide.notna().all()]
    names = df.drop_duplicates("code").set_index("code").signguNm
    return wide, names


def wape(y, p):
    return float(np.abs(y - p).sum() / y.sum())


def medape(y, p):
    return float(np.median(np.abs(y - p) / y))


# ------------------------------------------------------------------ 월 단위
def monthly(wide: pd.DataFrame) -> dict:
    M = wide.resample("MS").sum()
    L = np.log(M.clip(lower=1))
    recs = []
    for i, t in enumerate(M.index):
        if i < 16:
            continue  # t-16 까지 필요
        b0 = M.iloc[i - 12]
        recent = M.iloc[i - 4:i - 1].sum()          # t-4..t-2
        recent_ly = M.iloc[i - 16:i - 13].sum()     # 그 1년 전
        ratio = recent / recent_ly
        recs.append(pd.DataFrame({
            "t": t, "code": M.columns, "y": M.iloc[i].values, "b0": b0.values, "b1": (b0 * ratio).values,
            "l_b0": L.iloc[i - 12].values, "l_recent": L.iloc[i - 2].values, "l_ratio": np.log(ratio).values,
            "month": t.month, "covid": int(COVID[0] <= str(t.date()) <= COVID[1]),
            "covid_b0": int(COVID[0] <= str(M.index[i - 12].date()) <= COVID[1]),
        }))
    d = pd.concat(recs, ignore_index=True)
    d = d[d.t.dt.year.isin(list(TRAIN_YEARS) + [VAL_YEAR])]
    tr, va = d[d.t.dt.year.isin(TRAIN_YEARS)], d[d.t.dt.year == VAL_YEAR]

    def X_ridge(x):
        X = x[["l_b0", "l_recent", "l_ratio", "covid", "covid_b0"]].copy()
        for m in range(2, 13):
            X[f"m{m}"] = (x.month == m).astype(int)
        return X

    res = {}
    for name, p in [("B0 작년 같은 달", va.b0), ("B1 B0×최근 3개월 증감", va.b1)]:
        res[name] = (wape(va.y, p), medape(va.y, p))
    r = Ridge(alpha=1.0).fit(X_ridge(tr), np.log(tr.y))
    p = np.exp(r.predict(X_ridge(va)))
    res["ridge (작년값·최근값·증감·월·코로나)"] = (wape(va.y, p), medape(va.y, p))
    tr_nc = tr[(tr.covid == 0) & (tr.covid_b0 == 0)]
    r2 = Ridge(alpha=1.0).fit(X_ridge(tr_nc), np.log(tr_nc.y))
    p = np.exp(r2.predict(X_ridge(va)))
    res["ridge (코로나 기간 학습 제외)"] = (wape(va.y, p), medape(va.y, p))

    # 개선 시도: B1 잔차를 부스팅으로 보정
    feats = ["l_b0", "l_recent", "l_ratio", "month", "covid", "covid_b0"]
    h = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=SEED)
    h.fit(tr[feats], np.log(tr.y / tr.b1))
    p = va.b1 * np.exp(h.predict(va[feats]))
    res["hgb B1 잔차 보정"] = (wape(va.y, p), medape(va.y, p))

    c = monthly_calendar_baseline(wide, VAL_YEAR)
    res["[개선] B1_cal 달력 반영 기준선 (학습 없음)"] = (wape(c.y, c.b1_cal), medape(c.y, c.b1_cal))
    res["[개선] B1_cal + 증감도 달력 보정"] = (wape(c.y, c.b1_cal_ratio_cal), medape(c.y, c.b1_cal_ratio_cal))
    return {"n_val": len(va), "rows": res}


# ------------------------------------------------------------------ 일 단위 달력
def calendar(start="2017-01-01", end=LAST_DAY) -> pd.DataFrame:
    """날짜별 달력 특징. off = 주말 또는 공휴일. 연휴 = off 가 3일 이상 이어진 구간."""
    days = pd.date_range(start, end)
    kr = holidays.KR(years=range(days[0].year, days[-1].year + 1))
    c = pd.DataFrame(index=days)
    c["dow"] = days.dayofweek
    c["month"] = days.month
    c["holiday"] = [int(d in kr) for d in days]
    c["off"] = ((c.dow >= 5) | (c.holiday == 1)).astype(int)
    # off 구간 길이와 구간 내 위치
    block = (c.off != c.off.shift()).cumsum()
    c["block_len"] = c.groupby(block).off.transform("size") * c.off
    c["block_pos"] = c.groupby(block).cumcount() * c.off
    c["long_off"] = (c.block_len >= 3).astype(int)
    c["before_long"] = c.long_off.shift(-1, fill_value=0) * (1 - c.long_off)  # 연휴 전날
    c["after_long"] = c.long_off.shift(1, fill_value=0) * (1 - c.long_off)    # 연휴 다음날
    c["bridge"] = ((c.off == 0) & (c.off.shift(1) == 1) & (c.off.shift(-1) == 1)).astype(int)  # 징검다리
    c["holiday_related"] = ((c.holiday == 1) | (c.long_off == 1) | (c.before_long == 1) | (c.after_long == 1)).astype(int)
    return c


CAL_FEATS = ["holiday", "off", "block_len", "block_pos", "long_off", "before_long", "after_long", "bridge"]


def day_type(cal: pd.DataFrame) -> pd.Series:
    """0 평일 / 1 일반 주말(짧은 휴무) / 2 연휴(3일 이상 휴무) / 3 연휴 전날·다음날·징검다리."""
    return pd.Series(np.where(cal.long_off == 1, 2, np.where(cal.off == 1, 1,
                     np.where((cal.before_long + cal.after_long + cal.bridge) > 0, 3, 0))), index=cal.index)


def monthly_calendar_baseline(wide: pd.DataFrame, year: int) -> pd.DataFrame:
    """[개선] 월 단위 달력 반영 기준선 (학습 없음).

    지난 12개월(t-13..t-2)에서 시군구별 '평일 대비 날 유형별 방문 배수'를 구하고,
    작년 같은 달 평일 평균 × 대상 월의 날 유형 구성으로 기대값을 만든다.
    설·추석이 다른 달로 옮겨 가는 해에 B0(작년 같은 달)가 틀리는 문제를 고친다.
    """
    cal = calendar().loc[wide.index]
    typ = day_type(cal)
    M = wide.resample("MS").sum()
    months = M.index

    def days(a, b):
        return (wide.index >= months[a]) & (wide.index < months[b] + pd.offsets.MonthBegin(1))

    out = []
    for i, t in enumerate(months):
        if t.year != year:
            continue
        w = days(i - 13, i - 2)
        yw, tw = wide[w], typ[w]
        mult = [yw[tw == k].mean() / yw[tw == 0].mean() for k in range(4)]

        def expected(a, b):  # 기간 a..b 의 날 유형 구성에 따른 기대 배수 합
            m_ = days(a, b)
            return sum((typ[m_] == k).sum() * mult[k] for k in range(4))

        ly = days(i - 12, i - 12)
        b0_cal = wide[ly][typ[ly] == 0].mean() * expected(i, i)
        ratio = M.iloc[i - 4:i - 1].sum() / M.iloc[i - 16:i - 13].sum()
        ratio_cal = (M.iloc[i - 4:i - 1].sum() / expected(i - 4, i - 2)) / (M.iloc[i - 16:i - 13].sum() / expected(i - 16, i - 14))
        out.append(pd.DataFrame({"t": t, "code": wide.columns, "y": M.iloc[i].values,
                                 "b1_cal": (b0_cal * ratio).values, "b1_cal_ratio_cal": (b0_cal * ratio_cal).values}))
    return pd.concat(out, ignore_index=True)


def daily(wide: pd.DataFrame) -> dict:
    cal = calendar()
    Y = wide
    idx = Y.index
    b0 = Y.shift(364)
    win = Y.rolling(28).sum()
    ratio = win.shift(30) / win.shift(30 + 364)  # d-30 까지 28일 합 / 그 364일 전
    b1 = b0 * ratio

    # 지역 주말민감도: 학습 기간(코로나 제외) 주말 평균 / 평일 평균 (로그)
    trn = Y[(idx.year.isin(TRAIN_YEARS)) & ~((idx >= COVID[0]) & (idx <= COVID[1]))]
    is_off = cal.loc[trn.index, "off"].values == 1
    sens = np.log(trn[is_off].mean() / trn[~is_off].mean())
    lvl = np.log(trn.mean())

    # [개선] 날 유형 배수: d-30 까지 365일 창에서 시군구별 '유형 k 평균 / 평일 평균'
    typ = day_type(cal.loc[idx])
    log_mult = np.stack([
        np.log(Y.where(np.broadcast_to((typ == k).values[:, None], Y.shape)).rolling(365, min_periods=30).mean().shift(30)
               / Y.where(np.broadcast_to((typ == 0).values[:, None], Y.shape)).rolling(365, min_periods=30).mean().shift(30)).values
        for k in range(4)])
    cur = typ.values
    ly = typ.shift(364).fillna(0).astype(int).values
    t_ix = np.arange(len(idx))
    dmult = log_mult[cur, t_ix] - log_mult[ly, t_ix]  # 올해 그날 유형과 작년 같은 요일 유형의 배수 차이

    long = pd.DataFrame({
        "date": np.repeat(idx, Y.shape[1]), "code": np.tile(Y.columns, len(idx)),
        "y": Y.values.ravel(), "b0": b0.values.ravel(), "b1": b1.values.ravel(),
        "dmult": dmult.ravel(),
        "l_wm1": np.log(Y.shift(371) / b0).values.ravel(),   # 작년 1주 전
        "l_wp1": np.log(Y.shift(357) / b0).values.ravel(),   # 작년 1주 후
        "l_2y": np.log(Y.shift(728) / b0).values.ravel(),    # 2년 전
        "typ": np.repeat(cur, Y.shape[1]), "ly_typ": np.repeat(ly, Y.shape[1]),
    })
    long = long[long.date.dt.year.isin(list(TRAIN_YEARS) + [VAL_YEAR])].dropna(subset=["y", "b0", "b1"])
    c_now = cal.loc[long.date].reset_index(drop=True)
    c_ly = cal.loc[long.date - pd.Timedelta(days=364)].reset_index(drop=True)
    long = long.reset_index(drop=True)
    for f in CAL_FEATS:
        long[f] = c_now[f].values
        long[f"ly_{f}"] = c_ly[f].values  # B0(작년 같은 요일)가 어떤 날이었는지
    long["dow"] = c_now.dow.values
    long["month"] = c_now.month.values
    long["holiday_related"] = c_now.holiday_related.values
    long["sens"] = long.code.map(sens).values
    long["lvl"] = long.code.map(lvl).values
    long["covid"] = ((long.date >= COVID[0]) & (long.date <= COVID[1])).astype(int)
    long["l_ratio"] = np.log(long.b1 / long.b0)
    long = long.replace([np.inf, -np.inf], np.nan)
    long = long[(long.y > 0) & (long.b1 > 0)]
    long["resid"] = np.log(long.y / long.b1)

    tr = long[long.date.dt.year.isin(TRAIN_YEARS)]
    va = long[long.date.dt.year == VAL_YEAR]
    hol = va.holiday_related == 1

    def score(p):
        return wape(va.y, p), wape(va.y[hol], p[hol])

    res = {"B0 작년 같은 요일(364일 전)": score(va.b0), "B1 B0×최근 증감": score(va.b1)}

    # ridge 보정 (재현): 달력 특징 + 지역 주말민감도 상호작용
    def X_ridge(x):
        X = pd.DataFrame(index=x.index)
        for f in CAL_FEATS:
            X[f] = x[f]
            X[f"ly_{f}"] = x[f"ly_{f}"]
            X[f"sens_{f}"] = x[f] * x.sens
            X[f"sens_ly_{f}"] = x[f"ly_{f}"] * x.sens
        for k in range(1, 7):
            X[f"dow{k}"] = (x.dow == k).astype(int)
        for m in range(2, 13):
            X[f"m{m}"] = (x.month == m).astype(int)
        X["covid"] = x.covid
        return X

    w_tr = tr.covid == 0  # 코로나 기간은 보정 패턴이 달라 학습에서 제외
    r = Ridge(alpha=1.0).fit(X_ridge(tr[w_tr]), tr.resid[w_tr])
    res["B1 + 보정 (ridge)"] = score(va.b1 * np.exp(r.predict(X_ridge(va))))

    # 개선 시도: 같은 잔차를 부스팅으로 (상호작용을 자동 학습)
    feats = CAL_FEATS + [f"ly_{f}" for f in CAL_FEATS] + ["dow", "month", "sens", "lvl", "l_ratio"]
    h = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=63,
                                      categorical_features=[feats.index("dow"), feats.index("month")],
                                      random_state=SEED)
    h.fit(tr.loc[w_tr, feats], tr.resid[w_tr])
    res["B1 + 보정 (hgb)"] = score(va.b1 * np.exp(h.predict(va[feats])))

    feats2 = feats + ["dmult", "l_wm1", "l_wp1", "l_2y", "typ", "ly_typ"]
    h2 = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=63,
                                       categorical_features=[feats2.index("dow"), feats2.index("month")],
                                       random_state=SEED)
    h2.fit(tr.loc[w_tr, feats2], tr.resid[w_tr])
    res["[개선] B1 + 보정 (hgb + 유형배수·작년 앞뒤 주·2년 전)"] = score(va.b1 * np.exp(h2.predict(va[feats2])))
    return {"n_val": int(len(va)), "n_val_holiday": int(hol.sum()), "rows": res}


def main():
    wide, names = load_daily()
    print(f"시군구 {wide.shape[1]}개, {wide.index[0].date()} ~ {wide.index[-1].date()}")
    m = monthly(wide)
    print(f"\n[월 단위] 검증 {m['n_val']}행 (2025)")
    print("| 모델 | WAPE | medAPE |\n|---|---|---|")
    for k, (a, b) in m["rows"].items():
        print(f"| {k} | {a:.1%} | {b:.1%} |")
    d = daily(wide)
    print(f"\n[일 단위] 검증 {d['n_val']}행, 연휴 관련일 {d['n_val_holiday']}행 (2025)")
    print("| 모델 | 전체 WAPE | 연휴 관련일 WAPE |\n|---|---|---|")
    for k, (a, b) in d["rows"].items():
        print(f"| {k} | {a:.1%} | {b:.1%} |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({"monthly": m, "daily": d}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
