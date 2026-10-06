"""음식점 메뉴 사진·추가 사진 표본 조사: 무작위 30곳 × (imageYN=N 메뉴, imageYN=Y 추가) = 60회.

detailImage2 는 관광지 추가 사진(tour_images.py)과 하루 한도를 나눠 쓴다. 자정 이후 이것을 먼저 돌리고 tour_images.py 930 을 돌린다.
원문은 data/raw/tourapi/detailImage2_ct39_sample/ 에 저장하고, 이미 받은 것은 건너뛴다 (한도에 걸려도 다음 날 이어서).
실행 (저장소 루트에서): python src/collect/tour_food_photo_sample.py
"""
import sys, json, random, glob, urllib.error, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, "src/collect")
from tour_attractions import load_api_key
key = load_api_key()
OUT = Path("data/raw/tourapi/detailImage2_ct39_sample"); OUT.mkdir(parents=True, exist_ok=True)
items = []
for p in sorted(glob.glob(sorted(glob.glob("data/raw/tourapi/areaBasedList2_ct39_*"))[-1] + "/page_*.json")):
    items += json.load(open(p))["response"]["body"]["items"]["item"]
sample = random.Random(7).sample(items, 30)
rows = []
for it in sample:
    cid = it["contentid"]; row = {"id": cid, "name": it["title"], "kind": it.get("lclsSystm3"), "first": bool(it.get("firstimage"))}
    for yn in ("N", "Y"):
        f = OUT / f"{cid}_{yn}.json"
        if not f.exists():
            q = urllib.parse.urlencode({"MobileOS": "ETC", "MobileApp": "samsungproj", "_type": "json", "contentId": cid, "imageYN": yn, "numOfRows": 30, "pageNo": 1})
            try:
                d = json.loads(urllib.request.urlopen(f"https://apis.data.go.kr/B551011/KorService2/detailImage2?serviceKey={key}&{q}", timeout=30).read())
            except urllib.error.HTTPError as e:  # 429 = 오늘 한도 초과
                print(f"HTTP {e.code} → 멈춤 ({len(rows)}곳까지 집계, 받은 원문은 저장됨)"); sys.exit(0)
            if d.get("response", {}).get("header", {}).get("resultCode") != "0000":
                print("한도·오류로 멈춤:", json.dumps(d, ensure_ascii=False)[:160]); print(json.dumps(rows, ensure_ascii=False)); sys.exit(0)
            f.write_text(json.dumps(d, ensure_ascii=False))
        d = json.loads(f.read_text())
        its = (d["response"]["body"].get("items") or {}).get("item") or []
        its = [its] if isinstance(its, dict) else its
        row["menu" if yn == "N" else "extra"] = len(its)
        row[("menu" if yn == "N" else "extra") + "_lic"] = sorted({i.get("cpyrhtDivCd") for i in its})
        row[("menu" if yn == "N" else "extra") + "_names"] = [i.get("imgname") for i in its][:4]
    rows.append(row)
n = len(rows)
print(f"조사 {n}곳")
print(f"메뉴 사진 있음: {sum(r['menu'] > 0 for r in rows)}곳 ({sum(r['menu'] for r in rows)}장)")
print(f"추가 사진 있음: {sum(r['extra'] > 0 for r in rows)}곳 ({sum(r['extra'] for r in rows)}장)")
print(f"대표사진(목록) 있음: {sum(r['first'] for r in rows)}곳")
for r in rows:
    if r["menu"] or r["extra"]: print(r["name"], "| 메뉴", r["menu"], r["menu_lic"], r["menu_names"], "| 추가", r["extra"], r["extra_lic"], r["extra_names"])
json.dump(rows, open(OUT / "_summary.json", "w"), ensure_ascii=False, indent=1)
