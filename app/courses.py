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

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/tourapi"
INFO = RAW / "detailInfo2_ct25"
INTRO = RAW / "detailIntro2_ct25"
TAG = re.compile(r"<[^>]+>")


def _items(path):
    it = ((json.loads(path.read_text(encoding="utf-8"))["response"]["body"].get("items") or {}).get("item")) or []
    return [it] if isinstance(it, dict) else it


def _text(s, n=180):
    s = " ".join(TAG.sub(" ", s or "").split())
    return s if len(s) <= n else s[:n].rstrip() + "…"


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
                place[it["contentid"]] = {"lat": lat, "lon": lon, "region": f"{u[0]}_{u[2]}",
                                          "image_url": f"/images/kr/{it['contentid']}" if ok else None,
                                          "license": OK_LICENSE[it["cpyrhtDivCd"]] if ok else None}
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
                a, pl = acts.by_id.get(cid), place.get(cid)
                loc = a or pl
                img = (a and a["image_url"] and a) or (pl and pl["image_url"] and pl) or None
                stops.append({"order": len(stops) + 1, "id": cid, "name": (s.get("subname") or "").strip(),
                              "overview": _text(s.get("subdetailoverview")),
                              "lat": loc["lat"] if loc else None, "lon": loc["lon"] if loc else None,
                              "group": a["group"] if a else None, "kind": a["kind"] if a else None,
                              "image_url": img["image_url"] if img else None, "license": img["license"] if img else None,
                              "region": region_of.get(cid) or (pl["region"] if pl else None)})
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
