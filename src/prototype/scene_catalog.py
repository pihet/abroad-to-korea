"""해외 장면 카탈로그 v1 (HANDOFF 11장) → CLIP 임베딩 → 장면 단위 국내 추천과 성능 확인.

입력: data/external/overseas_scenes_v1_20261002.csv 의 qa_status=ok 사진 (383장)
단계:
    download   썸네일(640px)을 data/interim/clip/scenes/<scene_id>__<photo_rank>.jpg 로 받는다
    embed      CLIP 임베딩 → data/interim/clip/emb_scenes.npz
    recommend  장면마다 국내 추천 상위 5개 시군구 + 근거 관광지 3곳 → data/interim/clip/scene_recs.csv
    evaluate   정답 쌍 해외지 중 카탈로그에 있는 곳으로 Hit@k (원본·정리 세트와 같은 해외지로 비교)

실행: .venv/bin/python src/prototype/scene_catalog.py [단계 ...]
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import clip_proto as cp

SCENES_CSV = cp.ROOT / "data/external/overseas_scenes_v1_20261002.csv"
PLACES_CSV = cp.ROOT / "data/external/overseas_places_v1_20261002.csv"
IMG_DIR = cp.WORK / "scenes"
EMB = cp.WORK / "emb_scenes.npz"
VOTE_K = 100
TOP_N = 5


def ok_rows() -> pd.DataFrame:
    s = pd.read_csv(SCENES_CSV)
    s = s[s.qa_status == "ok"].copy()
    s["file"] = s.scene_id + "__" + s.photo_rank.astype(str) + ".jpg"
    return s


def step_download():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    s = ok_rows()
    with ThreadPoolExecutor(max_workers=4) as ex:
        ok = list(ex.map(lambda r: cp.download(r[0], IMG_DIR / r[1]), zip(s.thumb_url_640, s.file)))
    print(f"[download] {sum(ok)}/{len(ok)}장")
    for f, good in zip(s.file, ok):
        if not good:
            print("  실패:", f)


def step_embed():
    import torch
    from transformers import CLIPModel, CLIPProcessor

    torch.set_num_threads(12)
    model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
    proc = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
    paths = sorted(IMG_DIR.glob("*.jpg"))
    vecs, kept = cp.embed_files(paths, model, proc)
    np.savez(EMB, vecs=vecs, names=np.array([p.name for p in kept]))
    print(f"[embed] {len(kept)}장")


def domestic_index():
    """국내 관광지 사진 임베딩과 시군구 단위 인덱스 (clip_proto 평가와 같은 방식)."""
    unit_of = cp.load_regions()
    items = {i["contentid"]: i for i in cp.load_attractions()}
    kr = np.load(cp.WORK / "emb_kr.npz")
    region_idx = defaultdict(list)
    for k, cid in enumerate(kr["names"]):
        it = items.get(str(cid))
        if it and (it["lDongRegnCd"], it["lDongSignguCd"]) in unit_of:
            u = unit_of[(it["lDongRegnCd"], it["lDongSignguCd"])]
            region_idx[(u[0], u[2])].append(k)
    regions = sorted(region_idx)
    rpos = {r: i for i, r in enumerate(regions)}
    img_region = np.full(len(kr["vecs"]), -1)
    for r, ix in region_idx.items():
        img_region[ix] = rpos[r]
    name = {(u[0], u[2]): f"{u[1]} {u[2]}" for u in unit_of.values()}
    reg_mean = np.stack([kr["vecs"][region_idx[r]].mean(0) for r in regions])
    reg_mean /= np.linalg.norm(reg_mean, axis=1, keepdims=True)
    return {"kv": kr["vecs"], "cid": kr["names"], "items": items, "regions": regions, "rpos": rpos,
            "img_region": img_region, "name": name, "reg_mean": reg_mean}


def vote_scores(I, v):
    """vote100: 전국 관광지 사진 상위 100장의 유사도를 시군구별로 합산 (표 없는 지역은 평균 임베딩으로 순서)."""
    sims = I["kv"] @ v
    top = np.argsort(-sims)[:VOTE_K]
    top = top[I["img_region"][top] >= 0]
    s = np.bincount(I["img_region"][top], weights=sims[top], minlength=len(I["regions"]))
    return s + 1e-3 * (I["reg_mean"] @ v), sims, top


def scene_vectors():
    e = np.load(EMB)
    by_scene = defaultdict(list)
    for v, n in zip(e["vecs"], e["names"]):
        by_scene[str(n).rsplit("__", 1)[0]].append(v)
    return {k: (np.mean(vs, 0) / np.linalg.norm(np.mean(vs, 0))) for k, vs in by_scene.items()}, by_scene


def step_recommend():
    I = domestic_index()
    qv, _ = scene_vectors()
    s = ok_rows().drop_duplicates("scene_id").set_index("scene_id")
    places = pd.read_csv(PLACES_CSV).set_index("place_id")
    rows, appear = [], Counter()
    for sid, v in qv.items():
        sc, sims, top = vote_scores(I, v)
        order = np.argsort(-sc)[:TOP_N]
        for rank, ri in enumerate(order, 1):
            r = I["regions"][ri]
            # 근거 관광지: 이 시군구에 속한 상위 사진 중 유사도 높은 3곳
            ev = [i for i in top if I["img_region"][i] == ri][:3]
            ev_names = [I["items"][str(I["cid"][i])]["title"] for i in ev]
            rows.append({"scene_id": sid, "place_id": s.loc[sid, "place_id"],
                         "place_ko": places.loc[s.loc[sid, "place_id"], "name_ko"],
                         "scene_label_ko": s.loc[sid, "scene_label_ko"], "rank": rank,
                         "sigungu": I["name"][r], "score": round(float(sc[ri]), 3),
                         "evidence": " / ".join(ev_names), "top_sim": round(float(sims[ev[0]]), 3) if ev else None})
            appear[I["name"][r]] += 1
    out = pd.DataFrame(rows)
    out.to_csv(cp.WORK / "scene_recs.csv", index=False, encoding="utf-8-sig")
    n_scene = out.scene_id.nunique()
    no_ev = out[(out["rank"] == 1) & (out.evidence == "")]
    print(f"[recommend] 장면 {n_scene}개 × 상위 {TOP_N} → {len(out)}행 (scene_recs.csv)")
    print(f"  1위에 근거 관광지가 없는 장면: {len(no_ev)}개")
    print(f"  상위 {TOP_N}에 한 번이라도 나온 시군구: {len(appear)}개 / {len(I['regions'])}개")
    print("  가장 자주 나온 시군구 (장면 수): " + ", ".join(f"{k} {v}" for k, v in appear.most_common(10)))
    top_share = sum(v for _, v in appear.most_common(10)) / len(out)
    print(f"  상위 10개 시군구가 전체 추천 칸의 {top_share:.0%}")


def step_evaluate():
    I = domestic_index()
    qv, by_scene = scene_vectors()
    s = ok_rows()
    scenes_of = s.groupby("place_id").scene_id.unique().to_dict()

    # 정답 (clip_proto 와 같은 규칙)
    name_to_region = defaultdict(list)
    for r in I["regions"]:
        name_to_region[r[1]].append(r)
    gt = defaultdict(set)
    for f in cp.GT_FILES:
        for row in csv.DictReader(open(f, encoding="utf-8")):
            if row["use_for_eval"] != "1":
                continue
            for sg in row["sigungu"].split("|"):
                c = name_to_region[sg]
                if len(c) > 1:
                    c = [r for r in c if I["name"][r].startswith(row["sido"])]
                gt[row["overseas_id"]].update(I["rpos"][r] for r in c)
    places = [p for p in gt if gt[p] and p in scenes_of]
    n = len(I["regions"])

    def best_rank(sc, targets):
        pos = np.empty(n, int)
        pos[np.argsort(-sc)] = np.arange(1, n + 1)
        return min(pos[t] for t in targets)

    res = {"카탈로그: 여행지 전체 사진 평균": {}, "카탈로그: 가장 잘 맞는 장면": {}}
    for p in places:
        vs = [v for sid in scenes_of[p] for v in by_scene.get(sid, [])]
        pv = np.mean(vs, 0) / np.linalg.norm(np.mean(vs, 0))
        res["카탈로그: 여행지 전체 사진 평균"][p] = int(best_rank(vote_scores(I, pv)[0], gt[p]))
        res["카탈로그: 가장 잘 맞는 장면"][p] = int(min(best_rank(vote_scores(I, qv[sid])[0], gt[p])
                                         for sid in scenes_of[p] if sid in qv))
    for label, fname in [("원본 세트 (8장, 직접 고른 검색어)", "eval_results.json"),
                         ("정리 세트 (7장 P2 정리본)", "eval_results_curated.json")]:
        br = json.loads((cp.WORK / fname).read_text())["methods"]["vote100"]["best_ranks"]
        res[label] = {p: int(br[p]) for p in places}

    ks = (5, 10, 20)
    rand = {k: sum(1 - np.prod([(n - len(gt[p]) - i) / (n - i) for i in range(k)]) for p in places) for k in ks}
    print(f"[evaluate] 정답 해외지 {len(places)}곳 (카탈로그에 있는 곳만), 국내 {n}개 시군구, 방법 vote100")
    print("랜덤 기대: " + " / ".join(f"Hit@{k} {rand[k]:.2f}" for k in ks))
    print("| 질의 사진 | Hit@5 | Hit@10 | Hit@20 | MRR | 순위 중앙값 | 최악 |\n|---|---|---|---|---|---|---|")
    for label, br in res.items():
        r = np.array(list(br.values()))
        print(f"| {label} | {(r <= 5).sum()} | {(r <= 10).sum()} | {(r <= 20).sum()} | {np.mean(1 / r):.3f} | {np.median(r):.0f} | {r.max()} |")
    print("\n| 해외지 | 장면 수 | " + " | ".join(res) + " |")
    print("|---|---|" + "---|" * len(res))
    for p in places:
        print(f"| {p} | {len(scenes_of[p])} | " + " | ".join(str(res[k][p]) for k in res) + " |")
    (cp.WORK / "eval_results_scenes.json").write_text(json.dumps(
        {"places": places, "random": {k: float(v) for k, v in rand.items()}, "best_ranks": res}, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ 쏠림(hubness) 보정
CSLS_K = 10       # B: 국내 사진마다 가장 가까운 기준 장면 수 (표준값, 결과를 보기 전에 고정)
PRIOR_LAMBDA = 1  # A: 시군구 기본 점수를 몇 배 뺄지 (표준값, 결과를 보기 전에 고정)


def corrected_scores(I, v, ref, method, cache):
    """method: none / prior(A: 시군구 기본 점수 빼기) / csls(B: 사진 단위 CSLS). ref = 기준 장면 벡터 (정답 정보 없음)."""
    if method == "none":
        return vote_scores(I, v)[0]
    if method == "prior":
        key = ("prior", ref.shape[0], float(ref[:, 0].sum()))
        if key not in cache:  # 기준 장면들에 대한 시군구별 평균 vote 점수
            cache[key] = np.mean([vote_scores(I, r)[0] for r in ref], 0)
        return vote_scores(I, v)[0] - PRIOR_LAMBDA * cache[key]
    if method == "csls":
        key = ("csls", ref.shape[0], float(ref[:, 0].sum()))
        if key not in cache:  # 국내 사진마다 가장 가까운 기준 장면 K개와의 평균 유사도
            S = I["kv"] @ ref.T
            k = min(CSLS_K, S.shape[1])
            cache[key] = np.sort(S, axis=1)[:, -k:].mean(1)
        sims = 2 * (I["kv"] @ v) - cache[key]
        top = np.argsort(-sims)[:VOTE_K]
        top = top[I["img_region"][top] >= 0]
        s = np.bincount(I["img_region"][top], weights=sims[top] - sims[top].min() + 1e-6, minlength=len(I["regions"]))
        return s + 1e-3 * (I["reg_mean"] @ v)
    raise ValueError(method)


def step_hubness():
    I = domestic_index()
    qv, by_scene = scene_vectors()
    sids = sorted(qv)
    place_of = {sid: sid.split("__")[0] for sid in sids}
    s = ok_rows()
    scenes_of = s.groupby("place_id").scene_id.unique().to_dict()
    n = len(I["regions"])
    cache = {}
    methods = {"none": "C. 보정 없음", "prior": "A. 시군구 기본 점수 빼기", "csls": "B. 사진 단위 CSLS"}

    # 1) 쏠림 지표: 장면 213개 전체 (기준 = 자기 자신을 뺀 나머지 장면, 정답 미사용)
    print("[쏠림] 장면 213개의 상위 5 추천")
    print("| 방식 | 상위 5에 나온 시군구 수 | 상위 10개 시군구 비중 | 가장 많이 나온 시군구 (장면 수) |\n|---|---|---|---|")
    hub = {}
    all_ref = np.stack([qv[x] for x in sids])
    for m, label in methods.items():
        appear = Counter()
        for sid in sids:
            # 같은 여행지 장면은 기준에서 뺀다
            ref = all_ref[[place_of[x] != place_of[sid] for x in sids]]
            sc = corrected_scores(I, qv[sid], ref, m, cache)
            for ri in np.argsort(-sc)[:TOP_N]:
                appear[I["name"][I["regions"][ri]]] += 1
        share = sum(v for _, v in appear.most_common(10)) / (len(sids) * TOP_N)
        hub[m] = {"n_regions": len(appear), "top10_share": share, "most": appear.most_common(5)}
        print(f"| {label} | {len(appear)} / {n} | {share:.0%} | " + ", ".join(f"{k.split()[-1]} {v}" for k, v in appear.most_common(5)) + " |")

    # 2) 정확도: 정답 20곳, 여행지 전체 사진 평균 질의, 기준 = 그 여행지 장면을 뺀 나머지
    name_to_region = defaultdict(list)
    for r in I["regions"]:
        name_to_region[r[1]].append(r)
    gt = defaultdict(set)
    for f in cp.GT_FILES:
        for row in csv.DictReader(open(f, encoding="utf-8")):
            if row["use_for_eval"] != "1":
                continue
            for sg in row["sigungu"].split("|"):
                c = name_to_region[sg]
                if len(c) > 1:
                    c = [r for r in c if I["name"][r].startswith(row["sido"])]
                gt[row["overseas_id"]].update(I["rpos"][r] for r in c)
    places = [p for p in gt if gt[p] and p in scenes_of]
    acc = {}
    print(f"\n[정확도] 정답 해외지 {len(places)}곳, 여행지 전체 사진 평균 질의, 기준 장면에서 평가 여행지 제외")
    print("| 방식 | Hit@5 | Hit@10 | Hit@20 | MRR | 순위 중앙값 | 최악 |\n|---|---|---|---|---|---|---|")
    for m, label in methods.items():
        ranks = {}
        for p in places:
            vs = [v for sid in scenes_of[p] for v in by_scene.get(sid, [])]
            pv = np.mean(vs, 0) / np.linalg.norm(np.mean(vs, 0))
            ref = all_ref[[place_of[x] != p for x in sids]]
            sc = corrected_scores(I, pv, ref, m, cache)
            pos = np.empty(n, int)
            pos[np.argsort(-sc)] = np.arange(1, n + 1)
            ranks[p] = int(min(pos[t] for t in gt[p]))
        r = np.array(list(ranks.values()))
        acc[m] = ranks
        print(f"| {label} | {(r <= 5).sum()} | {(r <= 10).sum()} | {(r <= 20).sum()} | {np.mean(1 / r):.3f} | {np.median(r):.0f} | {r.max()} |")
    print("\n| 해외지 | " + " | ".join(methods.values()) + " |\n|---|" + "---|" * len(methods))
    for p in places:
        print(f"| {p} | " + " | ".join(str(acc[m][p]) for m in methods) + " |")
    (cp.WORK / "eval_hubness.json").write_text(json.dumps(
        {"csls_k": CSLS_K, "prior_lambda": PRIOR_LAMBDA, "hubness": hub, "best_ranks": acc}, ensure_ascii=False, indent=1))


STEPS = {"download": step_download, "embed": step_embed, "recommend": step_recommend, "evaluate": step_evaluate,
         "hubness": step_hubness}

if __name__ == "__main__":
    for name in sys.argv[1:] or list(STEPS):
        STEPS[name]()
