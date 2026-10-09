"""홀드아웃 15곳 파일럿 평가 (HANDOFF 11-5 지시서, Aside → Claude Code).

이 평가를 실행하면 신규 15곳은 개발셋으로 전환된다. 결과를 보고 설정을 바꾸지 않는다.

입력
    정답: ground_truth_holdout_new_v1_20261002.csv (15쌍, 해외지 15곳)
    질의: 해외지의 카탈로그 qa_status=ok 사진 + 보강 사진(emb_scenes_holdout.npz) 전체 평균
    국내: 기존 vote100 (국내 임베딩 재사용)
방법 (설정 고정)
    C  CLIP 단독 (vote100)
    A  시군구 기본 점수 빼기 (scene_catalog.PRIOR_LAMBDA=1, 기준 = 카탈로그 장면, 평가 해외지 장면 제외)
    K  CLIP + 대표 카테고리 1개, 가중치 0.4 (category_rerank 설정 그대로)
비교용으로 개발셋 23곳(reverify_dev 와 같은 정답)도 같은 지표로 다시 계산한다.

실행: .venv/bin/python src/model/holdout_pilot.py
결과: data/interim/clip/eval_holdout_pilot.json
"""

import csv
import json
from collections import Counter, defaultdict
from math import comb

import numpy as np

import category_rerank as cr
import clip_proto as cp
import reverify_dev as rd
import scene_catalog as sc

HOLDOUT_GT = cp.ROOT / "data/external/ground_truth_holdout_new_v1_20261002.csv"
HOLDOUT_EMB = cp.WORK / "emb_scenes_holdout.npz"
CAT_WEIGHT = 0.4
URBAN = {"hongkong", "singapore", "tokyo", "bangkok", "taipei", "beijing"}  # 지시서의 도시 야경·거리 정답
WATCH = ["제주특별자치도 제주시", "제주특별자치도 서귀포시", "서울특별시 종로구"]


def load_gt(I, files):
    name_to_region = defaultdict(list)
    for r in I["regions"]:
        name_to_region[r[1]].append(r)
    gt, label = defaultdict(set), defaultdict(list)
    for f in files:
        for row in csv.DictReader(open(f, encoding="utf-8")):
            if row["use_for_eval"] != "1":
                continue
            for sg in row["sigungu"].split("|"):
                c = name_to_region[sg]
                if len(c) > 1:
                    c = [r for r in c if I["name"][r].startswith(row["sido"])]
                if not c:
                    print(f"  경고: 정답 지역을 찾지 못함 {row['pair_id']} {row['sido']} {sg}")
                gt[row["overseas_id"]].update(I["rpos"][r] for r in c)
                label[row["overseas_id"]].append(f"{row['korean_place']}({sg})")
    return gt, label


def sign(a, b):
    better, worse = int((a < b).sum()), int((a > b).sum())
    k, n = min(better, worse), better + worse
    p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    return better, worse, int(len(a) - better - worse), p


def main():
    I = sc.domestic_index()
    n = len(I["regions"])
    qv, by_scene = sc.scene_vectors()
    rows = sc.ok_rows()
    scenes_of = rows.groupby("place_id").scene_id.unique().to_dict()
    place_of_scene = rows.drop_duplicates("scene_id").set_index("scene_id").place_id.to_dict()
    sids = sorted(qv)
    all_ref = np.stack([qv[x] for x in sids])

    # 보강 사진 (도쿄·방콕·타이베이·베이징·나라)
    he = np.load(HOLDOUT_EMB)
    extra = defaultdict(list)
    for v, pid in zip(he["vecs"], he["place_ids"]):
        extra[str(pid)].append(v)

    cats_of, _ = cr.place_categories()
    cat_names, text_vecs = cr.category_text_vectors()
    cat_scores = cr.domestic_category_scores(I, text_vecs)
    cache = {}

    def place_vector(p):
        vs = [v for sid in scenes_of[p] for v in by_scene.get(sid, [])] + extra.get(p, [])
        m = np.mean(vs, 0)
        return m / np.linalg.norm(m), len(vs)

    def scores(method, v, p):
        if method == "C":
            return sc.vote_scores(I, v)[0]
        if method == "A":
            ref = all_ref[[place_of_scene[x] != p for x in sids]]  # 평가 해외지 장면은 기준에서 제외
            return sc.corrected_scores(I, v, ref, "prior", cache)
        return cr.combine_scores(sc.vote_scores(I, v)[0], cats_of.get(p, [])[:1], cat_names, cat_scores, CAT_WEIGHT)

    methods = {"C": "CLIP 단독 (vote100)", "A": "방법 A 시군구 기본 점수 빼기", "K": "CLIP + 대표 카테고리 0.4"}

    def run(files, label):
        gt, gt_label = load_gt(I, files)
        places = [p for p in gt if gt[p] and p in scenes_of]
        ranks, top5, n_photo = {m: {} for m in methods}, {m: {} for m in methods}, {}
        for p in places:
            v, n_photo[p] = place_vector(p)
            for m in methods:
                sc_ = scores(m, v, p)
                order = np.argsort(-sc_, kind="stable")
                pos = np.empty(n, int)
                pos[order] = np.arange(1, n + 1)
                ranks[m][p] = int(min(pos[t] for t in gt[p]))
                top5[m][p] = [I["name"][I["regions"][i]] for i in order[:5]]
        ks = (5, 10, 20)
        rand = {k: float(sum(1 - np.prod([(n - len(gt[p]) - i) / (n - i) for i in range(k)]) for p in places)) for k in ks}
        out = {"places": places, "gt": {p: gt_label[p] for p in places}, "n_photo": n_photo,
               "random": rand, "ranks": ranks, "top5": top5, "summary": {}}
        base = np.array([ranks["C"][p] for p in places])
        for m in methods:
            r = np.array([ranks[m][p] for p in places])
            appear = Counter(x for p in places for x in top5[m][p])
            urban = np.array([p in URBAN for p in places])
            out["summary"][m] = {
                "hit5": int((r <= 5).sum()), "hit10": int((r <= 10).sum()), "hit20": int((r <= 20).sum()),
                "mrr": float(np.mean(1 / r)), "median": float(np.median(r)), "worst": int(r.max()),
                "over20": int((r > 20).sum()),
                "hit10_urban": int((r[urban] <= 10).sum()), "n_urban": int(urban.sum()),
                "hit10_other": int((r[~urban] <= 10).sum()), "n_other": int((~urban).sum()),
                "top5_regions": len(appear),
                "top10_share": sum(v for _, v in appear.most_common(10)) / (len(places) * 5),
                "watch": {w: appear.get(w, 0) for w in WATCH},
                "vs_C": None if m == "C" else sign(r, base),
            }
        return out

    hold = run([HOLDOUT_GT], "holdout")
    dev = run(rd.DEV_FILES, "dev")

    def table(res, title):
        n_q = len(res["places"])
        rd_ = res["random"]
        print(f"\n## {title}: 해외지 {n_q}곳, 국내 {n}개 시군구")
        print(f"랜덤 기대: Hit@5 {rd_[5]:.2f} / Hit@10 {rd_[10]:.2f} / Hit@20 {rd_[20]:.2f}")
        print("| 방법 | Hit@5 | Hit@10 | Hit@20 | MRR | 중앙 | 최악 | 20위 밖 | 도시 Hit@10 | 그 외 Hit@10 | 상위5 시군구 수 | 상위10 점유율 | 제주시/서귀포/종로 | C 대비 좋아짐/나빠짐/같음 (p) |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for m, lab in methods.items():
            s = res["summary"][m]
            vs = "—" if s["vs_C"] is None else f"{s['vs_C'][0]}/{s['vs_C'][1]}/{s['vs_C'][2]} ({s['vs_C'][3]:.2f})"
            w = "/".join(str(v) for v in s["watch"].values())
            print(f"| {lab} | {s['hit5']} | {s['hit10']} | {s['hit20']} | {s['mrr']:.3f} | {s['median']:.0f} | {s['worst']} | "
                  f"{s['over20']} | {s['hit10_urban']}/{s['n_urban']} | {s['hit10_other']}/{s['n_other']} | "
                  f"{s['top5_regions']} | {s['top10_share']:.0%} | {w} | {vs} |")

    table(hold, "홀드아웃 15곳 (1회 평가)")
    table(dev, "개발셋 23곳 (같은 지표)")
    print("\n## 홀드아웃 해외지별 순위")
    print("| 해외지 | 구분 | 질의 사진 수 | 정답 | CLIP 단독 | 방법 A | 카테고리 0.4 | CLIP 단독 상위 3 |")
    print("|---|---|---|---|---|---|---|---|")
    for p in hold["places"]:
        print(f"| {p} | {'도시' if p in URBAN else '그 외'} | {hold['n_photo'][p]} | {', '.join(hold['gt'][p])} | "
              + " | ".join(str(hold["ranks"][m][p]) for m in methods)
              + " | " + ", ".join(x.split()[-1] for x in hold["top5"]["C"][p][:3]) + " |")
    (cp.WORK / "eval_holdout_pilot.json").write_text(json.dumps({"holdout": hold, "dev": dev}, ensure_ascii=False,
                                                                 indent=1, default=float))


if __name__ == "__main__":
    main()
