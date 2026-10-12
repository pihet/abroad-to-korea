"""월 단위 혼잡도: 서비스 Ridge(p1_spec 명세)와 같은 특징·분할로 트리 모델을 비교한다.

질문: 월 단위에서도 트리 모델(HistGradientBoosting · LightGBM)이 Ridge보다 나은가?
조건: p1_spec.monthly 와 같은 시군구·특징 19개·예측 시점 t-2. 트리 설정은 10-2 연휴 실험 값을 그대로 쓰고
      검증 결과를 보고 바꾸지 않았다. 트리에는 월 원-핫 12개 대신 월 범주 열 하나를 준다.
분할: 검증 2025 (학습 2019~2024, 서비스 수치 기준) / 검증 2024 (학습 2019~2023, 연도 안정성 확인)

실행:  .venv/bin/python src/forecast/p1_monthly_trees.py   (LightGBM 은 WSL 에서 libgomp1 필요, HANDOFF 10-2)
결과:  콘솔 표 (HANDOFF 15-48)
"""

import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p1_spec as S  # noqa: E402

TREE = dict(num_leaves=63, learning_rate=0.05, n_estimators=500, min_child_samples=100, verbose=-1, random_state=42)


def features(last_year=S.VAL_YEAR):
    """p1_spec.monthly 와 같은 행·특징 (목표 연도 last_year 까지). 트리용 행렬(월 범주 열)과 기준선도 함께 돌려준다."""
    A = S.load_daily().resample("MS").sum()
    a, months = A.values, A.index
    R = a.shape[1]
    Xs, ys, b0s, b1s, yrs = [], [], [], [], []
    for t in range(len(months)):
        o = t - 2
        if o - 14 < 0 or months[t].year > last_year:
            continue
        yr = months[t].year
        yoy = np.log((a[o] + a[o - 1] + a[o - 2] + 1) / (a[o - 12] + a[o - 13] + a[o - 14] + 1))
        a24 = a[t - 24] if t >= 24 else a[t - 12]
        onehot = np.zeros((R, 12))
        onehot[:, months[t].month - 1] = 1
        Xs.append(np.column_stack([
            np.log1p(a[t - 12]), np.log1p(a[o]), np.log1p(a[o - 1]), yoy, np.log1p(a24),
            np.full(R, int(yr in (2020, 2021))), np.full(R, int(yr - 1 in (2020, 2021))), onehot,
        ]))
        ys.append(a[t])
        b0s.append(a[t - 12])
        b1s.append(a[t - 12] * np.exp(yoy))
        yrs.append(np.full(R, yr))
    X, y, b0, b1, yr = map(np.concatenate, (Xs, ys, b0s, b1s, yrs))
    Xt = np.column_stack([X[:, :7], X[:, 7:19].argmax(1)])
    return X, Xt, y, b0, b1, yr


def compare(X, Xt, y, b0, b1, yr, train_years, val_year):
    tr, va = np.isin(yr, train_years), yr == val_year
    preds = {"B0 작년 같은 달": b0[va], "B1 작년 × 최근 3개월 증감": b1[va]}
    beta = S.ridge_fit(S.with_intercept(X[tr]), np.log1p(y[tr]))
    ridge = np.expm1(S.with_intercept(X[va]) @ beta)
    preds["Ridge (서비스)"] = ridge
    hgb = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=63, min_samples_leaf=100,
                                        categorical_features=[7], random_state=42).fit(Xt[tr], np.log1p(y[tr]))
    preds["HistGradientBoosting"] = np.expm1(hgb.predict(Xt[va]))
    lgbm = lgb.LGBMRegressor(**TREE).fit(Xt[tr], np.log1p(y[tr]), categorical_feature=[7])
    lg = np.expm1(lgbm.predict(Xt[va]))
    preds["LightGBM"] = lg
    resid = lgb.LGBMRegressor(**TREE).fit(Xt[tr], np.log1p(y[tr]) - np.log1p(b1[tr]), categorical_feature=[7])
    preds["LightGBM (B1 잔차 보정)"] = np.expm1(np.log1p(b1[va]) + resid.predict(Xt[va]))
    preds["Ridge + LightGBM 50:50"] = np.expm1((np.log1p(ridge) + np.log1p(lg)) / 2)
    return int(tr.sum()), int(va.sum()), {k: S.wape(y[va], p) for k, p in preds.items()}


def main():
    data = features()
    for label, train_years, val_year in [("검증 2025 (학습 2019~2024)", range(2019, 2025), 2025),
                                         ("검증 2024 (학습 2019~2023)", range(2019, 2024), 2024)]:
        n_tr, n_va, rows = compare(*data, list(train_years), val_year)
        print(f"\n{label}: 학습 {n_tr}행 / 검증 {n_va}행\n| 모델 | WAPE |\n|---|---|")
        for k, v in rows.items():
            print(f"| {k} | {v * 100:.2f}% |")


if __name__ == "__main__":
    main()
