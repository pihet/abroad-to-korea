"""시군구별 1인 여행 경비 추정 (국민여행조사 2023~2025, src/cost/build_cost_table.py 가 만든 표).

표본이 30건 미만인 시군구는 시도 값이 들어 있다 (level = 'sido'). 표가 없으면 None 을 돌려준다.
"""

import csv

from .context import ROOT

TABLE = ROOT / "data/interim/app/travel_cost.csv"
SOURCE = "국민여행조사 원자료 2023~2025 (문화체육관광부·한국문화관광연구원), 순수 관광 여행의 1인 경비 가중 중앙값"


class Cost:
    def __init__(self):
        self.rows = {}
        if TABLE.exists():
            with TABLE.open(encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["median"]:
                        self.rows[(r["key"], r["trip"])] = r

    def for_region(self, key):
        out = {}
        for trip in ("day", "1night"):
            r = self.rows.get((key, trip))
            if r:
                out[trip] = {"median": round(float(r["median"]), -3), "p25": round(float(r["p25"]), -3),
                             "p75": round(float(r["p75"]), -3), "n": int(r["n"]),
                             "level": r["level"], "sido": r["sido"]}
        return {"key": key, **out, "source": SOURCE} if out else None
