"""혼잡도 월 단위 최종 테스트: 2026-01~08을 한 번만 평가한다 (HANDOFF 15-49).

학습 2019~2025, 테스트 2026 (예측 시점 t-2). 모델·특징·설정은 검증(2025)에서 정한 그대로 바꾸지 않는다.
비교: B0 · B1 · 서비스 Ridge · 트리 모델 (p1_monthly_trees 와 같은 설정).
시군구: p1_spec.load_daily 의 "2018-01~2026-08 결측 없는 곳" 그대로. 인천 개편으로 2026-07부터 바뀐 구는
        결측이 생겨 자동으로 빠진다. 전남·광주 신코드는 같은 이름의 구코드에 합친다.

실행:  .venv/bin/python src/forecast/p1_test_2026.py
"""

import numpy as np

import p1_monthly_trees as T
import p1_spec as S


def main():
    X, Xt, y, b0, b1, yr = T.features(last_year=2026)
    n_tr, n_te, rows = T.compare(X, Xt, y, b0, b1, yr, list(range(2019, 2026)), 2026)
    regions = len(S.load_daily().columns)
    print(f"시군구 {regions}곳 · 학습 2019~2025 {n_tr}행 / 테스트 2026-01~08 {n_te}행\n| 모델 | WAPE |\n|---|---|")
    for k, v in rows.items():
        print(f"| {k} | {v * 100:.2f}% |")

    # 월별로 보면 어디서 틀리는지 보인다 (B1 과 서비스 Ridge 만)
    tr, te = np.isin(yr, list(range(2019, 2026))), yr == 2026
    beta = S.ridge_fit(S.with_intercept(X[tr]), np.log1p(y[tr]))
    ridge = np.expm1(S.with_intercept(X[te]) @ beta)
    month = X[te, 7:19].argmax(1) + 1
    print("\n| 2026 월 | B1 | Ridge |\n|---|---|---|")
    for m in sorted(set(month)):
        k = month == m
        print(f"| {m}월 | {S.wape(y[te][k], b1[te][k]) * 100:.1f}% | {S.wape(y[te][k], ridge[k]) * 100:.1f}% |")


if __name__ == "__main__":
    main()
