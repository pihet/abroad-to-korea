"""시군구별 조건 데이터: 월별 혼잡도(실측·예측), 날씨, 거리, 관광지 주소, 데이터 기준일.

모두 data/raw 의 실제 원천에서 계산한다. 없으면 None 을 돌려주고 화면은 "자료 없음"으로 표시한다.
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for sub in ("src/prototype", "src/forecast", "src/collect"):
    sys.path.insert(0, str(ROOT / sub))

import clip_proto as cp  # noqa: E402
import make_demo_page as demo  # noqa: E402
import p1_spec  # noqa: E402
from region_context import monthly_climate, region_centers  # noqa: E402

ORIGINS = {"서울": (37.5665, 126.9780), "부산": (35.1796, 129.0756), "대구": (35.8714, 128.6014),
           "광주": (35.1595, 126.8526), "대전": (36.3504, 127.3845)}
COMFORT = (15.0, 24.0)
FORECAST_MONTH = "2026-10"  # 마지막 실측(2026-08)의 2개월 뒤 = 월 단위 예측 모델 조건

DATA_SOURCES = [
    {"name": "국내 관광지·사진·주소 (한국관광공사 TourAPI KorService2)", "as_of": "2026-10-02 수집", "period": "수집 시점 등록 관광지"},
    {"name": "외지인 방문자 수 (한국관광공사 관광 빅데이터 지역별 방문자수)", "as_of": "2026-10-02 수집", "period": "2018-01 ~ 2026-08 (화면은 최근 12개월 2025-09 ~ 2026-08)"},
    {"name": "혼잡도 예측 (월 단위 ridge, HANDOFF 10-1)", "as_of": "2026-10-04 계산", "period": "2026-10 (2026-08까지 실측으로 학습)"},
    {"name": "날씨 (Open-Meteo Historical Weather, CC BY 4.0)", "as_of": "2026-10-04 수집", "period": "2021 ~ 2025년 같은 달 평균"},
    {"name": "해외 데모 사진 (Wikimedia Commons, 사진별 라이선스)", "as_of": "2026-10-02 수집", "period": "-"},
]


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class Context:
    """서버 시작 때 한 번 만든다. 시군구 키 = '시도코드_시군구명' (clip_proto 지역 단위와 같다)."""

    def __init__(self, regions):
        self.regions = regions  # [(시도코드, 시군구명)] — 추천 인덱스와 같은 순서
        self.centers = region_centers()
        self._monthly_visitors()
        self._forecast()
        self._climate_cache = {}

    # ---------------- 혼잡도
    def _visit_key_map(self, codes):
        names = demo.visit_code_names()
        out = defaultdict(list)
        for c in codes:
            nm = names.get(c, "")
            sido = demo.VISIT_TO_TOUR_SIDO.get(c[:2], c[:2])
            if nm:
                out[(sido, nm.split()[0])].append(c)
        return out

    def _monthly_visitors(self):
        wide = p1_spec.load_daily()
        M = wide.resample("MS").sum()
        last12 = M.iloc[-12:]
        self.months12 = [d.strftime("%Y-%m") for d in last12.index]
        keymap = self._visit_key_map(list(M.columns))
        self.visitors12 = {}
        for key, codes in keymap.items():
            self.visitors12[key] = last12[codes].sum(axis=1).to_numpy()

    def _forecast(self):
        pred, _ = demo.monthly_forecast(FORECAST_MONTH)
        keymap = self._visit_key_map(list(pred))
        self.forecast = {key: float(sum(pred[c] for c in codes)) for key, codes in keymap.items()}

    def congestion(self, key, month):
        """고른 달의 혼잡도와 12개월 실측. index = 방문자 / 최근 12개월 평균 × 100."""
        v = self.visitors12.get(key)
        if v is None:
            return None
        mean = float(v.mean())
        monthly = [{"month": m, "visitors": int(x), "index": round(100 * x / mean)} for m, x in zip(self.months12, v)]
        if month is None:  # 여행 월을 고르지 않음: 최근 12개월 월평균
            return {"month": None, "index": None, "visitors": round(mean), "basis": "annual",
                    "basis_month": f"{self.months12[0]}~{self.months12[-1]}", "monthly": monthly}
        if month == int(FORECAST_MONTH[5:]) and key in self.forecast:
            value, basis, basis_month = self.forecast[key], "forecast", FORECAST_MONTH
        else:
            hit = [m for m in monthly if int(m["month"][5:]) == month][0]
            value, basis, basis_month = hit["visitors"], "actual", hit["month"]
        return {"month": month, "index": round(100 * value / mean), "visitors": int(value), "basis": basis,
                "basis_month": basis_month, "monthly": monthly}

    # ---------------- 날씨·거리
    def climate(self, key, month):
        if month is None:  # 날씨는 달마다 달라서 월이 없으면 보여 주지 않는다
            return None
        ck = (key, month)
        if ck not in self._climate_cache:
            d = monthly_climate(key[0], key[1], month)
            out = None
            if d:
                temps = [t for t in d["temperature_2m_mean"] if t is not None]
                rains = [r for r in d["precipitation_sum"] if r is not None]
                years = len({t[:4] for t in d["time"]})
                if temps and years:
                    t = float(np.mean(temps))
                    rain_days = sum(r >= 1.0 for r in rains) / years
                    pen = max(0.0, COMFORT[0] - t, t - COMFORT[1])
                    out = {"month": month, "temp_c": round(t, 1), "rain_days": round(rain_days, 1),
                           "comfort": round(-(pen + 0.5 * rain_days), 2)}
            self._climate_cache[ck] = out
        return self._climate_cache[ck]

    def distance(self, key, origin):
        c = self.centers.get(key)
        if origin not in ORIGINS or c is None:
            return None
        return round(haversine(c, ORIGINS[origin]))
