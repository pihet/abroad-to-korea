"""국내 관광지 추가 사진(detailImage2)으로 국내 사진 풀을 늘리고 개발셋 38곳에서 시군구 vote100 을 다시 평가한다.

단계
    download  data/raw/tourapi/detailImage2/*.json 에서 공공누리 1·3유형 사진을 관광지당 최대 5장
              (대표사진과 같은 파일은 제외) → data/interim/clip/kr_extra/<contentid>__<n>.jpg (긴 변 400px)
    embed     → data/interim/clip/emb_kr_extra.npz
    evaluate  기존 풀(대표사진 11,353장) vs 늘린 풀(대표사진 + 추가 사진)로 개발셋 38곳 C(vote100) 비교

실행: .venv/bin/python src/prototype/kr_extra.py [단계 ...]
"""

import io
import json
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from math import comb

import numpy as np

import clip_proto as cp
import holdout_pilot as hp
import reverify_dev as rd
import scene_catalog as sc

RAW = cp.ROOT / "data/raw/tourapi/detailImage2"
IMG_DIR = cp.WORK / "kr_extra"
EMB = cp.WORK / "emb_kr_extra.npz"
PER_ATTRACTION = 5
MAX_SIDE = 400


def selected():
    """(contentid, 순번, url) 목록. 공공누리 1·3유형, 대표사진 파일 제외, 관광지당 최대 5장."""
    first = {}
    for p in sorted(cp.RAW_TOUR.glob("page_*.json")):
        for it in json.loads(p.read_text())["response"]["body"]["items"]["item"]:
            first[it["contentid"]] = (it.get("firstimage") or "").rsplit("/", 1)[-1].split("_")[0]
    out = []
    for f in sorted(RAW.glob("*.json")):
        body = json.loads(f.read_text())["response"]["body"]
        items = body["items"]["item"] if body.get("items") else []
        cid, n = f.stem, 0
        for x in items:
            if x.get("cpyrhtDivCd") not in ("Type1", "Type3"):
                continue
            if x["originimgurl"].rsplit("/", 1)[-1].split("_")[0] == first.get(cid):
                continue  # 대표사진과 같은 원본
            out.append((cid, n, x.get("smallimageurl") or x["originimgurl"]))
            n += 1
            if n >= PER_ATTRACTION:
                break
    return out


def step_download():
    from PIL import Image
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    rows = selected()

    def get(r):
        cid, n, url = r
        path = IMG_DIR / f"{cid}__{n}.jpg"
        if path.exists():
            return True
        try:
            req = urllib.request.Request(url, headers={"User-Agent": cp.UA})
            im = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=60).read())).convert("RGB")
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            im.save(path, quality=88)
            return True
        except Exception:
            return False
    with ThreadPoolExecutor(max_workers=8) as ex:
        ok = list(ex.map(get, rows))
    n_attr = len({r[0] for r in rows})
    print(f"[download] 관광지 {n_attr}곳, 사진 {sum(ok)}/{len(ok)}장")


def step_embed():
    import torch
    from transformers import CLIPModel, CLIPProcessor
    torch.set_num_threads(12)
    model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
    proc = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
    paths = sorted(IMG_DIR.glob("*.jpg"))
    vecs, kept = cp.embed_files(paths, model, proc)
    np.savez(EMB, vecs=vecs, names=np.array([p.stem for p in kept]))
    print(f"[embed] {len(kept)}장")


def enlarged_index(I):
    """기존 인덱스에 추가 사진을 붙인다. 추가 사진의 시군구는 관광지 목록 원본에서 찾는다."""
    unit_of = cp.load_regions()
    region_of_cid = {}
    for p in sorted(cp.RAW_TOUR.glob("page_*.json")):
        for it in json.loads(p.read_text())["response"]["body"]["items"]["item"]:
            u = unit_of.get((it["lDongRegnCd"], it["lDongSignguCd"]))
            if u and (u[0], u[2]) in I["rpos"]:
                region_of_cid[it["contentid"]] = I["rpos"][(u[0], u[2])]
    e = np.load(EMB)
    cids = np.array([str(n).split("__")[0] for n in e["names"]])
    reg = np.array([region_of_cid.get(c, -1) for c in cids])
    J = dict(I)
    J["kv"] = np.vstack([I["kv"], e["vecs"]])
    J["cid"] = np.concatenate([np.array([str(c) for c in I["cid"]]), cids])
    J["img_region"] = np.concatenate([I["img_region"], reg])
    # 시군구 평균 임베딩도 늘린 풀로 다시 계산 (vote100 의 동점 정렬용)
    m = np.zeros_like(I["reg_mean"])
    for k in range(len(I["regions"])):
        m[k] = J["kv"][J["img_region"] == k].mean(0)
    J["reg_mean"] = m / np.linalg.norm(m, axis=1, keepdims=True)
    return J, int((reg >= 0).sum())


def step_evaluate():
    I = sc.domestic_index()
    J, n_extra = enlarged_index(I)
    qv, by_scene = sc.scene_vectors()
    rows = sc.ok_rows()
    scenes_of = rows.groupby("place_id").scene_id.unique().to_dict()
    he = np.load(hp.HOLDOUT_EMB)
    extra = {}
    for v, pid in zip(he["vecs"], he["place_ids"]):
        extra.setdefault(str(pid), []).append(v)
    gt, _ = hp.load_gt(I, rd.DEV_FILES + [hp.HOLDOUT_GT])
    places = [p for p in gt if gt[p] and p in scenes_of]
    n = len(I["regions"])
    enriched_regions = Counter(J["img_region"][len(I["kv"]):][J["img_region"][len(I["kv"]):] >= 0])

    def vote_attraction_max(X, v):
        """관광지마다 가장 닮은 사진 1장만 쓰고, 상위 100개 관광지의 유사도를 시군구별로 합산."""
        sims = X["kv"] @ v
        ok = X["img_region"] >= 0
        cids, inv = np.unique(X["cid"][ok], return_inverse=True)
        best = np.full(len(cids), -np.inf)
        np.maximum.at(best, inv, sims[ok])
        reg = np.zeros(len(cids), int)
        reg[inv] = X["img_region"][ok]
        top = np.argsort(-best)[:sc.VOTE_K]
        s = np.bincount(reg[top], weights=best[top], minlength=len(X["regions"]))
        return s + 1e-3 * (X["reg_mean"] @ v)

    variants = [("기존 풀 (대표사진)", I, sc.vote_scores), ("늘린 풀 (대표사진 + 추가 사진)", J, sc.vote_scores),
                ("기존 풀 · 관광지 최대값 투표", I, vote_attraction_max),
                ("늘린 풀 · 관광지 최대값 투표", J, vote_attraction_max)]
    res, top5 = {}, {}
    for label, X, fn in variants:
        ranks, appear = {}, Counter()
        for p in places:
            vs = [v for sid in scenes_of[p] for v in by_scene.get(sid, [])] + extra.get(p, [])
            v = np.mean(vs, 0)
            v /= np.linalg.norm(v)
            s = fn(X, v)
            s = s[0] if isinstance(s, tuple) else s
            order = np.argsort(-s, kind="stable")
            pos = np.empty(n, int)
            pos[order] = np.arange(1, n + 1)
            ranks[p] = int(min(pos[t] for t in gt[p]))
            appear.update(I["name"][I["regions"][i]] for i in order[:5])
        res[label], top5[label] = ranks, appear

    print(f"[evaluate] 개발셋 {len(places)}곳, 국내 {n}개 시군구, 방법 C(vote100)")
    print(f"  추가 사진 {n_extra}장 → 사진을 얻은 시군구 {len(enriched_regions)}개 "
          f"(시군구당 중앙값 {int(np.median(list(enriched_regions.values())))}장)")
    print("| 국내 사진 풀 | 사진 수 | Hit@5 | Hit@10 | Hit@20 | MRR | 중앙 | 최악 | 상위5 시군구 수 | 상위10 점유율 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for label, X, _ in variants:
        r = np.array([res[label][p] for p in places])
        share = sum(v for _, v in top5[label].most_common(10)) / (len(places) * 5)
        print(f"| {label} | {int((X['img_region'] >= 0).sum())} | {(r <= 5).sum()} | {(r <= 10).sum()} | {(r <= 20).sum()} | "
              f"{np.mean(1 / r):.3f} | {np.median(r):.0f} | {r.max()} | {len(top5[label])} | {share:.0%} |")
    a = np.array([res["기존 풀 (대표사진)"][p] for p in places])
    for label, _, _ in variants[1:]:
        b = np.array([res[label][p] for p in places])
        better, worse = int((b < a).sum()), int((b > a).sum())
        k, m = min(better, worse), better + worse
        pv = 1.0 if m == 0 else min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m)
        print(f"  {label} vs 기존 풀: 좋아짐 {better} / 나빠짐 {worse} / 같음 {len(places) - better - worse} (p={pv:.2f})")
    print("\n| 해외지 | " + " | ".join(l for l, _, _ in variants) + " |\n|---|" + "---|" * len(variants))
    for p in places:
        print(f"| {p} | " + " | ".join(str(res[l][p]) for l, _, _ in variants) + " |")
    (cp.WORK / "eval_kr_extra.json").write_text(json.dumps(
        {"n_extra": n_extra, "places": places, "ranks": res}, ensure_ascii=False, indent=1))


STEPS = {"download": step_download, "embed": step_embed, "evaluate": step_evaluate}

if __name__ == "__main__":
    for s in sys.argv[1:] or list(STEPS):
        STEPS[s]()
