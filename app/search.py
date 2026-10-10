"""이름 검색: 읍·면·동(3,558곳)과 장소(관광지 전체·레포츠·음식점·축제). 시군구 검색은 화면이 230곳 목록으로 직접 한다.

장소를 누르면 그 시군구의 지역 상세를 열고, 그 장소가 있는 동네를 알면 그 동네를 고른 채로 연다.
"""

from .activities import _fl, _pages, cp

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def choseong(s):
    return "".join(CHO[(ord(c) - 0xAC00) // 588] if 0xAC00 <= ord(c) < 0xAC00 + 11172 else c for c in s)


def _norm(s):
    return "".join(s.split()).lower()


def _score(name, q, cho):
    """이름 앞에서 맞으면 3, 안에서 맞으면 2, 초성으로만 맞으면 1, 안 맞으면 0."""
    n = _norm(name)
    if n.startswith(q):
        return 3
    if q in n:
        return 2
    if cho and choseong(n).startswith(q):
        return 1
    return 0


class Search:
    def __init__(self, acts, hoods, static, include_places=True):
        dong_of = {}  # 장소 id → (시군구, 동 코드, 동 이름)
        self.dongs = []
        for key, rows in hoods.by_region.items():
            for d in rows:
                self.dongs.append({"name": d["name"], "code": d["code"], "region_key": key, "n_acts": d["total"]})
                for i in d["act_ids"] + d["food_ids"]:
                    dong_of[i] = (d["code"], d["name"])
        self.places, seen = [], set()
        if not include_places:
            self.static = static
            return
        for key, rows in acts.by_region.items():
            for r in rows:
                seen.add(r["id"])
                self.places.append(self._place(r["id"], r["name"], r["kind"], r["group"], key, dong_of))
        # 활동 묶음으로 분류되지 않은 관광지(전통마을·사찰 등)도 이름으로 찾을 수 있게
        unit_of = cp.load_regions()
        for it in _pages(cp.RAW_TOUR):
            u = unit_of.get((it.get("lDongRegnCd"), it.get("lDongSignguCd")))
            if not u or it["contentid"] in seen or _fl(it.get("mapy")) is None:
                continue
            seen.add(it["contentid"])
            self.places.append(self._place(it["contentid"], it["title"], "관광지", None, f"{u[0]}_{u[2]}", dong_of))
        self.static = static

    @staticmethod
    def _place(pid, name, kind, group, key, dong_of):
        d = dong_of.get(pid)
        return {"id": pid, "name": name.strip(), "kind": kind, "group": group, "region_key": key,
                "dong_code": d[0] if d else None, "dong_name": d[1] if d else None}

    def find(self, q, limit=20):
        q = _norm(q)
        if not q:
            return {"dongs": [], "places": []}
        cho = all(c in CHO for c in q)

        def top(rows, extra=lambda r: 0):
            hit = [(s, r) for r in rows if (s := _score(r["name"], q, cho))]
            hit.sort(key=lambda x: (-x[0], -extra(x[1]), len(x[1]["name"]), x[1]["name"]))
            return [self._with_region(r) for _, r in hit[:limit]]

        return {"dongs": top(self.dongs, lambda r: r["n_acts"]), "places": top(self.places)}

    def _with_region(self, r):
        st = self.static.get(r["region_key"], {})
        return {**r, "region_name": st.get("name"), "sido": st.get("sido")}
