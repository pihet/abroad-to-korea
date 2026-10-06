"""고른 기간에 비가 올까: 16일 안이면 Open-Meteo 일기예보, 더 멀면 2021~2025년 같은 날짜 기록.

두 값은 성격이 다르다 (예보 vs 과거 기록). 응답의 basis 로 구분하고 화면에도 그대로 적는다.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from region_context import monthly_climate

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16  # Open-Meteo 무료 예보 최대 기간
MAX_SPAN = 14  # 한 번에 고를 수 있는 최대 일수
RAIN_MM = 1.0  # 비 온 날 기준 (지역 상세의 '비 온 날'과 같다)
RAIN_PROB = 50  # 예보에서 '비 예보'로 볼 강수확률 (%)


class RainError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 오류. status = 돌려줄 HTTP 코드."""

    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def _days(start, end):
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _history(key, start, end):
    by_month = {}
    rows = []
    for d in _days(start, end):
        if d.month not in by_month:
            by_month[d.month] = monthly_climate(key[0], key[1], d.month)
        m = by_month[d.month]
        if m is None:
            raise RainError("이 지역의 과거 날씨 자료가 없습니다.", 404)
        hits = {t[:4]: p for t, p in zip(m["time"], m["precipitation_sum"]) if t[5:] == d.strftime("%m-%d") and p is not None}
        rows.append({"date": d.isoformat(), "rainy_years": sum(p >= RAIN_MM for p in hits.values()), "years": len(hits),
                     "by_year": {y: round(p, 1) for y, p in sorted(hits.items())}})
    years = sorted({y for r in rows for y in r["by_year"]})
    any_rain = sum(any(r["by_year"].get(y, 0) >= RAIN_MM for r in rows) for y in years)
    avg_days = sum(r["rainy_years"] for r in rows) / len(years) if years else None
    return {"basis": "history", "years": f"{years[0]}~{years[-1]}" if years else None, "n_years": len(years),
            "days": rows, "years_with_rain": any_rain, "avg_rainy_days": round(avg_days, 1) if avg_days is not None else None,
            "rule": f"하루 강수량 {RAIN_MM:g}mm 이상을 비 온 날로 셈"}


def _forecast(center, start, end):
    q = urllib.parse.urlencode({"latitude": center[0], "longitude": center[1], "timezone": "Asia/Seoul",
                                "daily": "precipitation_sum,precipitation_probability_max",
                                "start_date": start.isoformat(), "end_date": end.isoformat()})
    try:
        with urllib.request.urlopen(f"{FORECAST_URL}?{q}", timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))["daily"]
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        raise RainError(f"일기예보를 불러오지 못했습니다 ({type(e).__name__}). 잠시 뒤 다시 시도해 주세요.", 503)
    rows = [{"date": t, "rain_mm": mm, "prob": pr}
            for t, mm, pr in zip(d["time"], d["precipitation_sum"], d["precipitation_probability_max"])]
    rainy = [r for r in rows if (r["prob"] or 0) >= RAIN_PROB or (r["rain_mm"] or 0) >= RAIN_MM]
    return {"basis": "forecast", "days": rows, "rainy_days": len(rainy),
            "rule": f"강수확률 {RAIN_PROB}% 이상 또는 예상 강수량 {RAIN_MM:g}mm 이상을 비 예보로 셈"}


class Rain:
    def __init__(self, centers):
        self.centers = centers  # {(시도코드, 시군구명): (위도, 경도)}
        self._cache = {}  # 예보는 같은 날 안에서만 재사용

    def check(self, key, start, end, today=None):
        today = today or date.today()
        if end < start:
            raise RainError("끝나는 날이 시작하는 날보다 빠릅니다.")
        if (end - start).days + 1 > MAX_SPAN:
            raise RainError(f"기간은 최대 {MAX_SPAN}일까지 고를 수 있습니다.")
        if key not in self.centers:
            raise RainError("이 지역의 위치 정보가 없습니다.", 404)
        if today <= start and end < today + timedelta(days=FORECAST_DAYS):
            ck = (key, start, end, today)
            if ck not in self._cache:
                self._cache[ck] = _forecast(self.centers[key], start, end)
            out = self._cache[ck]
        else:
            out = _history(key, start, end)
        return {"start": start.isoformat(), "end": end.isoformat(), **out}
