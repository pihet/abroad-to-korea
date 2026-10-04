"""탐색 서비스 v2: 사진으로 닮은 후보 20곳을 사용자 조건으로 다시 정렬한다 (2단계 추천).

1단계 닮음: 서비스 기본값(CLIP B/32, 시군구 vote100, 대표사진 풀) 상위 20곳
2단계 조건: 덜 붐비게(10월 혼잡도) / 가깝게(출발지 거리) / 날씨 좋게(10월 쾌적도) / 관심사(관광지 분류 수)
    점수(결과 전에 고정): 닮음 = 후보 20곳 안 순위의 0~1 값, 조건 = 후보 20곳 안 백분위
    조건 1개: 0.5·닮음 + 0.5·조건 / 조건 + 관심사: 0.4·닮음 + 0.3·조건 + 0.3·관심사
    축제(2026년 10월)는 점수에 넣지 않고 정보로만 보여 준다

실행:
    .venv/bin/python src/prototype/build_explore_conditions.py evaluate          # 조건 반영 효과 (오프라인)
    .venv/bin/python src/prototype/build_explore_conditions.py artifact <경로>   # 단일 파일 페이지 (사진 base64)
    .venv/bin/python src/prototype/build_explore_conditions.py site <폴더>       # 페이지 + 묶음 이미지 WebP (선명한 사진)
"""

import base64
import io
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import clip_proto as cp
import make_demo_page as demo
import scene_catalog as sc

sys.path.insert(0, str(cp.ROOT / "src/collect"))
from region_context import CLIMATE_DIR, region_centers  # noqa: E402

N_CAND = 20
SHOW = 10
FESTIVALS = cp.ROOT / "data/raw/tourapi/searchFestival2_20261001_20261031.json"
ORIGINS = {"서울": (37.5665, 126.9780), "부산": (35.1796, 129.0756), "대구": (35.8714, 128.6014),
           "광주": (35.1595, 126.8526), "대전": (36.3504, 127.3845)}
INTERESTS = {"NA": "자연", "HS": "역사", "VE": "문화·도시", "EX": "체험·휴식"}
COMFORT = (15.0, 24.0)  # 쾌적 기온 범위(°C)
MONTH = 10


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def region_features(I):
    """시군구 인덱스 → 조건 특징."""
    unit_of = cp.load_regions()
    centers = region_centers()
    # 관심사: 관광지 분류 수 (사진 유무와 무관하게 전체 관광지)
    counts = defaultdict(Counter)
    for p in sorted(cp.RAW_TOUR.glob("page_*.json")):
        for it in json.loads(p.read_text())["response"]["body"]["items"]["item"]:
            u = unit_of.get((it["lDongRegnCd"], it["lDongSignguCd"]))
            if u and it.get("lclsSystm1") in INTERESTS:
                counts[(u[0], u[2])][it["lclsSystm1"]] += 1
    # 축제
    fest = defaultdict(list)
    for it in json.loads(FESTIVALS.read_text())["response"]["body"]["items"]["item"]:
        u = unit_of.get((it["lDongRegnCd"], it["lDongSignguCd"]))
        if u:
            fest[(u[0], u[2])].append({"title": it["title"], "start": it["eventstartdate"], "end": it["eventenddate"]})
    # 혼잡도 (10월 예측)
    pred, recent = demo.monthly_forecast(demo.TARGET_MONTH)
    code_names = demo.visit_code_names()
    rows = [{"sido_code": r[0], "region": I["name"][r]} for r in I["regions"]]
    cong = demo.congestion_for(rows, pred, recent, code_names)
    feats = {}
    for k, r in enumerate(I["regions"]):
        key = (r[0], r[1])
        clim = None
        f = CLIMATE_DIR / f"archive_{r[0]}_{r[1]}.json"
        if f.exists():
            d = json.loads(f.read_text())["daily"]
            sel = [i for i, t in enumerate(d["time"]) if t[:4] >= "2021" and int(t[5:7]) == MONTH]
            temps = [d["temperature_2m_mean"][i] for i in sel if d["temperature_2m_mean"][i] is not None]
            rains = [d["precipitation_sum"][i] for i in sel if d["precipitation_sum"][i] is not None]
            years = len({d["time"][i][:4] for i in sel})
            if temps and years:
                t = float(np.mean(temps))
                rain_days = sum(x >= 1.0 for x in rains) / years
                pen = max(0.0, COMFORT[0] - t, t - COMFORT[1])
                clim = {"temp": round(t, 1), "rain_days": round(rain_days, 1), "comfort": round(-(pen + 0.5 * rain_days), 2)}
        c = centers.get(key)
        feats[k] = {
            "congestion": None if cong[k]["index"] is None else round(cong[k]["index"]),
            "visitors_10k": None if cong[k]["pred"] is None else round(cong[k]["pred"] / 10000, 1),
            "dist": {o: (None if c is None else round(haversine(c, xy))) for o, xy in ORIGINS.items()},
            "climate": clim,
            "interest": {k2: counts[key].get(k2, 0) for k2 in INTERESTS},
            "festivals": sorted(fest.get(key, []), key=lambda x: x["start"])[:3],
            "n_festivals": len(fest.get(key, [])),
        }
    return feats


def candidates(I, v):
    v = v / np.linalg.norm(v)
    scores, sims, _ = sc.vote_scores(I, v)
    out = []
    for ri in np.argsort(-scores, kind="stable")[:N_CAND]:
        idx = np.where(I["img_region"] == ri)[0]
        best = idx[np.argmax(sims[idx])]
        it = I["items"][str(I["cid"][best])]
        out.append({"ri": int(ri), "title": it["title"], "kogl": demo.KOGL.get(it["cpyrhtDivCd"], it["cpyrhtDivCd"]),
                    "img": f"img/kr/{it['contentid']}.jpg"})
    return out


def place_vectors():
    qv, by_scene = sc.scene_vectors()
    rows = sc.ok_rows()
    scenes_of = rows.groupby("place_id").scene_id.unique().to_dict()
    he = np.load(sc.cp.WORK / "emb_scenes_holdout.npz")
    extra = defaultdict(list)
    for v, pid in zip(he["vecs"], he["place_ids"]):
        extra[str(pid)].append(v)
    return {p: np.mean([v for sid in s for v in by_scene.get(sid, [])] + extra.get(p, []), 0)
            for p, s in scenes_of.items()}


# ------------------------------------------------------------------ 조건 점수 (페이지 JS 와 같은 식)
def rerank(cands, feats, priority=None, origin="서울", interest=None):
    n = len(cands)
    sim = {c["ri"]: 1 - i / (n - 1) for i, c in enumerate(cands)}

    def pct(vals):  # 높을수록 좋은 값 → 후보 안 백분위 (결측은 0.5)
        ok = [v for v in vals.values() if v is not None]
        return {k: 0.5 if v is None else (sum(x < v for x in ok) + 0.5 * (sum(x == v for x in ok) - 1)) / max(1, len(ok) - 1)
                for k, v in vals.items()}

    def cond(p):
        f = {c["ri"]: feats[c["ri"]] for c in cands}
        if p == "crowd":
            return pct({k: None if x["congestion"] is None else -x["congestion"] for k, x in f.items()})
        if p == "near":
            return pct({k: None if x["dist"][origin] is None else -x["dist"][origin] for k, x in f.items()})
        if p == "weather":
            return pct({k: None if x["climate"] is None else x["climate"]["comfort"] for k, x in f.items()})
        return pct({k: x["interest"][p] for k, x in f.items()})

    if priority is None and interest is None:
        return list(cands)
    score = {}
    for c in cands:
        k = c["ri"]
        if priority and interest:
            score[k] = 0.4 * sim[k] + 0.3 * cond(priority)[k] + 0.3 * cond(interest)[k]
        else:
            score[k] = 0.5 * sim[k] + 0.5 * cond(priority or interest)[k]
    return sorted(cands, key=lambda c: -score[c["ri"]])


def step_evaluate():
    I = sc.domestic_index()
    feats = region_features(I)
    pv = place_vectors()
    have_clim = sum(f["climate"] is not None for f in feats.values())
    print(f"시군구 {len(feats)}개 (10월 날씨 있는 곳 {have_clim}개, 혼잡도 있는 곳 "
          f"{sum(f['congestion'] is not None for f in feats.values())}개), 해외지 {len(pv)}곳")
    cands = {p: candidates(I, v) for p, v in pv.items()}

    def avg(vals):
        vals = [x for x in vals if x is not None]
        return float(np.mean(vals)) if vals else float("nan")

    print("| 조건 | 상위 5 평균 지표: 기본 → 조건 반영 | 기본 상위 5 유지율 | 새로 올라온 후보의 원래 순위 (평균) |")
    print("|---|---|---|---|")
    tests = [("덜 붐비게", "crowd", None, lambda f: f["congestion"], "혼잡도"),
             ("가깝게 (서울 출발)", "near", None, lambda f: f["dist"]["서울"], "거리 km"),
             ("날씨 좋게", "weather", None, lambda f: None if f["climate"] is None else f["climate"]["comfort"], "쾌적도"),
             ("관심사: 자연", None, "NA", lambda f: f["interest"]["NA"], "자연 관광지 수"),
             ("관심사: 역사", None, "HS", lambda f: f["interest"]["HS"], "역사 관광지 수")]
    out = {}
    for label, pr, it, metric, unit in tests:
        b, a, keep, new_rank = [], [], [], []
        for p, cs in cands.items():
            base5 = cs[:5]
            new5 = rerank(cs, feats, pr, "서울", it)[:5]
            b.append(avg(metric(feats[c["ri"]]) for c in base5))
            a.append(avg(metric(feats[c["ri"]]) for c in new5))
            ids = {c["ri"] for c in base5}
            keep.append(sum(c["ri"] in ids for c in new5) / 5)
            orig = {c["ri"]: i + 1 for i, c in enumerate(cs)}
            new_rank += [orig[c["ri"]] for c in new5 if c["ri"] not in ids]
        out[label] = {"before": avg(b), "after": avg(a), "keep_top5": float(np.mean(keep)),
                      "new_from_rank": float(np.mean(new_rank)) if new_rank else None}
        print(f"| {label} | {unit} {avg(b):.1f} → {avg(a):.1f} | {np.mean(keep):.0%} | "
              f"{'—' if not new_rank else f'{np.mean(new_rank):.1f}위'} |")
    (cp.WORK / "eval_conditions.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


SPRITE_W, SPRITE_H = 2048, 2048


def build_sprites(entries, out_dir, quality=78):
    """사진을 묶음 이미지(WebP)에 선반식으로 채운다. 각 사진은 비율 유지 축소만 하고 자르지 않는다.
    entries: [(src, 원본 경로, 최대 변)] → ({src: [묶음 번호, x, y, w, h]}, [{"file", "w", "h"}])"""
    from PIL import Image
    out_dir.mkdir(parents=True, exist_ok=True)
    pos, sheets, cur, x, y, row_h, n = {}, [], None, 0, 0, 0, 0

    def flush():
        nonlocal cur
        if cur is not None:
            used_h = y + row_h
            f = f"sheets/s{len(sheets):02d}.webp"
            cur.crop((0, 0, SPRITE_W, used_h)).save(out_dir.parent / f, "WEBP", quality=quality, method=5)
            sheets.append({"file": f, "w": SPRITE_W, "h": used_h})
            cur = None
    for src, path, side in entries:
        im = Image.open(path).convert("RGB")
        im.thumbnail((side, side))
        w, h = im.size
        if cur is None:
            cur, x, y, row_h = Image.new("RGB", (SPRITE_W, SPRITE_H), (255, 255, 255)), 0, 0, 0
        if x + w > SPRITE_W:
            x, y, row_h = 0, y + row_h, 0
        if y + h > SPRITE_H:
            flush()
            cur, x, y, row_h = Image.new("RGB", (SPRITE_W, SPRITE_H), (255, 255, 255)), 0, 0, 0
        cur.paste(im, (x, y))
        pos[src] = [len(sheets), x, y, w, h]
        x, row_h, n = x + w, max(row_h, h), n + 1
    flush()
    return pos, sheets


def step_artifact(path, kr_side=200, scene_side=300, quality=65, sprite=False):
    import build_explore_site as ex
    from PIL import Image
    I = sc.domestic_index()
    feats = region_features(I)
    pv = place_vectors()
    base = ex.build_data()  # 해외지 이름·장면 사진·저작자
    pool = {}
    order = {}  # 묶음 이미지 모드: 처음 쓰인 순서대로 (src → 최대 변)
    dirs = {"img/kr": cp.KR_DIR, "img/scenes": sc.IMG_DIR, "img/holdout": cp.WORK / "scenes_holdout"}

    def ref(src, side):
        if sprite:
            order.setdefault(src, side)
            return src
        if src not in pool:
            folder, name = src.rsplit("/", 1)
            d = {"img/kr": cp.KR_DIR, "img/scenes": sc.IMG_DIR, "img/holdout": cp.WORK / "scenes_holdout"}[folder]
            im = Image.open(d / name).convert("RGB")
            im.thumbnail((side, side))  # 비율 유지 축소만
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality)
            pool[src] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        return src

    # 해외 사진별 벡터 (짝 맞추기용)
    pvec = {}
    for f in (sc.EMB, cp.WORK / "emb_scenes_holdout.npz"):
        e = np.load(f)
        for v, n in zip(e["vecs"], e["names"]):
            pvec[str(n)] = v
    cid_index = {str(c): i for i, c in enumerate(I["cid"])}
    for p in base["places"]:  # 첫 화면 갤러리 사진을 앞 묶음에 모은다
        ref(p["scenes"][0]["photos"][0]["src"], scene_side)
    used = set()
    places = []
    for p in base["places"]:
        cs = candidates(I, pv[p["id"]])
        photos = []
        for x in p["scenes"]:
            for f in x["photos"]:
                photos.append({"img": ref(f["src"], scene_side), "scene": x["label"], "vec": pvec[f["src"].rsplit("/", 1)[1]],
                               **{k: f[k] for k in ("artist", "license", "license_url", "page")}})
        P = np.stack([ph.pop("vec") for ph in photos])
        for c in cs:
            ref(c["img"], kr_side)
            used.add(c["ri"])
            kv = I["kv"][cid_index[c["img"].rsplit("/", 1)[1][:-4]]]
            c["pair"] = int(np.argmax(P @ kv))  # 이 국내 사진과 가장 닮은 해외 사진
        places.append({"id": p["id"], "name": p["name"], "name_en": p["name_en"], "country": p["country"],
                       "tags": p["tags"], "photos": photos, "cands": cs})
    regions = {ri: {"name": I["name"][I["regions"][ri]], **feats[ri]} for ri in used}
    data = {"month": f"2026년 {MONTH}월", "origins": list(ORIGINS), "interests": INTERESTS, "comfort": COMFORT,
            "places": places, "regions": regions}
    path = Path(path)
    if sprite:
        entries = [(src, dirs[src.rsplit("/", 1)[0]] / src.rsplit("/", 1)[1], side) for src, side in order.items()]
        data["img"], data["sheets"] = build_sprites(entries, path.parent / "sheets")
        page = PAGE_V3.replace("/*DATA*/", "window.DATA = " + json.dumps(data, ensure_ascii=False) + ";")
        path.write_text(page, encoding="utf-8")
        total = sum((path.parent / s_["file"]).stat().st_size for s_ in data["sheets"])
        print(f"완료: 해외 {len(places)}곳, 후보 시군구 {len(regions)}개, 사진 {len(order)}장 → 묶음 {len(data['sheets'])}개 "
              f"{total / 1e6:.1f}MB, 페이지 {path.stat().st_size / 1e6:.2f}MB → {path}")
        return
    data["img"] = pool
    page = PAGE.replace("/*DATA*/", "window.DATA = " + json.dumps(data, ensure_ascii=False) + ";")
    path.write_text(page, encoding="utf-8")
    print(f"완료: 해외 {len(places)}곳, 후보 시군구 {len(regions)}개, 사진 {len(pool)}장, "
          f"{path.stat().st_size / 1e6:.1f}MB → {path}")


PAGE = (Path(__file__).parent / "templates/explore_v2.html").read_text(encoding="utf-8")
PAGE_V3 = (Path(__file__).parent / "templates/explore_v3.html").read_text(encoding="utf-8")

if __name__ == "__main__":
    if sys.argv[1] == "evaluate":
        step_evaluate()
    elif sys.argv[1] == "site":  # 묶음 이미지(WebP) + 페이지: <폴더>/index.html, <폴더>/sheets/*.webp
        out = Path(sys.argv[2])
        step_artifact(out / "index.html", kr_side=420, scene_side=560, sprite=True)
    else:
        step_artifact(sys.argv[2])
