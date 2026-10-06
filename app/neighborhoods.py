"""시군구 안의 읍·면·동: 경계(지도용) + 활동지 수. 지역 상세 페이지의 "활동이 몰린 동네" 지도에 쓴다.

경계: vuski/admdongkor ver20260701 (통계청 SGIS 행정동 경계 기반, CC BY 4.0 — SGIS와 저장소 출처 표시 필요)
활동지: app/activities.py 의 관광지·레포츠 (축제는 달마다 바뀌어 빼고 센다)
처음 한 번 계산해 data/interim/app/neighborhoods.json 에 저장한다.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/raw/admdongkor/HangJeongDong_ver20260701.geojson"
CACHE = ROOT / "data/interim/app/neighborhoods.json"
SIMPLIFY_DEG = 0.0006  # 약 60m. 화면 지도용으로 꼭짓점을 줄인다
CREDIT = "행정동 경계: 통계청 SGIS · vuski/admdongkor (CC BY 4.0)"


def _sgg_name(p):
    """경계 데이터의 시군구 이름 → 우리 키의 이름. '고양시덕양구' → '고양시', 세종 '세종시' → '세종특별자치시'."""
    if p["sidonm"].startswith("세종"):
        return p["sidonm"]
    m = re.match(r"^(.+?시)(.+구)$", p["sggnm"])
    return m.group(1) if m else p["sggnm"]


def _round(geom):
    return json.loads(json.dumps(geom.__geo_interface__), parse_float=lambda x: round(float(x), 5))


def build(acts, sido_code):
    from shapely import STRtree, Point
    from shapely.geometry import shape

    feats = json.loads(SRC.read_text(encoding="utf-8"))["features"]
    shapes, meta = [], []
    for f in feats:
        p = f["properties"]
        code = sido_code.get(p["sidonm"])
        if code is None:
            continue
        shapes.append(shape(f["geometry"]))
        meta.append({"key": f"{code}_{_sgg_name(p)}", "code": p["adm_cd2"], "name": p["adm_nm"].split()[-1]})
    tree = STRtree(shapes)
    counts = [dict() for _ in shapes]
    for items in acts.by_region.values():
        for r in items:
            if r["group"] in ("festival", "food"):  # 동네 순위는 관광지·레포츠만 (음식점은 도심에 몰려 순위를 덮는다)
                continue
            pt = Point(r["lon"], r["lat"])
            for i in tree.query(pt, predicate="intersects"):
                counts[i][r["group"]] = counts[i].get(r["group"], 0) + 1
                break
    out = {}
    for s, m, c in zip(shapes, meta, counts):
        parts = list(getattr(s, "geoms", [s]))
        big = max(parts, key=lambda g: g.area)
        lab = big.representative_point()  # 가장 큰 땅덩이 안의 한 점 (경계 상자 중심은 섬이 있으면 바다에 찍힌다)
        out.setdefault(m["key"], []).append({
            "code": m["code"], "name": m["name"], "groups": c, "total": sum(c.values()),
            "label": [round(lab.y, 5), round(lab.x, 5)],
            "parts": [[round(v, 5) for v in g.bounds] + [g.area] for g in parts],
            "geometry": _round(s.simplify(SIMPLIFY_DEG, preserve_topology=True)),
        })
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


class Neighborhoods:
    def __init__(self, acts, sido_code):
        self.by_region = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else build(acts, sido_code)

    def for_region(self, key, top=5):
        """그 시군구의 읍·면·동 전부(지도 바탕) + 활동지 수 상위 top 곳 (활동지 0곳은 순위에서 뺀다)."""
        dongs = self.by_region.get(key, [])
        ranked = sorted((d for d in dongs if d["total"] > 0), key=lambda d: (-d["total"], d["name"]))[:top]
        rank = {d["code"]: i + 1 for i, d in enumerate(ranked)}
        return [{k: v for k, v in d.items() if k != "parts"} | {"rank": rank.get(d["code"])} for d in dongs]

    def focus(self, key):
        """지도 범위 [남, 서, 북, 동]: 시군구 전체 넓이의 1% 미만인 외딴 조각(예: 울릉군의 독도)은 뺀다."""
        parts = [p for d in self.by_region.get(key, []) for p in d["parts"]]
        if not parts:
            return None
        total = sum(p[4] for p in parts)
        keep = [p for p in parts if p[4] >= total * 0.01] or parts
        return [min(p[1] for p in keep), min(p[0] for p in keep), max(p[3] for p in keep), max(p[2] for p in keep)]
