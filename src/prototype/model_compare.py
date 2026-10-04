"""CLIP 모델 크기 비교: ViT-B/32(현재) vs ViT-B/16 vs ViT-L/14, 개발셋 38곳, 시군구 vote100.

판정 기준 (결과를 보기 전에 정함): 현재 모델 대비 Hit@10 이 4곳 이상 오르고 MRR 도 오르면 "개선 가능".
개발셋 38곳은 이미 결과를 본 세트이므로, 채택하더라도 새 테스트셋으로 다시 확인해야 한다.

단계
    embed <model>   국내 대표사진·해외 장면 사진·보강 사진을 그 모델로 임베딩
                    → data/interim/clip/models/<slug>/{kr,scenes,holdout}.npz
    evaluate        캐시된 모델 전부를 같은 조건으로 평가 → data/interim/clip/eval_model_compare.json

실행:
    .venv/bin/python src/prototype/model_compare.py embed openai/clip-vit-base-patch16
    .venv/bin/python src/prototype/model_compare.py evaluate
"""

import json
import sys
import time
from collections import defaultdict
from math import comb

import numpy as np

import clip_proto as cp
import holdout_pilot as hp
import reverify_dev as rd
import scene_catalog as sc

MODELS = ["openai/clip-vit-base-patch32", "openai/clip-vit-base-patch16", "openai/clip-vit-large-patch14"]
BASE_MODEL = MODELS[0]
CACHE = cp.WORK / "models"
HOLDOUT_IMG = cp.WORK / "scenes_holdout"


def slug(model):
    return model.split("/")[-1]


def step_embed(model):
    import torch
    from transformers import CLIPModel, CLIPProcessor
    torch.set_num_threads(14)
    out = CACHE / slug(model)
    out.mkdir(parents=True, exist_ok=True)
    m = CLIPModel.from_pretrained(model).eval()
    p = CLIPProcessor.from_pretrained(model)
    kr_names = [str(n) for n in np.load(cp.WORK / "emb_kr.npz")["names"]]  # 현재 모델과 같은 사진·순서
    jobs = {
        "kr": [cp.KR_DIR / f"{n}.jpg" for n in kr_names],
        "scenes": sorted(sc.IMG_DIR.glob("*.jpg")),
        "holdout": sorted(HOLDOUT_IMG.glob("*.jpg")),
    }
    for name, paths in jobs.items():
        f = out / f"{name}.npz"
        if f.exists():
            print(f"[{slug(model)}] {name} 캐시 사용", flush=True)
            continue
        t = time.time()
        vecs, kept = cp.embed_files(paths, m, p, batch=32)
        np.savez(f, vecs=vecs, names=np.array([x.stem if name == "kr" else x.name for x in kept]))
        print(f"[{slug(model)}] {name}: {len(kept)}/{len(paths)}장, {time.time() - t:.0f}초", flush=True)


def load_model_vectors(model):
    d = CACHE / slug(model)
    if model == BASE_MODEL and not (d / "kr.npz").exists():
        # 현재 모델은 기존 캐시를 그대로 쓴다
        kr, scenes, hold = np.load(cp.WORK / "emb_kr.npz"), np.load(sc.EMB), np.load(hp.HOLDOUT_EMB)
        return kr["vecs"], [str(n) for n in kr["names"]], scenes["vecs"], [str(n) for n in scenes["names"]], \
            hold["vecs"], [str(n) for n in hold["names"]]
    kr, scenes, hold = (np.load(d / f"{x}.npz") for x in ("kr", "scenes", "holdout"))
    return kr["vecs"], [str(n) for n in kr["names"]], scenes["vecs"], [str(n) for n in scenes["names"]], \
        hold["vecs"], [str(n) for n in hold["names"]]


def step_evaluate():
    base_I = sc.domestic_index()
    gt, _ = hp.load_gt(base_I, rd.DEV_FILES + [hp.HOLDOUT_GT])
    n = len(base_I["regions"])
    results = {}
    for model in MODELS:
        if model != BASE_MODEL and not (CACHE / slug(model) / "holdout.npz").exists():
            print(f"{slug(model)}: 임베딩 없음, 건너뜀")
            continue
        kv, kn, sv, sn, hv, hn = load_model_vectors(model)
        # 국내 인덱스: 사진·시군구 대응은 현재 모델과 같고 벡터만 바꾼다
        assert kn == [str(c) for c in base_I["cid"]], "국내 사진 순서가 현재 모델 캐시와 다르다"
        I = dict(base_I)
        I["kv"] = kv
        m = np.stack([kv[base_I["img_region"] == k].mean(0) for k in range(n)])
        I["reg_mean"] = m / np.linalg.norm(m, axis=1, keepdims=True)
        photos = defaultdict(list)
        for v, name in zip(sv, sn):
            photos[name.split("__")[0]].append(v)
        for v, name in zip(hv, hn):
            photos[name.split("__")[0]].append(v)
        places = [p for p in gt if gt[p] and photos.get(p)]
        ranks = {}
        for p in places:
            v = np.mean(photos[p], 0)
            v /= np.linalg.norm(v)
            pos = np.empty(n, int)
            pos[np.argsort(-sc.vote_scores(I, v)[0], kind="stable")] = np.arange(1, n + 1)
            ranks[p] = int(min(pos[t] for t in gt[p]))
        results[model] = ranks

    base = results[BASE_MODEL]
    places = list(base)
    print(f"[개발셋] 해외지 {len(places)}곳, 국내 {n}개 시군구, 시군구 vote100")
    print("| 모델 | Hit@5 | Hit@10 | Hit@20 | MRR | 중앙 | 최악 | 현재 대비 좋아짐/나빠짐 (p) | 판정 |")
    print("|---|---|---|---|---|---|---|---|---|")
    summary = {}
    for model, ranks in results.items():
        r = np.array([ranks[p] for p in places])
        b = np.array([base[p] for p in places])
        better, worse = int((r < b).sum()), int((r > b).sum())
        k, t = min(better, worse), better + worse
        pv = 1.0 if t == 0 else min(1.0, 2 * sum(comb(t, i) for i in range(k + 1)) / 2 ** t)
        s = {"hit5": int((r <= 5).sum()), "hit10": int((r <= 10).sum()), "hit20": int((r <= 20).sum()),
             "mrr": float(np.mean(1 / r)), "median": float(np.median(r)), "worst": int(r.max()),
             "better": better, "worse": worse, "p": pv}
        bs = {"hit10": int((b <= 10).sum()), "mrr": float(np.mean(1 / b))}
        verdict = "—" if model == BASE_MODEL else (
            "개선 가능" if s["hit10"] - bs["hit10"] >= 4 and s["mrr"] > bs["mrr"] else "기준 미달")
        summary[model] = {**s, "verdict": verdict}
        print(f"| {slug(model)} | {s['hit5']} | {s['hit10']} | {s['hit20']} | {s['mrr']:.3f} | {s['median']:.0f} | "
              f"{s['worst']} | {'—' if model == BASE_MODEL else f'{better}/{worse} (p={pv:.2f})'} | {verdict} |")
    print("\n| 해외지 | " + " | ".join(slug(m) for m in results) + " |\n|---|" + "---|" * len(results))
    for p in places:
        print(f"| {p} | " + " | ".join(str(results[m][p]) for m in results) + " |")
    (cp.WORK / "eval_model_compare.json").write_text(json.dumps(
        {"summary": summary, "ranks": results}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "embed":
        step_embed(sys.argv[2])
    else:
        step_evaluate()
