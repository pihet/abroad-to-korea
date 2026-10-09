"""CLIP 프로토타입: 해외 여행지 사진으로 질의했을 때 정답 시군구가 상위에 오는지 확인한다.

단계 (각 단계 결과는 data/interim/clip/ 에 캐시되어, 다시 실행하면 건너뛴다):
    1. kr_images     TourAPI 관광지 대표사진(공공누리 1·3유형) 썸네일 다운로드
    2. ov_images     Wikimedia Commons 에서 해외 여행지 사진 다운로드 (CC / 퍼블릭 도메인만)
    3. embed         CLIP 이미지 임베딩 계산
    4. evaluate      정답 쌍(use_for_eval=1)으로 Hit@k 측정, 랜덤 기준선과 비교

실행:
    .venv/bin/python src/model/clip_proto.py            # 전체
    .venv/bin/python src/model/clip_proto.py evaluate   # 평가만 다시

필요 패키지 (프로토타입 전용, requirements.txt 미반영): torch(CPU), transformers, pillow
"""

import csv
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW_TOUR = ROOT / "data/raw/tourapi/areaBasedList2_ct12_20261002"
LDONG = ROOT / "data/raw/tourapi/ldongCode2_list_20261002.json"
GT_FILES = [ROOT / "data/external/ground_truth_pairs.csv",
            ROOT / "data/external/ground_truth_pairs_candidates_20261002.csv"]  # 후보(HANDOFF 9-1)는 병합 전이라 따로 읽는다
WORK = ROOT / "data/interim/clip"
KR_DIR = WORK / "kr"
# 해외 질의 사진 세트: 기본은 원본, CLIP_OV_SET=curated 면 수동 정리본 (curate_overseas.py)
OV_SET = os.environ.get("CLIP_OV_SET", "")
OV_DIR = WORK / ("overseas_curated" if OV_SET == "curated" else "overseas")
OV_SUFFIX = "_curated" if OV_SET == "curated" else ""
MODEL_NAME = "openai/clip-vit-base-patch32"
UA = "samsung-project2-clip-prototype/0.1 (education project)"
OV_PER_PLACE = 8
RANDOM_SEED = 42
FIXED_N = 20          # top3_fixed: 지역당 고정 샘플 수
SAMPLE_REPEATS = 20   # top3_fixed: 반복 횟수
VOTE_K = 100          # vote: 전체에서 뽑을 상위 사진 수

# 해외 사진 검색어. 해당 여행지의 대표 경관이 나오도록 직접 정했다 (선정 편향 있음).
OVERSEAS_QUERIES = {
    "kyoto": "Kyoto temple garden",
    "naples": "Naples bay Vesuvius",
    "santorini": "Santorini Oia",
    "grandcanyon": "Grand Canyon South Rim",
    "interlaken": "Lauterbrunnen valley",
    "pyla": "Dune du Pilat",
    "vik": "Vik Iceland black sand beach",
    "uyuni": "Salar de Uyuni",
    "kotakinabalu": "Kota Kinabalu beach",
    "honolulu": "Waikiki beach Diamond Head",
    "niagara": "Niagara Falls",
    # HANDOFF 9-1 후보 정답 쌍의 새 질의 12곳
    "zhangjiajie": "Zhangjiajie National Forest Park",
    "serengeti": "Serengeti plains",
    "maldives": "Maldives island beach",
    "halong": "Ha Long Bay",
    "galapagos": "Galapagos Islands landscape",
    "etretat": "Etretat cliffs",
    "sahara_merzouga": "Erg Chebbi dunes Merzouga",
    "giants_causeway": "Giant's Causeway",
    "machupicchu": "Machu Picchu",
    "cinqueterre": "Cinque Terre Vernazza",
    "montmartre": "Montmartre street",
    "brooklyn": "Brooklyn street",
}
ORIGINAL_11 = ["kyoto", "naples", "santorini", "grandcanyon", "interlaken", "pyla", "vik", "uyuni",
               "kotakinabalu", "honolulu", "niagara"]


# ---------------------------------------------------------------- 지역 단위
def load_regions():
    """법정동 시군구 코드 → 분석 단위 (시도코드, 시군구명 첫 단어). '전주시 완산구' → '전주시'."""
    items = json.loads(LDONG.read_text())["response"]["body"]["items"]["item"]
    unit = {}
    for x in items:
        unit[(x["lDongRegnCd"], x["lDongSignguCd"])] = (x["lDongRegnCd"], x["lDongRegnNm"], x["lDongSignguNm"].split()[0])
    return unit


def load_attractions():
    items = []
    for p in sorted(RAW_TOUR.glob("page_*.json")):
        items += json.loads(p.read_text())["response"]["body"]["items"]["item"]
    return [i for i in items if i.get("firstimage2") and i.get("cpyrhtDivCd") in ("Type1", "Type3")]


# ---------------------------------------------------------------- 1. 국내 사진
def download(url, path):
    if path.exists():
        return True
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                path.write_bytes(r.read())
            return True
        except Exception:
            time.sleep(2 * (attempt + 1))
    return False


def step_kr_images():
    KR_DIR.mkdir(parents=True, exist_ok=True)
    items = load_attractions()
    jobs = [(i["firstimage2"], KR_DIR / f'{i["contentid"]}.jpg') for i in items]
    with ThreadPoolExecutor(max_workers=8) as ex:
        ok = list(ex.map(lambda j: download(*j), jobs))
    print(f"[kr_images] {sum(ok)}/{len(ok)}장 확보")


# ---------------------------------------------------------------- 2. 해외 사진
def commons_search(query, limit=40):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size", "iiurlwidth": 512,
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    pages = json.load(urllib.request.urlopen(req, timeout=60)).get("query", {}).get("pages", {})
    return sorted(pages.values(), key=lambda p: p.get("index", 0))


def step_ov_images():
    OV_DIR.mkdir(parents=True, exist_ok=True)
    attr = OV_DIR / "attribution.json"
    meta = json.loads(attr.read_text()) if attr.exists() else []
    bad_name = re.compile(r"map|logo|flag|diagram|plan|chart|stamp|coat|seal", re.I)
    for oid, query in OVERSEAS_QUERIES.items():
        got = 0
        if sum(m["overseas_id"] == oid for m in meta) >= OV_PER_PLACE:
            continue  # 이미 받은 여행지
        for p in commons_search(query):
            if got >= OV_PER_PLACE:
                break
            ii = p["imageinfo"][0]
            em = ii.get("extmetadata", {})
            lic = em.get("LicenseShortName", {}).get("value", "")
            if ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 800 or bad_name.search(p["title"]):
                continue
            if not (lic.startswith("CC") or "Public domain" in lic):
                continue
            path = OV_DIR / f"{oid}_{got}.jpg"
            if download(ii["thumburl"], path):
                artist = re.sub("<[^>]+>", "", em.get("Artist", {}).get("value", ""))[:80]
                meta.append({"overseas_id": oid, "file": path.name, "title": p["title"], "license": lic,
                             "artist": artist, "page": ii.get("descriptionurl", "")})
                got += 1
            time.sleep(0.3)
        print(f"[ov_images] {oid}: {got}장")
    attr.write_text(json.dumps(meta, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- 3. 임베딩
def embed_files(paths, model, processor, batch=64):
    import torch
    from PIL import Image

    vecs, kept = [], []
    for s in range(0, len(paths), batch):
        imgs, names = [], []
        for p in paths[s:s + batch]:
            try:
                imgs.append(Image.open(p).convert("RGB"))
                names.append(p)
            except Exception:
                pass
        if not imgs:
            continue
        with torch.no_grad():
            inputs = processor(images=imgs, return_tensors="pt")
            out = model.get_image_features(**inputs)
            # transformers 버전에 따라 텐서 대신 출력 객체가 올 수 있다
            f = out if isinstance(out, torch.Tensor) else out.pooler_output
        f = torch.nn.functional.normalize(f, dim=-1).numpy()
        vecs.append(f)
        kept += names
        if (s // batch) % 20 == 0:
            print(f"  {s + len(imgs)}/{len(paths)}", flush=True)
    return np.concatenate(vecs), kept


def step_embed():
    import torch
    from transformers import CLIPModel, CLIPProcessor

    torch.set_num_threads(12)
    model = CLIPModel.from_pretrained(MODEL_NAME).eval()
    processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    for name, d in [("overseas" + OV_SUFFIX, OV_DIR), ("kr", KR_DIR)]:
        out = WORK / f"emb_{name}.npz"
        if out.exists():
            print(f"[embed] {name} 캐시 사용")
            continue
        paths = sorted(d.glob("*.jpg"))
        t = time.time()
        vecs, kept = embed_files(paths, model, processor)
        np.savez(out, vecs=vecs, names=np.array([p.stem for p in kept]))
        print(f"[embed] {name}: {len(kept)}장, {time.time() - t:.0f}초")


# ---------------------------------------------------------------- 4. 평가
def step_evaluate():
    unit_of = load_regions()
    items = {i["contentid"]: i for i in load_attractions()}
    kr = np.load(WORK / "emb_kr.npz")
    ov = np.load(WORK / f"emb_overseas{OV_SUFFIX}.npz")

    # 지역별 이미지 인덱스
    region_idx = defaultdict(list)
    for k, cid in enumerate(kr["names"]):
        it = items.get(str(cid))
        if it and (it["lDongRegnCd"], it["lDongSignguCd"]) in unit_of:
            u = unit_of[(it["lDongRegnCd"], it["lDongSignguCd"])]
            region_idx[(u[0], u[2])].append(k)
    regions = sorted(region_idx)
    region_name = {(u[0], u[2]): f"{u[1]} {u[2]}" for u in unit_of.values()}
    kv = kr["vecs"]
    reg_mean = np.stack([kv[region_idx[r]].mean(0) for r in regions])
    reg_mean /= np.linalg.norm(reg_mean, axis=1, keepdims=True)
    n_img = np.array([len(region_idx[r]) for r in regions])
    print(f"[evaluate] 국내 지역 {len(regions)}개, 이미지 {len(kv)}장 (지역당 중앙값 {int(np.median(n_img))})")

    # 해외 질의 벡터 = 해당 여행지 사진 평균
    q = defaultdict(list)
    for k, name in enumerate(ov["names"]):
        q[str(name).rsplit("_", 1)[0]].append(k)
    qv = {oid: ov["vecs"][ix].mean(0) / np.linalg.norm(ov["vecs"][ix].mean(0)) for oid, ix in q.items()}

    # 정답 쌍: 해외 id → 정답 지역 집합
    name_to_region = defaultdict(list)
    for r in regions:
        name_to_region[r[1]].append(r)
    gt = defaultdict(set)
    rows = [r for f in GT_FILES for r in csv.DictReader(open(f, encoding="utf-8"))]
    n_pairs = sum(r["use_for_eval"] == "1" for r in rows)
    for row in rows:
        if row["use_for_eval"] != "1":
            continue
        for sg in row["sigungu"].split("|"):
            cands = name_to_region[sg]
            if len(cands) > 1:  # 이름이 겹치는 시군구(예: 남구)는 시도로 구분
                cands = [r for r in cands if region_name[r].startswith(row["sido"])]
            if not cands:
                print(f"  경고: 정답 지역을 찾지 못함 {row['pair_id']} {row['sido']} {sg}")
            gt[row["overseas_id"]].update(cands)

    sample_rng = np.random.default_rng(RANDOM_SEED)
    # 크기 편향 제거용: 지역마다 최대 FIXED_N장을 SAMPLE_REPEATS번 무작위 추출해 둔다
    samples = [[sample_rng.choice(region_idx[r], size=min(FIXED_N, len(region_idx[r])), replace=False)
                for r in regions] for _ in range(SAMPLE_REPEATS)]

    def top3(sims, idx_lists):
        return np.array([np.sort(sims[ix])[-3:].mean() for ix in idx_lists])

    def scores(method, v):
        sims = kv @ v
        if method == "mean":  # 지역 평균 임베딩과 코사인
            return reg_mean @ v
        if method == "top3":  # 지역 내 상위 3장 유사도 평균 (사진 많은 지역이 유리)
            return top3(sims, [region_idx[r] for r in regions])
        if method == f"top3_fixed{FIXED_N}":  # 지역당 FIXED_N장 고정 샘플에서 top3, 반복 평균
            return np.mean([top3(sims, smp) for smp in samples], axis=0)
        if method == f"vote{VOTE_K}":  # 전체 관광지 사진 중 상위 VOTE_K장의 유사도를 지역별로 합산
            top = np.argsort(-sims)[:VOTE_K]
            vote = defaultdict(float)
            for i in top:
                vote[img_region[i]] += sims[i]
            # 표를 못 받은 지역끼리는 평균 임베딩 유사도로 순서를 정한다
            return np.array([vote.get(r, 0.0) for r in regions]) + 1e-3 * (reg_mean @ v)
        raise ValueError(method)

    img_region = {}
    for r, ix in region_idx.items():
        for i in ix:
            img_region[i] = r

    ks = (5, 10, 20)
    methods = ["mean", "top3", f"top3_fixed{FIXED_N}", f"vote{VOTE_K}"]
    queries = [oid for oid in gt if gt[oid] and oid in qv]
    n = len(regions)
    rand = {k: sum(1 - np.prod([(n - len(gt[o]) - i) / (n - i) for i in range(k)]) for o in queries) for k in ks}
    summary = {}
    for method in methods:
        print(f"\n== 방법: {method} ==")
        best_ranks = {}
        mean_scores = np.zeros(n)
        for oid in queries:
            s = scores(method, qv[oid])
            mean_scores += s / len(queries)
            order = list(np.argsort(-s))
            ranks = sorted(order.index(regions.index(t)) + 1 for t in gt[oid])
            best_ranks[oid] = ranks[0]
            top5 = ", ".join(region_name[regions[i]].split()[-1] for i in order[:5])
            print(f"  {oid:13s} 정답 {','.join(t[1] for t in gt[oid]):28s} 최고순위 {ranks[0]:4d}/{n}  상위5: {top5}")
        hits = {k: sum(r <= k for r in best_ranks.values()) for k in ks}
        mrr = float(np.mean([1 / r for r in best_ranks.values()]))
        rho = np.corrcoef(np.argsort(np.argsort(n_img)), np.argsort(np.argsort(mean_scores)))[0, 1]
        print("  " + " / ".join(f"Hit@{k} {hits[k]}/{len(queries)}" for k in ks) + f" / MRR {mrr:.3f} / 사진수 순위상관 {rho:.2f}")
        for label, qs in [("기존 11", [q for q in queries if q in ORIGINAL_11]),
                          ("신규", [q for q in queries if q not in ORIGINAL_11])]:
            if qs:
                br = [best_ranks[q] for q in qs]
                print(f"    └ {label} {len(qs)}개: " + " / ".join(f"Hit@{k} {sum(r <= k for r in br)}" for k in ks)
                      + f" / MRR {np.mean([1 / r for r in br]):.3f}")
        summary[method] = {"hits": hits, "mrr": mrr, "size_rho": float(rho), "best_ranks": best_ranks}

    print(f"\n정답 쌍 {n_pairs}개, 질의 {len(queries)}개")
    print(f"랜덤 기대: " + " / ".join(f"Hit@{k} {rand[k]:.2f}" for k in ks))
    print("\n| 방법 | Hit@5 | Hit@10 | Hit@20 | MRR | 사진수 순위상관 |")
    print("|---|---|---|---|---|---|")
    for m, r in summary.items():
        print(f"| {m} | {r['hits'][5]} | {r['hits'][10]} | {r['hits'][20]} | {r['mrr']:.3f} | {r['size_rho']:.2f} |")
    (WORK / f"eval_results{OV_SUFFIX}.json").write_text(json.dumps(
        {"n_regions": n, "n_queries": len(queries), "random": rand, "methods": summary}, ensure_ascii=False, indent=1))


STEPS = {"kr_images": step_kr_images, "ov_images": step_ov_images, "embed": step_embed, "evaluate": step_evaluate}

if __name__ == "__main__":
    names = sys.argv[1:] or list(STEPS)
    for n in names:
        STEPS[n]()
