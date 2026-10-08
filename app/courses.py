"""한국관광공사 공식 여행코스(contentTypeId=25): 코스마다 들르는 곳·순서·설명, 총거리·소요시간.

코스 목록의 시군구 코드는 대부분 비어 있어서, 들르는 곳이 어느 시군구에 있는지로 코스의 지역을 정한다.
들르는 곳의 위치는 받아 둔 관광지 전체 목록(12,603곳)과 레포츠·음식점·축제(activities)에서 찾는다.
사진은 라이선스(공공누리 1·3유형)를 확인한 것만: 활동지 사진, 또는 추천 인덱스의 관광지 사진(/images/kr).
(코스 원문의 사진 subdetailimg 은 라이선스 표시가 없어 쓰지 않는다. 문화시설·쇼핑 등은 위치 없이 이름·설명만 보여 준다.)
"""

import json
import re
from collections import Counter
from pathlib import Path

from .activities import OK_LICENSE, _fl, _pages, cp
from .context import haversine

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/tourapi"
INFO = RAW / "detailInfo2_ct25"
COMMON = RAW / "detailCommon2"  # 목록에 없는 정류장(문화시설·쇼핑 등)의 좌표 (tour_course_stops.py)
INTRO = RAW / "detailIntro2_ct25"
TAG = re.compile(r"<[^>]+>")


def _items(path):
    it = ((json.loads(path.read_text(encoding="utf-8"))["response"]["body"].get("items") or {}).get("item")) or []
    return [it] if isinstance(it, dict) else it


def _text(s, n=180):
    s = " ".join(TAG.sub(" ", s or "").split())
    return s if len(s) <= n else s[:n].rstrip() + "…"


def _common_place(cid, unit_of):
    """받아 둔 detailCommon2 원문에서 좌표·시군구. 없으면 None (사진은 쓰지 않는다)."""
    f = COMMON / f"{cid}.json" if cid else None
    if not f or not f.exists():
        return None
    it = (_items(f) or [{}])[0]
    lat, lon = _fl(it.get("mapy")), _fl(it.get("mapx"))
    u = unit_of.get((it.get("lDongRegnCd"), it.get("lDongSignguCd")))
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon, "region": f"{u[0]}_{u[2]}" if u else None, "image_url": None, "license": None}


def _name(s):
    return re.sub(r"[\s·.,'\"-]", "", s or "").lower()


def _fill_by_name(stops, by_name, max_km=30):
    """좌표를 못 찾은 정류장을 이름으로 찾는다. 코스가 옛 콘텐츠 번호(삭제됨)를 가리키는 경우가 있어서다 (예: 오죽헌).
    '점심식사(일출봉횟집)'처럼 괄호 안이 실제 장소면 그것도 찾아 본다. 후보가 여럿이면 코스의 다른 정류장에 가장 가까운 곳,
    max_km 보다 멀면 쓰지 않는다 (같은 이름의 다른 지역 장소)."""
    located = [(s["lat"], s["lon"]) for s in stops if s["lat"] is not None]
    if not located:
        return
    center = (sum(a for a, _ in located) / len(located), sum(b for _, b in located) / len(located))
    for s in stops:
        if s["lat"] is not None:
            continue
        names = [s["name"], *re.findall(r"\((.*?)\)", s["name"]), re.sub(r"\(.*?\)", "", s["name"])]
        keys = {_name(n) for n in names if len(_name(n)) >= 3}
        cands = [c for k in keys for c in by_name.get(k, [])]
        if not cands:  # '오죽헌' ↔ '강릉 오죽헌'처럼 한쪽 이름이 다른 쪽에 들어 있는 경우
            cands = [c for k in keys for n, cs in by_name.items() if len(n) >= 3 and (k in n or n in k) for c in cs]
        if not cands:
            continue
        best = min(cands, key=lambda c: haversine(center, (c["lat"], c["lon"])))
        if haversine(center, (best["lat"], best["lon"])) <= max_km:
            s.update(lat=best["lat"], lon=best["lon"], region=s["region"] or best["region"])


class Courses:
    def __init__(self, acts, engine):
        dirs = sorted(RAW.glob("areaBasedList2_ct25_*"))
        listing = [it for p in sorted(dirs[-1].glob("page_*.json")) for it in _items(p)] if dirs else []
        region_of = {r["id"]: key for key, rows in acts.by_region.items() for r in rows}
        # 활동 묶음으로 분류되지 않은 관광지(예: 전통마을)도 위치를 찾도록 관광지 전체 목록을 쓴다
        unit_of = cp.load_regions()
        place = {}
        for it in _pages(cp.RAW_TOUR):
            u = unit_of.get((it.get("lDongRegnCd"), it.get("lDongSignguCd")))
            lat, lon = _fl(it.get("mapy")), _fl(it.get("mapx"))
            if u and lat is not None and lon is not None:
                ok = it["contentid"] in engine.I["items"] and it.get("firstimage") and it.get("cpyrhtDivCd") in OK_LICENSE
                place[it["contentid"]] = {"name": it.get("title"), "lat": lat, "lon": lon, "region": f"{u[0]}_{u[2]}",
                                          "image_url": f"/images/kr/{it['contentid']}" if ok else None,
                                          "license": OK_LICENSE[it["cpyrhtDivCd"]] if ok else None}
        by_name = {}
        for cid, r in [*acts.by_id.items(), *place.items()]:
            by_name.setdefault(_name(r.get("name")), []).append({"lat": r["lat"], "lon": r["lon"], "region": r.get("region") or region_of.get(cid)})
        self.by_region = {}
        self.n_total = len(listing)
        self.n_loaded = 0
        for c in listing:
            f = INFO / f"{c['contentid']}.json"
            if not f.exists():
                continue
            self.n_loaded += 1
            stops, seen = [], set()
            for s in sorted(_items(f), key=lambda s: int(s.get("subnum") or 0)):
                sid = s.get("subcontentid") or s.get("subname")
                if sid in seen:  # 원문에 같은 곳이 여러 번 나오는 코스가 있다 (처음 나온 순서만 남김)
                    continue
                seen.add(sid)
                cid = s.get("subcontentid")
                a, pl = acts.by_id.get(cid), place.get(cid) or _common_place(cid, unit_of)
                loc = a or pl
                img = (a and a["image_url"] and a) or (pl and pl["image_url"] and pl) or None
                stops.append({"order": len(stops) + 1, "id": cid, "name": (s.get("subname") or "").strip(),
                              "overview": _text(s.get("subdetailoverview")),
                              "lat": loc["lat"] if loc else None, "lon": loc["lon"] if loc else None,
                              "group": a["group"] if a else None, "kind": a["kind"] if a else None,
                              "image_url": img["image_url"] if img else None, "license": img["license"] if img else None,
                              "region": region_of.get(cid) or (pl["region"] if pl else None)})
            _fill_by_name(stops, by_name)
            regions = Counter(s["region"] for s in stops if s["region"])
            if not regions:
                continue
            intro = {}
            fi = INTRO / f"{c['contentid']}.json"
            if fi.exists() and _items(fi):
                intro = _items(fi)[0]
            course = {"id": c["contentid"], "title": c["title"].strip(), "stops": stops,
                      "distance": intro.get("distance") or None, "taketime": intro.get("taketime") or None,
                      "theme": intro.get("theme") or None, "regions": dict(regions)}
            for key in regions:
                self.by_region.setdefault(key, []).append(course)

    def for_region(self, key):
        """그 시군구에 들르는 곳이 많은 코스부터."""
        rows = self.by_region.get(key, [])
        return sorted(rows, key=lambda c: (-c["regions"][key], -len(c["stops"]), c["title"]))
