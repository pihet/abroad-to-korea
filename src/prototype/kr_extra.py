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


def enlarged_index(I, drop=None):
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
    if drop is not None:
        reg = np.where(drop, -1, reg)  # 거른 사진은 어느 시군구에도 표를 주지 않는다
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
    variants = [("기존 풀 (대표사진)", I, sc.vote_scores), ("늘린 풀 (대표사진 + 추가 사진)", J, sc.vote_scores),
                ("기존 풀 · 관광지 최대값 투표", I, vote_attraction_max),
                ("늘린 풀 · 관광지 최대값 투표", J, vote_attraction_max)]
    compare(I, J, n_extra, variants, "eval_kr_extra.json")


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


def compare(I, J, n_extra, variants, out_name):
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
    a = np.array([res[variants[0][0]][p] for p in places])  # 첫 후보가 기준
    for label, _, _ in variants[1:]:
        b = np.array([res[label][p] for p in places])
        better, worse = int((b < a).sum()), int((b > a).sum())
        k, m = min(better, worse), better + worse
        pv = 1.0 if m == 0 else min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m)
        print(f"  {label} vs {variants[0][0]}: 좋아짐 {better} / 나빠짐 {worse} / 같음 {len(places) - better - worse} (p={pv:.2f})")
    print("\n| 해외지 | " + " | ".join(l for l, _, _ in variants) + " |\n|---|" + "---|" * len(variants))
    for p in places:
        print(f"| {p} | " + " | ".join(str(res[l][p]) for l, _, _ in variants) + " |")
    (cp.WORK / out_name).write_text(json.dumps(
        {"n_extra": n_extra, "places": places, "ranks": res}, ensure_ascii=False, indent=1))


def step_subset():
    """공정 비교: detailImage2 를 받은 관광지만으로 국내 풀을 한정하고, 같은 관광지 집합에서
    A(대표사진만) vs B(대표사진 + 추가 사진)를 비교한다. 차이는 관광지당 사진 장수뿐이다.
    판정 기준 (결과 전에 정함): 개발셋 38곳에서 B 가 A 보다 Hit@10 +4곳 이상이고 MRR 상승이면 "효과 있음".
    """
    I = sc.domestic_index()
    J, _ = enlarged_index(I)
    fetched = {f.stem for f in RAW.glob("*.json")}
    n_base = len(I["kv"])
    cid_all = J["cid"]

    def restrict(X, keep):
        Y = dict(X)
        Y["kv"], Y["cid"], Y["img_region"] = X["kv"][keep], X["cid"][keep], X["img_region"][keep]
        n = len(X["regions"])
        m = np.zeros((n, X["kv"].shape[1]))
        has = np.zeros(n, bool)
        for k in range(n):
            sel = Y["img_region"] == k
            if sel.any():
                m[k], has[k] = Y["kv"][sel].mean(0), True
        Y["reg_mean"] = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
        Y["has_region"] = has
        return Y

    in_subset = np.isin(cid_all, list(fetched)) & (J["img_region"] >= 0)
    A = restrict(J, in_subset & (np.arange(len(cid_all)) < n_base))   # 대표사진만
    B = restrict(J, in_subset)                                         # 대표 + 추가
    # 추가 사진만 있고 대표사진이 없는 관광지는 B 에서 뺀다 (두 조건의 관광지 집합을 같게)
    keep_b = np.isin(B["cid"], list(set(A["cid"])))
    B = restrict(B, keep_b)
    assert set(A["cid"]) == set(B["cid"]), "두 조건의 관광지 집합이 다르다"

    def vote(X, v, attraction_max):
        sims = X["kv"] @ v
        if attraction_max:  # 관광지마다 가장 닮은 사진 1장만 투표
            cids, inv = np.unique(X["cid"], return_inverse=True)
            best = np.full(len(cids), -np.inf)
            np.maximum.at(best, inv, sims)
            reg = np.zeros(len(cids), int)
            reg[inv] = X["img_region"]
            top = np.argsort(-best)[:sc.VOTE_K]
            s = np.bincount(reg[top], weights=best[top], minlength=len(X["regions"]))
        else:
            top = np.argsort(-sims)[:sc.VOTE_K]
            s = np.bincount(X["img_region"][top], weights=sims[top], minlength=len(X["regions"]))
        s = s + 1e-3 * (X["reg_mean"] @ v)
        return np.where(X["has_region"], s, -np.inf)

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
    gt_covered = sum(any(A["has_region"][t] for t in gt[p]) for p in places)

    res = {}
    for label, X, am in [("A 대표사진만", A, False), ("B 대표+추가", B, False),
                         ("A 대표사진만 · 관광지 최대값", A, True), ("B 대표+추가 · 관광지 최대값", B, True)]:
        ranks = {}
        for p in places:
            vs = [v for sid in scenes_of[p] for v in by_scene.get(sid, [])] + extra.get(p, [])
            v = np.mean(vs, 0)
            v /= np.linalg.norm(v)
            pos = np.empty(n, int)
            pos[np.argsort(-vote(X, v, am), kind="stable")] = np.arange(1, n + 1)
            ranks[p] = int(min(pos[t] for t in gt[p]))
        res[label] = ranks

    n_attr = len(set(A["cid"]))
    print(f"[subset] 관광지 {n_attr}곳 (시군구 {int(A['has_region'].sum())}개), 사진 A {len(A['kv'])}장 / B {len(B['kv'])}장")
    print(f"  개발셋 {len(places)}곳 중 정답 시군구에 관광지가 남아 있는 곳: {gt_covered}")
    print("| 조건 | Hit@5 | Hit@10 | Hit@20 | MRR | 중앙 | 최악 | A 대비 좋아짐/나빠짐/같음 (p) | 판정 |")
    print("|---|---|---|---|---|---|---|---|---|")
    pairs = {"B 대표+추가": "A 대표사진만", "B 대표+추가 · 관광지 최대값": "A 대표사진만 · 관광지 최대값"}
    out = {}
    for label, ranks in res.items():
        r = np.array([ranks[p] for p in places])
        s = {"hit5": int((r <= 5).sum()), "hit10": int((r <= 10).sum()), "hit20": int((r <= 20).sum()),
             "mrr": float(np.mean(1 / r)), "median": float(np.median(r)), "worst": int(r.max())}
        cmp_, verdict = "—", "—"
        if label in pairs:
            b = np.array([res[pairs[label]][p] for p in places])
            better, worse = int((r < b).sum()), int((r > b).sum())
            k, m = min(better, worse), better + worse
            pv = 1.0 if m == 0 else min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m)
            cmp_ = f"{better}/{worse}/{len(places) - better - worse} ({pv:.2f})"
            verdict = "효과 있음" if s["hit10"] - int((b <= 10).sum()) >= 4 and s["mrr"] > float(np.mean(1 / b)) else "기준 미달"
        out[label] = {**s, "verdict": verdict}
        print(f"| {label} | {s['hit5']} | {s['hit10']} | {s['hit20']} | {s['mrr']:.3f} | {s['median']:.0f} | {s['worst']} | {cmp_} | {verdict} |")
    print("\n| 해외지 | " + " | ".join(res) + " |\n|---|" + "---|" * len(res))
    for p in places:
        print(f"| {p} | " + " | ".join(str(res[l][p]) for l in res) + " |")
    (cp.WORK / "eval_kr_extra_subset.json").write_text(json.dumps(
        {"n_attractions": n_attr, "summary": out, "ranks": res}, ensure_ascii=False, indent=1))


# 추가 사진 거르기 규칙 (C). 2026-10-08 결과를 보기 전에 고정: 사진마다 아래 문구 중 가장 가까운 것을 고르고,
# 버릴 쪽이면 뺀다. 대표사진은 건드리지 않는다.
KEEP_PROMPTS = ["a landscape photo", "a photo of a building exterior", "a photo of a street", "a photo of a beach or sea",
                "a photo of mountains or forest", "a photo of a traditional village", "a photo of a park or garden"]
DROP_PROMPTS = ["a photo of food on a table", "a photo of an indoor room", "a photo of a sign or text board",
                "a portrait photo of people", "a photo of a museum exhibit", "a photo of a map or brochure"]


def filter_mask():
    """추가 사진마다 버릴지(True) 정한다. (버린 이유별 개수도 함께)"""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
    proc = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
    prompts = KEEP_PROMPTS + DROP_PROMPTS
    with torch.no_grad():
        t = model.get_text_features(**proc(text=prompts, return_tensors="pt", padding=True))
        t = t if isinstance(t, torch.Tensor) else t.pooler_output
    T = torch.nn.functional.normalize(t, dim=-1).numpy()
    e = np.load(EMB)
    best = np.argmax(e["vecs"] @ T.T, axis=1)
    drop = best >= len(KEEP_PROMPTS)
    why = Counter(prompts[i] for i in best[drop])
    return drop, why


def step_filtered():
    """A(대표사진) vs B(늘린 풀) vs C(늘린 풀에서 실내·음식·안내판 등을 거른 풀)."""
    I = sc.domestic_index()
    drop, why = filter_mask()
    print(f"[filtered] 추가 사진 {len(drop)}장 중 {int(drop.sum())}장({drop.mean():.0%}) 거름: " +
          ", ".join(f"{k.replace('a photo of ', '').replace('a ', '')} {v}" for k, v in why.most_common()))
    J, n_extra = enlarged_index(I)
    K, n_kept = enlarged_index(I, drop)
    variants = [("A 기존 풀 (대표사진)", I, sc.vote_scores), ("B 늘린 풀", J, sc.vote_scores),
                ("C 늘린 풀 · 거름", K, sc.vote_scores),
                ("B 늘린 풀 · 관광지 최대값", J, vote_attraction_max), ("C 늘린 풀 · 거름 · 관광지 최대값", K, vote_attraction_max)]
    compare(I, K, n_kept, variants, "eval_kr_extra_filtered.json")


STEPS = {"download": step_download, "embed": step_embed, "evaluate": step_evaluate, "subset": step_subset,
         "filtered": step_filtered}

if __name__ == "__main__":
    for s in sys.argv[1:] or list(STEPS):
        STEPS[s]()
