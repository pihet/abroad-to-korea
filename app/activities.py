"""시군구별 "할 만한 것": 한국관광공사 TourAPI 관광지(12)·레포츠(28)·축제(15) 목록을 활동 묶음으로 나눈다.

묶음은 TourAPI 분류체계(lclsSystm) 이름으로만 정한다. 데이터에 없는 정보(개장 시기, 난이도, 추천도)는 만들지 않는다.
정렬은 "사진이 닮은 관광지에서 가까운 순" 하나뿐이다.
"""

import json
import re
import sys
from datetime import date
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/prototype"))
import clip_proto as cp  # noqa: E402

from .context import haversine  # noqa: E402

RAW = ROOT / "data/raw/tourapi"
LCLS = RAW / "lclsSystmCode2_20261004.json"
LEPORTS = RAW / "areaBasedList2_ct28_20261004"
FESTIVALS = RAW / "searchFestival2_20251001_20261231.json"
FOOD_INTRO = RAW / "detailIntro2_ct39"   # 음식점 대표메뉴 (tour_food_intro.py, 매일 이어 받는 중)
FESTIVAL_YEAR = "2026"   # 축제 목록은 끝난 행사가 빠지므로 2026년 기록을 쓴다
TODAY = "20261004"

GROUPS = [  # (키, 화면 이름) — 화면의 색 순서와 같다
    ("water", "물·바다"),
    ("mountain", "산·숲"),
    ("leisure", "레저"),
    ("camping", "캠핑"),
    ("experience", "체험"),
    ("food", "먹거리"),
    ("festival", "축제"),
]
# 여행 활동으로 보기 어려운 레포츠 세부 분류 (동네 체육시설)
LEPORTS_EXCLUDE = {"스포츠센터, 수련시설", "스포츠경기장", "수영", "인라인(실내 인라인 포함)"}
OK_LICENSE = {"Type1": "공공누리 제1유형 (출처표시)", "Type3": "공공누리 제3유형 (출처표시·변경금지)"}


def _names():
    names = {}
    for it in json.loads(LCLS.read_text())["response"]["body"]["items"]["item"]:
        for lv in "123":
            if it.get(f"lclsSystm{lv}Cd"):
                names[it[f"lclsSystm{lv}Cd"]] = it[f"lclsSystm{lv}Nm"]
    return names


def _pages(d):
    out = []
    for p in sorted(d.glob("page_*.json")):
        out += json.loads(p.read_text())["response"]["body"]["items"]["item"]
    return out


def classify(item, ctype, names):
    """(묶음 키, 세부 분류 이름) 또는 None."""
    c2, c3 = item.get("lclsSystm2", ""), item.get("lclsSystm3", "")
    n2, n3 = names.get(c2, ""), names.get(c3, "")
    if ctype == "15":
        return "festival", "축제"
    if ctype == "39":
        return "food", n3 or "음식점"
    if ctype == "28":
        if n3 in LEPORTS_EXCLUDE or not n2:
            return None
        if n2 == "캠핑":
            return "camping", n3 or n2
        if n2 == "수상레저스포츠":
            return "water", n3 or n2
        if n2 in ("육상레저스포츠", "항공레저스포츠", "복합레저스포츠", "레저스포츠시설"):
            return "leisure", n3 or n2
        return None
    if c2 == "NA02" or n3 == "유람선/잠수함관광":
        return "water", n3 or n2
    if c2 in ("NA01", "NA04"):
        return "mountain", n3 or n2
    if c2.startswith("EX"):
        return "experience", n3 or n2
    return None


def _fl(x):
    try:
        v = float(x)
        return v if v else None
    except (TypeError, ValueError):
        return None


class Activities:
    def __init__(self):
        names = _names()
        unit_of = cp.load_regions()
        food_dirs = sorted(RAW.glob("areaBasedList2_ct39_*"))
        sources = [("12", _pages(cp.RAW_TOUR)), ("28", _pages(LEPORTS)), ("39", _pages(food_dirs[-1]) if food_dirs else []),
                   ("15", json.loads(FESTIVALS.read_text())["response"]["body"]["items"]["item"])]
        self.by_region, self.by_id = {}, {}
        for ctype, items in sources:
            for it in items:
                u = unit_of.get((it.get("lDongRegnCd"), it.get("lDongSignguCd")))
                g = classify(it, ctype, names)
                lat, lon = _fl(it.get("mapy")), _fl(it.get("mapx"))
                if not u or not g or lat is None or lon is None:
                    continue
                if ctype == "15" and not _in_year(it):
                    continue
                photo = it.get("firstimage2") if it.get("cpyrhtDivCd") in OK_LICENSE else None
                rec = {"id": it["contentid"], "name": it["title"], "group": g[0], "kind": g[1],
                       "lat": lat, "lon": lon, "address": it.get("addr1") or None,
                       "image_url": f"/images/tour/{it['contentid']}" if photo else None,
                       "license": OK_LICENSE.get(it.get("cpyrhtDivCd")) if photo else None,
                       "start": it.get("eventstartdate"), "end": it.get("eventenddate")}
                if ctype == "39":
                    rec["menu"] = _menu(it["contentid"])
                self.by_id[it["contentid"]] = {**rec, "_photo": photo}
                self.by_region.setdefault(f"{u[0]}_{u[2]}", []).append(rec)

    def for_region(self, key, month, origin=None):
        """origin: (위도, 경도) — 사진이 닮은 관광지. 있으면 가까운 순, 없으면 이름순."""
        out = []
        for r in self.by_region.get(key, []):
            if r["group"] == "festival":
                if not _in_month(r, month):
                    continue
                r = {**r, "period": f"{_d(r['start'])} ~ {_d(r['end'])}",
                     "schedule": "예정" if r["end"] >= TODAY else "지난 개최 기록"}
            d = round(haversine(origin, (r["lat"], r["lon"])), 1) if origin else None
            out.append({**{k: v for k, v in r.items() if k not in ("start", "end")}, "distance_km": d})
        out.sort(key=lambda r: (r["distance_km"] if r["distance_km"] is not None else 0, r["name"]))
        counts = Counter(r["group"] for r in out)
        groups = [{"key": k, "label": label, "count": counts.get(k, 0)} for k, label in GROUPS]
        return groups, out

    def festivals_between(self, start, end, max_days=62):
        """start~end(YYYYMMDD)에 하루라도 열리는 축제. 1년 내내 하는 상설 행사는 '이번 주 축제'가 아니라서 max_days 넘으면 뺀다.
        이 기간에 시작하는 축제를 먼저, 그다음 끝나는 날이 가까운 순."""
        out = []
        for key, items in self.by_region.items():
            for r in items:
                if r["group"] != "festival" or not r["start"] or not r["end"]:
                    continue
                if r["end"] < start or r["start"] > end:
                    continue
                if (date.fromisoformat(_iso(r["end"])) - date.fromisoformat(_iso(r["start"]))).days + 1 > max_days:
                    continue
                out.append({"id": r["id"], "name": r["name"], "region_key": key, "address": r["address"],
                            "image_url": r["image_url"], "license": r["license"], "start": _iso(r["start"]), "end": _iso(r["end"]),
                            "starts_in_range": r["start"] >= start})
        out.sort(key=lambda f: (not f["starts_in_range"], f["start"] if f["starts_in_range"] else f["end"], f["name"]))
        return out

    def food_summary(self, key, top=8, min_menus=5):
        """지역 먹거리: 음식점 대표메뉴에 많이 나오는 음식. 대표메뉴를 받은 곳이 min_menus 미만이면 순위를 내지 않는다."""
        foods = [r for r in self.by_region.get(key, []) if r["group"] == "food"]
        menus = [r["menu"] for r in foods if r.get("menu")]
        counts = Counter()
        for m in menus:
            counts.update(set(_menu_words(m)))  # 한 음식점이 같은 음식을 여러 번 적어도 1번
        words = [{"name": w, "places": n} for w, n in counts.most_common(top) if n >= 2] if len(menus) >= min_menus else []
        return {"n_places": len(foods), "n_menus": len(menus), "top": words}

    def photo_url(self, cid):
        r = self.by_id.get(cid)
        return r["_photo"] if r else None


def _menu(cid):
    """음식점 대표메뉴. 아직 받지 않았으면 None (화면은 '대표메뉴 준비 중' 없이 그냥 비워 둔다)."""
    f = FOOD_INTRO / f"{cid}.json"
    if not f.exists():
        return None
    it = ((json.loads(f.read_text(encoding="utf-8"))["response"]["body"].get("items") or {}).get("item") or [{}])
    it = it[0] if isinstance(it, list) else it
    return (it.get("firstmenu") or "").strip() or None


_MENU_SPLIT = re.compile(r"[,/·|+&\n]|\s및\s")
_MENU_TAIL = re.compile(r"\s*(외|등|기타)\s*$")  # "막국수 외" → "막국수" (등갈비처럼 이름 안의 글자는 그대로)
_MENU_NOISE = re.compile(r"\(.*?\)|\[.*?\]|[0-9][0-9,.]*\s*(원|인분|마리|개|g|kg|ml|L|인|접시|그릇|세트)?|[~*★☆]")


def _menu_words(menu):
    """'북경오리 1마리, 소고기국밥(1인분) 9,000원' → ['북경오리', '소고기국밥']"""
    out = []
    for part in _MENU_SPLIT.split(menu):
        w = _MENU_TAIL.sub("", _MENU_NOISE.sub(" ", part)).strip()
        w = " ".join(w.split())
        if 2 <= len(w) <= 12:
            out.append(w)
    return out


def _in_year(it):
    return it.get("eventstartdate", "")[:4] <= FESTIVAL_YEAR <= it.get("eventenddate", "")[:4]


def _in_month(r, month):
    if month is None:  # 여행 월을 고르지 않으면 2026년 축제 전부
        return True
    ym = f"{FESTIVAL_YEAR}{month:02d}"
    return r["start"][:6] <= ym <= r["end"][:6]


def _iso(s):
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def _d(s):
    return f"{s[:4]}.{s[4:6]}.{s[6:]}" if s and len(s) == 8 else s
