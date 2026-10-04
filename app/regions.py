"""시군구 조건 필터: 바다 가까움 · 산·숲 많음 · 덜 붐빔 · 쾌적한 날씨 · 시도.

기준은 화면에 그대로 적을 수 있는 것만 쓴다 (FILTERS 의 basis).
"""

import json
from pathlib import Path

import numpy as np

from .context import COMFORT

ROOT = Path(__file__).resolve().parents[1]
COAST_SRC = ROOT / "data/raw/naturalearth/ne_10m_coastline.geojson"   # Natural Earth (public domain)
COAST_CACHE = ROOT / "data/interim/app/region_coast_km.json"
COAST_KM = 3.0
MOUNTAIN_MIN = 8

FILTERS = {
    "sea": ("바다 가까운 곳", f"관광지가 해안선 {COAST_KM:g}km 안에 있는 시군구 (Natural Earth 해안선)"),
    "mountain": ("산·숲이 많은 곳", f"산·계곡·숲·자연공원 관광지 {MOUNTAIN_MIN}곳 이상 (TourAPI 분류)"),
    "calm": ("방문객이 적은 곳", "그 달 외지인 방문자 수가 전국 시군구 중앙값 이하 (절대량. 카드의 혼잡도는 그 지역 평소 대비라 다를 수 있음)"),
    "mild": ("날씨가 쾌적한 곳", f"그 달 평균기온 {COMFORT[0]}~{COMFORT[1]}°C (2021~2025년)"),  # 달마다 바뀜: weather_rule
}


def weather_rule(median):
    """그 달 전국 평균기온 중앙값으로 날씨 칩의 방향을 정한다: (방향, 이름, 기준 문구).
    추운 달은 따뜻한 쪽, 더운 달은 시원한 쪽, 그 사이는 쾌적 구간. 고정 구간만 쓰면 1~4월·11~12월은 0곳이 된다."""
    if median < COMFORT[0]:
        return "warm", "따뜻한 곳", f"그 달 평균기온이 전국 시군구 중앙값({median}°C) 이상 (2021~2025년)"
    if median > COMFORT[1]:
        return "cool", "시원한 곳", f"그 달 평균기온이 전국 시군구 중앙값({median}°C) 이하 (2021~2025년)"
    return "mild", FILTERS["mild"][0], FILTERS["mild"][1]


def _weather_ok(way, t, median):
    if way == "warm":
        return t >= median
    if way == "cool":
        return t <= median
    return COMFORT[0] <= t <= COMFORT[1]


def coast_distance(acts):
    """시군구마다 관광지·활동지 중 해안선에 가장 가까운 곳까지의 거리(km). 한 번 계산해 저장한다."""
    if COAST_CACHE.exists():
        return json.loads(COAST_CACHE.read_text())
    from sklearn.neighbors import BallTree
    pts = []
    for f in json.loads(COAST_SRC.read_text())["features"]:
        g = f["geometry"]
        for ln in (g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]):
            a = np.array(ln)
            if not ((a[:, 0] > 123) & (a[:, 0] < 132.5) & (a[:, 1] > 32.5) & (a[:, 1] < 39.5)).any():
                continue
            for p, q in zip(a[:-1], a[1:]):  # 약 200m 간격으로 촘촘히
                n = max(1, int(np.hypot(*(q - p)) / 0.002))
                pts += [p + (q - p) * t for t in np.linspace(0, 1, n, endpoint=False)]
    tree = BallTree(np.radians(np.array(pts)[:, ::-1]), metric="haversine")
    out = {}
    for key, items in acts.by_region.items():
        d, _ = tree.query(np.radians([[r["lat"], r["lon"]] for r in items]), k=1)
        out[key] = round(float(d.min() * 6371), 2)
    COAST_CACHE.parent.mkdir(parents=True, exist_ok=True)
    COAST_CACHE.write_text(json.dumps(out, ensure_ascii=False))
    return out


class Regions:
    def __init__(self, engine, acts):
        self.e, self.ctx = engine, engine.ctx
        coast = coast_distance(acts)
        self.static = {}
        for i, key in enumerate(engine.region_keys):
            items = acts.by_region.get(key, [])
            sido_name = engine.I["name"][engine.I["regions"][i]].rsplit(" ", 1)[0]
            self.static[key] = {"key": key, "name": key.split("_", 1)[1], "sido": sido_name, "ri": i,
                                "coast_km": coast.get(key),
                                "mountain_n": sum(r["group"] == "mountain" for r in items)}
        self._month, self._rule = {}, {}

    def month_table(self, month):
        """시군구별 조건 값과 필터 통과 여부 (월마다 한 번 계산)."""
        if month in self._month:
            return self._month[month]
        rows = []
        for key, s in self.static.items():
            k = tuple(key.split("_", 1))
            cg, cl = self.ctx.congestion(k, month), self.ctx.climate(k, month)
            rows.append({**s, "visitors": cg["visitors"] if cg else None,
                         "congestion_index": cg["index"] if cg else None,
                         "temp_c": cl["temp_c"] if cl else None, "rain_days": cl["rain_days"] if cl else None})
        vis = sorted(r["visitors"] for r in rows if r["visitors"] is not None)
        med = vis[len(vis) // 2] if vis else None
        temps = sorted(r["temp_c"] for r in rows if r["temp_c"] is not None)
        t_med = temps[len(temps) // 2]
        rule = weather_rule(t_med)
        for r in rows:
            r["flags"] = {
                "sea": r["coast_km"] is not None and r["coast_km"] <= COAST_KM,
                "mountain": r["mountain_n"] >= MOUNTAIN_MIN,
                "calm": med is not None and r["visitors"] is not None and r["visitors"] <= med,
                "mild": r["temp_c"] is not None and _weather_ok(rule[0], r["temp_c"], t_med),
            }
        self._month[month] = rows
        self._rule[month] = rule
        return rows

    def filter_meta(self, month):
        """화면에 보일 칩 이름·기준. 날씨 칩은 그 달 방향에 따라 바뀐다."""
        self.month_table(month)
        _, label, basis = self._rule[month]
        return [{"key": k, "label": label if k == "mild" else v[0], "basis": basis if k == "mild" else v[1]}
                for k, v in FILTERS.items()]

    def allowed(self, month, filters, sido=None):
        """조건을 모두 통과한 시군구의 인덱스 집합. 조건이 없으면 None(전체)."""
        if not filters and not sido:
            return None
        return {r["ri"] for r in self.month_table(month)
                if all(r["flags"][f] for f in filters) and (not sido or r["sido"] == sido)}
