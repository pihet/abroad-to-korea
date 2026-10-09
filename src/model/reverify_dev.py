"""CLIP 재검증 (개발셋만): HANDOFF 11-4 의 dev 정답(41쌍 + 국내 정답 보강 4쌍, 해외지 23곳).

홀드아웃(ground_truth_holdout_new_v1)은 11-4 평가 순서에 따라 여기서 열지 않는다.

비교: C CLIP 단독(vote100) / A 시군구 기본 점수 빼기 / B 사진 단위 CSLS / 카테고리 재정렬(대표 1개, 가중치 0.4)
지표: Hit@5/10/20, MRR, 중앙·최악 순위, 부트스트랩 95% 구간, C 대비 부호검정, 장면 213개 쏠림

실행: .venv/bin/python src/model/reverify_dev.py
결과: data/interim/clip/eval_reverify_dev.json
"""

import csv
import json
from collections import Counter, defaultdict
from math import comb

import numpy as np

import category_rerank as cr
import clip_proto as cp
import scene_catalog as sc

DEV_FILES = [cp.ROOT / "data/external/ground_truth_dev_v1_20261002.csv",
             cp.ROOT / "data/external/ground_truth_dev_label_additions_v1_20261002.csv"]
CAT_WEIGHT = 0.4
BOOT = 2000
SEED = 42


def load_dev_gt(I):
    name_to_region = defaultdict(list)
    for r in I["regions"]:
        name_to_region[r[1]].append(r)
    gt, n_pairs = defaultdict(set), 0
    for f in DEV_FILES:
        for row in csv.DictReader(open(f, encoding="utf-8")):
            if row["use_for_eval"] != "1":
                continue
            n_pairs += 1
            for sg in row["sigungu"].split("|"):
                c = name_to_region[sg]
                if len(c) > 1:  # 이름이 겹치는 시군구만 시도로 구분
                    c = [r for r in c if I["name"][r].startswith(row["sido"])]
                if not c:
                    print(f"  경고: 정답 지역을 찾지 못함 {row['pair_id']} {row['sido']} {sg}")
                gt[row["overseas_id"]].update(I["rpos"][r] for r in c)
    return gt, n_pairs


def sign_test(better, worse):
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def main():
    I = sc.domestic_index()
    qv, by_scene = sc.scene_vectors()
    rows = sc.ok_rows()
    scenes_of = rows.groupby("place_id").scene_id.unique().to_dict()
    place_of_scene = rows.drop_duplicates("scene_id").set_index("scene_id").place_id.to_dict()
    sids = sorted(qv)
    all_ref = np.stack([qv[x] for x in sids])
    gt, n_pairs = load_dev_gt(I)
    places = [p for p in gt if gt[p] and p in scenes_of]
    n = len(I["regions"])

    cats_of, _ = cr.place_categories()
    cat_names, text_vecs = cr.category_text_vectors()
    cat_scores = cr.domestic_category_scores(I, text_vecs)
    cache = {}

    def scores(method, v, place):
        ref = all_ref[[place_of_scene[x] != place for x in sids]]  # 같은 여행지 장면은 기준에서 뺀다
        if method == "cat":
            return cr.combine_scores(sc.vote_scores(I, v)[0], cats_of.get(place, [])[:1], cat_names, cat_scores, CAT_WEIGHT)
        return sc.corrected_scores(I, v, ref, method, cache)

    methods = {"none": "C. CLIP 단독 (vote100)", "prior": "A. 시군구 기본 점수 빼기",
               "csls": "B. 사진 단위 CSLS", "cat": f"카테고리 재정렬 (대표 1개, {CAT_WEIGHT})"}
    ranks = {}
    for m in methods:
        ranks[m] = {}
        for p in places:
            vs = [v for sid in scenes_of[p] for v in by_scene.get(sid, [])]
            pv = np.mean(vs, 0) / np.linalg.norm(np.mean(vs, 0))
            pos = np.empty(n, int)
            pos[np.argsort(-scores(m, pv, p), kind="stable")] = np.arange(1, n + 1)
            ranks[m][p] = int(min(pos[t] for t in gt[p]))

    ks = (5, 10, 20)
    rand = {k: sum(1 - np.prod([(n - len(gt[p]) - i) / (n - i) for i in range(k)]) for p in places) for k in ks}
    rng = np.random.default_rng(SEED)
    boot_idx = rng.integers(0, len(places), size=(BOOT, len(places)))
    print(f"[개발셋] 해외지 {len(places)}곳, 정답 {n_pairs}쌍, 국내 {n}개 시군구 (홀드아웃은 열지 않음)")
    print("랜덤 기대: " + " / ".join(f"Hit@{k} {rand[k]:.2f}" for k in ks))
    print("| 방식 | Hit@5 (95% 구간) | Hit@10 (95% 구간) | Hit@20 | MRR (95% 구간) | 중앙 | 최악 | C 대비 좋아짐/나빠짐 (p) |")
    print("|---|---|---|---|---|---|---|---|")
    summary = {}
    base = np.array([ranks["none"][p] for p in places])
    for m, label in methods.items():
        r = np.array([ranks[m][p] for p in places])
        rb = r[boot_idx]
        ci = lambda x: (np.percentile(x, 2.5), np.percentile(x, 97.5))
        h5, h10, mrr = ci((rb <= 5).mean(1)), ci((rb <= 10).mean(1)), ci((1 / rb).mean(1))
        better, worse = int((r < base).sum()), int((r > base).sum())
        p = sign_test(better, worse)
        summary[m] = {"hit5": int((r <= 5).sum()), "hit10": int((r <= 10).sum()), "hit20": int((r <= 20).sum()),
                      "mrr": float(np.mean(1 / r)), "median": float(np.median(r)), "worst": int(r.max()),
                      "better": better, "worse": worse, "sign_p": p,
                      "ci": {"hit5": h5, "hit10": h10, "mrr": mrr}}
        cmp_ = "—" if m == "none" else f"{better}/{worse} (p={p:.2f})"
        print(f"| {label} | {(r <= 5).sum()} ({h5[0]:.0%}~{h5[1]:.0%}) | {(r <= 10).sum()} ({h10[0]:.0%}~{h10[1]:.0%}) | "
              f"{(r <= 20).sum()} | {np.mean(1 / r):.3f} ({mrr[0]:.2f}~{mrr[1]:.2f}) | {np.median(r):.0f} | {r.max()} | {cmp_} |")

    print("\n| 해외지 | 정답 수 | " + " | ".join(methods.values()) + " |\n|---|---|" + "---|" * len(methods))
    for p in places:
        print(f"| {p} | {len(gt[p])} | " + " | ".join(str(ranks[m][p]) for m in methods) + " |")

    # 쏠림: 장면 213개 상위 5
    print("\n| 방식 | 상위 5에 나온 시군구 | 상위 10개 비중 |\n|---|---|---|")
    hub = {}
    for m, label in methods.items():
        appear = Counter()
        for sid in sids:
            for ri in np.argsort(-scores(m, qv[sid], place_of_scene[sid]), kind="stable")[:sc.TOP_N]:
                appear[I["name"][I["regions"][ri]]] += 1
        share = sum(v for _, v in appear.most_common(10)) / (len(sids) * sc.TOP_N)
        hub[m] = {"n_regions": len(appear), "top10_share": float(share)}
        print(f"| {label} | {len(appear)} / {n} | {share:.0%} |")

    (cp.WORK / "eval_reverify_dev.json").write_text(json.dumps(
        {"split": "dev", "places": places, "n_pairs": n_pairs, "random": {k: float(v) for k, v in rand.items()},
         "summary": summary, "best_ranks": ranks, "hubness": hub}, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
