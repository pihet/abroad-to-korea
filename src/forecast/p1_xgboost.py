"""월 단위 혼잡도: XGBoost 를 p1_monthly_trees 와 같은 특징·분할·트리 설정으로 추가 비교한다.

질문: 다른 부스팅 구현(XGBoost)도 Ridge 보다 나은가? (발표 질문 대비, 2026-10-15 추가)
설정: LightGBM 과 같은 값을 XGBoost 이름으로 옮겼다 (잎 63개 · 학습률 0.05 · 트리 500개 · 잎당 최소 100).
      제곱 오차에서 min_child_weight 는 잎당 최소 행 수와 같다. 월은 범주 열 하나.
분할: 검증 2025 · 검증 2024 · 2026 최종 테스트. 서비스 모델은 바꾸지 않는다 (비교용 추가 기록).

실행:  .venv/bin/python src/forecast/p1_xgboost.py
"""

import numpy as np
import pandas as pd
import xgboost as xgb

import p1_monthly_trees as T
import p1_spec as S

XGB = dict(tree_method="hist", grow_policy="lossguide", max_leaves=63, max_depth=0, learning_rate=0.05,
           n_estimators=500, min_child_weight=100, enable_categorical=True, random_state=42)


def frame(Xt):
    df = pd.DataFrame(Xt, columns=[f"f{i}" for i in range(Xt.shape[1])])
    df["f7"] = df["f7"].astype(int).astype("category")
    return df


def wape_xgb(Xt, y, yr, train_years, eval_year):
    tr, ev = np.isin(yr, train_years), yr == eval_year
    df = frame(Xt)
    model = xgb.XGBRegressor(**XGB).fit(df[tr], np.log1p(y[tr]))
    return S.wape(y[ev], np.expm1(model.predict(df[ev])))


def main():
    runs = {}
    _, Xt, y, _, _, yr = T.features()
    for train, year in [(range(2019, 2025), 2025), (range(2019, 2024), 2024)]:
        runs[("congestion-monthly-models", f"val{year}-XGBoost", year)] = wape_xgb(Xt, y, yr, list(train), year)
    _, Xt, y, _, _, yr = T.features(last_year=2026)
    runs[("congestion-test-2026", "test2026-XGBoost", 2026)] = wape_xgb(Xt, y, yr, list(range(2019, 2026)), 2026)

    print("| 분할 | XGBoost WAPE |\n|---|---|")
    for (_, name, _), v in runs.items():
        print(f"| {name} | {v * 100:.2f}% |")
    for exp in ("congestion-monthly-models", "congestion-test-2026"):
        S.log_runs(exp, [{"name": name, "metrics": {"wape": v},
                          "params": {"model": "XGBoost", "eval_year": year}}
                         for (e, name, year), v in runs.items() if e == exp], {})


if __name__ == "__main__":
    main()
