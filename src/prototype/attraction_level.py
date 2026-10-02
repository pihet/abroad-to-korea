"""관광지 단위 추천 평가 (개발셋 38곳 = dev 23 + 11-6 에서 개발셋으로 전환된 15곳).

방식
    C    시군구 vote100 (현재 서비스 기본값). 시군구마다 가장 닮은 관광지 1곳을 보여준다고 본다
    T    관광지를 유사도 순으로 그대로 (같은 시군구 반복 허용)
    T-1  T 에서 시군구당 1곳만 (= 시군구를 '가장 닮은 관광지 1장'으로 순위화)
지표
    시군구 Hit@k : 추천 목록 상위 k 안에 정답 시군구의 관광지가 있는가
    정확 관광지 Hit@k : 정답 장소로 연결된 TourAPI 관광지 자체가 상위 k 안에 있는가 (연결표 STRICT)
연결표는 추천 결과를 보기 전에 정답 시군구 안의 이름 후보를 보고 고정했다.

실행: .venv/bin/python src/prototype/attraction_level.py
결과: data/interim/clip/eval_attraction_level.json
"""

import json
from collections import Counter
from math import comb

import numpy as np

import holdout_pilot as hp
import reverify_dev as rd
import scene_catalog as sc

# 정답 쌍 → TourAPI contentid (이름이 명확히 같은 것만, 사진 있는 것만 평가에 쓰인다)
STRICT = {
    "gt001": ["264284"], "gt004": ["2570170"], "gt005": ["2768201"], "gt006": ["2524188"],
    "gt008": ["2767553"], "gt009": ["2637753"], "gt010": ["2590796"], "gt011": ["2820546"], "gt012": ["125616"],
    "gt013": ["128013"], "gt014": ["128013"], "gt015": ["129401"], "gt016": ["2710734"], "gt019": ["125653"],
    "ga001": ["2820737", "125792", "127649"], "ga003": ["126020"], "ga009": ["3351160"], "ga010": ["2664196"],
    "ga011": ["127549", "575857", "126822"], "ga012": ["1032715"], "ga015": ["2664266"], "ga016": ["127053"],
    "ga017": ["125711"], "ga020": ["1997221"], "ga021": ["1997221"], "ga022": ["1997221"], "ga023": ["2684712"],
    "ga025": ["127778"], "ga027": ["2650231", "2930901"],
    "gt2_010": ["2733852", "127955", "2774305", "809596", "1059479", "2760268"], "gt2_013": ["1608654"],
    "gt2_014": ["577866"], "gt2_001": ["781031", "2500145", "3082405"], "gt2_005": ["2350092", "2617724"],
    "gt2_006": ["2465107"], "gt2_008": ["2606204", "3544138"], "gt2_009": ["125805"], "gt2_011": ["126595"],
    "gt2_015": ["2710184"], "gt2_018": ["126999", "1019182", "2650771", "2401910"],
    "gt2_019": ["264353", "2666751"], "gt2_020": ["126081"], "gt2_021": ["2603509"], "gt2_024": ["264353", "2666751"],
}
REGION_WIDE = {"gt002": "통영", "gt018": "제주", "ga019": "여수", "ga028": "경주"}  # 지역 전체가 정답
UNMATCHED = {  # 정확 관광지 평가에서 제외
    "gt003": "동피랑마을 사진 없음", "gt007": "대관령양떼목장 사진 없음", "gt017": "하누넘해변 TourAPI 없음",
    "ga002": "수섬 TourAPI 없음", "ga004": "미인폭포 사진 없음", "ga008": "죽도(홍성) 사진 없음",
    "ga014": "영산도 사진 없음", "ga026": "동피랑마을 사진 없음", "gt2_012": "한탄강 주상절리길 TourAPI 없음",
    "gt2_017": "곡성 동화정원 TourAPI 없음", "gt2_022": "송도컨벤시아 TourAPI 없음", "gt2_023": "망양로 버스 구간(관광지 아님)",
}
KS = (5, 10, 20)


def main():
    I = sc.domestic_index()
    n_reg = len(I["regions"])
    N = len(I["kv"])
    cid = np.array([str(c) for c in I["cid"]])
    img_region = I["img_region"]
    qv, by_scene = sc.scene_vectors()
    rows = sc.ok_rows()
    scenes_of = rows.groupby("place_id").scene_id.unique().to_dict()
    he = np.load(hp.HOLDOUT_EMB)
    extra = {}
    for v, pid in zip(he["vecs"], he["place_ids"]):
        extra.setdefault(str(pid), []).append(v)

    files = rd.DEV_FILES + [hp.HOLDOUT_GT]
    gt, _ = hp.load_gt(I, files)
    import csv
    strict_of, pair_ids = {}, {}
    for f in files:
        for row in csv.DictReader(open(f, encoding="utf-8")):
            if row["use_for_eval"] != "1":
                continue
            pair_ids.setdefault(row["overseas_id"], []).append(row["pair_id"])
            ids = [c for c in STRICT.get(row["pair_id"], []) if c in set(cid)]
            if ids:
                strict_of.setdefault(row["overseas_id"], set()).update(ids)
    places = [p for p in gt if gt[p] and p in scenes_of]
    no_photo_strict = sorted({c for v in STRICT.values() for c in v} - set(cid))

    res = {m: {"region": {}, "strict": {}} for m in ("C", "T", "T-1")}
    top5_regions = {m: Counter() for m in res}
    for p in places:
        vs = [v for sid in scenes_of[p] for v in by_scene.get(sid, [])] + extra.get(p, [])
        v = np.mean(vs, 0)
        v /= np.linalg.norm(v)
        sims = I["kv"] @ v
        order = np.argsort(-sims, kind="stable")
        order = order[img_region[order] >= 0]

        # T: 관광지 순서 그대로
        reg_seq = img_region[order]
        hit_pos = np.where(np.isin(reg_seq, list(gt[p])))[0]
        res["T"]["region"][p] = int(hit_pos[0] + 1)
        # T-1: 시군구 첫 등장 순서
        _, first = np.unique(reg_seq, return_index=True)
        first_order = order[np.sort(first)]
        reg_rank = {img_region[i]: k + 1 for k, i in enumerate(first_order)}
        res["T-1"]["region"][p] = int(min(reg_rank[t] for t in gt[p]))
        # C: vote100 시군구 순위, 각 시군구의 대표 관광지 = 그 시군구 안 최고 유사 사진
        vs_ = sc.vote_scores(I, v)[0]
        c_order = np.argsort(-vs_, kind="stable")
        pos = np.empty(n_reg, int)
        pos[c_order] = np.arange(1, n_reg + 1)
        res["C"]["region"][p] = int(min(pos[t] for t in gt[p]))
        best_of_region = {img_region[i]: i for i in first_order}  # 시군구별 최고 유사 사진
        c_list = [best_of_region[r] for r in c_order if r in best_of_region]

        for m, lst in [("T", order), ("T-1", first_order), ("C", np.array(c_list))]:
            top5_regions[m].update(I["name"][I["regions"][img_region[i]]] for i in lst[:5])
            if p in strict_of:
                hits = np.where(np.isin(cid[lst], list(strict_of[p])))[0]
                res[m]["strict"][p] = int(hits[0] + 1) if len(hits) else 10 ** 6  # 목록에 없으면 미적중

    # 랜덤 기대 (시군구 Hit: T 는 사진 단위, C·T-1 은 시군구 단위)
    def rand_region_T(k):
        return sum(1 - comb(N - int(np.isin(img_region, list(gt[p])).sum()), k) / comb(N, k) for p in places)

    def rand_region_C(k):
        return sum(1 - np.prod([(n_reg - len(gt[p]) - i) / (n_reg - i) for i in range(k)]) for p in places)

    sp = [p for p in places if p in strict_of]
    print(f"[개발셋] 해외지 {len(places)}곳 (dev 23 + 전환 15), 국내 관광지 사진 {N}장 · {n_reg}개 시군구")
    print(f"정확 관광지 평가 가능 해외지 {len(sp)}곳 (연결표 사진 없는 id: {', '.join(no_photo_strict) or '없음'})")
    print("\n| 방식 | 시군구 Hit@5 | Hit@10 | Hit@20 | MRR | 중앙 | 최악 | 정확 관광지 Hit@5 | Hit@10 | Hit@20 | 상위5 시군구 수 | 상위10 점유율 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    summary = {}
    for m in res:
        r = np.array([res[m]["region"][p] for p in places])
        s = np.array([res[m]["strict"][p] for p in sp])
        share = sum(v for _, v in top5_regions[m].most_common(10)) / (len(places) * 5)
        summary[m] = {"region_hit": {k: int((r <= k).sum()) for k in KS}, "mrr": float(np.mean(1 / r)),
                      "median": float(np.median(r)), "worst": int(r.max()),
                      "strict_hit": {k: int((s <= k).sum()) for k in KS},
                      "top5_regions": len(top5_regions[m]), "top10_share": float(share)}
        print(f"| {m} | {(r <= 5).sum()} | {(r <= 10).sum()} | {(r <= 20).sum()} | {np.mean(1 / r):.3f} | "
              f"{np.median(r):.0f} | {r.max()} | {(s <= 5).sum()}/{len(sp)} | {(s <= 10).sum()} | {(s <= 20).sum()} | "
              f"{len(top5_regions[m])} | {share:.0%} |")
    print("랜덤 기대 시군구 Hit (C·T-1): " + " / ".join(f"@{k} {rand_region_C(k):.2f}" for k in KS)
          + " | (T): " + " / ".join(f"@{k} {rand_region_T(k):.2f}" for k in KS))

    def sign(a, b):
        better, worse = int((a < b).sum()), int((a > b).sum())
        k, n = min(better, worse), better + worse
        return better, worse, 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    base = np.array([res["C"]["region"][p] for p in places])
    for m in ("T", "T-1"):
        b, w, pv = sign(np.array([res[m]["region"][p] for p in places]), base)
        print(f"  {m} vs C (시군구 순위): 좋아짐 {b} / 나빠짐 {w} (p={pv:.2f})")

    print("\n| 해외지 | 시군구 순위 C | T | T-1 | 정확 관광지 순위 C | T | T-1 |\n|---|---|---|---|---|---|---|")
    fmt = lambda x: "-" if x is None else ("목록 밖" if x >= 10 ** 6 else str(x))
    for p in places:
        print(f"| {p} | {res['C']['region'][p]} | {res['T']['region'][p]} | {res['T-1']['region'][p]} | "
              + " | ".join(fmt(res[m]["strict"].get(p)) for m in ("C", "T", "T-1")) + " |")
    (sc.cp.WORK / "eval_attraction_level.json").write_text(json.dumps(
        {"places": places, "strict_places": sp, "summary": summary, "ranks": res,
         "region_wide": REGION_WIDE, "unmatched": UNMATCHED}, ensure_ascii=False, indent=1, default=int))


if __name__ == "__main__":
    main()
