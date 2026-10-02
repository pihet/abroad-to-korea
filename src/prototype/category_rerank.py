"""CLIP 이미지 추천에 사용자 분위기 카테고리를 더해 재정렬한다.

기존 장면 카탈로그 평가(HANDOFF 11장)와 같은 국내 230개 시군구,
vote100 점수, 정답 쌍을 사용한다. 해외 카탈로그의 ``vibe_tags``는
실제 사용자 입력이 없을 때 선택 카테고리를 모사하는 용도로만 쓴다.

국내 대응이 어려운 태그는 억지로 매핑하지 않고 이미지 점수만 사용한다.
카테고리 점수는 CLIP 텍스트 프롬프트와 국내 관광지 사진의 유사도로 만든다.

실행:
    .venv/bin/python src/prototype/category_rerank.py

결과:
    data/interim/clip/eval_category_rerank.json
"""

import json
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

import clip_proto as cp
import scene_catalog as sc


RESULT_PATH = cp.WORK / "eval_category_rerank.json"
TEXT_EMB_PATH = cp.WORK / "category_text_v1.npz"
CATEGORY_TOP_N = 3
WEIGHTS = (0.0, 0.1, 0.2, 0.3, 0.4)

# OpenAI CLIP은 영어 프롬프트에서 더 안정적이므로 영어 문장을 사용한다.
# 범주는 국내에서 대응 사진을 충분히 찾을 수 있는 분위기로 제한했다.
CATEGORIES = {
    "coast_island": [
        "a travel photo of a beach, island, or coastal landscape",
        "a scenic Korean seaside travel destination",
    ],
    "mountain_snow": [
        "a travel photo of mountains, snowy peaks, or a highland",
        "a scenic mountain travel destination",
    ],
    "forest_grassland": [
        "a travel photo of a forest, meadow, grassland, or flower field",
        "a green rural landscape with fields and open nature",
    ],
    "dune_sand": [
        "a travel photo of sand dunes or a sandy coastal landscape",
        "a scenic sand dune travel destination",
    ],
    "waterfall_valley": [
        "a travel photo of a waterfall, river valley, or gorge stream",
        "a scenic waterfall and valley destination",
    ],
    "cliff_canyon": [
        "a travel photo of a rocky cliff, canyon, or unusual rock formation",
        "a dramatic geological cliff landscape",
    ],
    "volcanic_geology": [
        "a travel photo of a volcanic island, lava rock, or columnar basalt",
        "a dramatic volcanic geological landscape",
    ],
    "heritage_traditional": [
        "a travel photo of a historic town, temple, palace, or traditional village",
        "a traditional cultural heritage travel destination",
    ],
    "city_night": [
        "a travel photo of a modern city street, downtown skyline, or night market",
        "a lively urban travel destination at night",
    ],
    "harbor_canal": [
        "a travel photo of a harbor city, canal, waterfront, or port",
        "a scenic waterfront city travel destination",
    ],
    "rural_terrace": [
        "a travel photo of terraced fields, a hillside village, or rural farmland",
        "a scenic terraced rural village landscape",
    ],
}

# 카탈로그의 기존 태그를 사용자가 고를 수 있는 지원 범주로 묶는다.
# 명시되지 않은 태그는 지원하지 않는 것으로 처리한다.
TAG_TO_CATEGORY = {
    "해변": "coast_island", "섬": "coast_island", "해안": "coast_island",
    "바다": "coast_island", "라군": "coast_island", "갯벌": "coast_island",
    "검은 모래 해변": "coast_island", "해안 절벽 마을": "coast_island",
    "해안 절벽": "cliff_canyon", "석회암 절벽": "cliff_canyon",
    "석회암 섬": "cliff_canyon", "협곡": "cliff_canyon", "기암": "cliff_canyon",
    "암봉": "cliff_canyon", "화강암 계곡": "cliff_canyon",
    "주상절리 해안": "volcanic_geology", "화산": "volcanic_geology",
    "화산섬": "volcanic_geology",
    "산": "mountain_snow", "설산": "mountain_snow", "설경": "mountain_snow",
    "고원": "mountain_snow", "알프스": "mountain_snow", "산악마을": "mountain_snow",
    "초원": "forest_grassland", "숲": "forest_grassland", "꽃": "forest_grassland",
    "꽃밭": "forest_grassland", "공원": "forest_grassland", "정원": "forest_grassland",
    "사구": "dune_sand", "사막": "dune_sand",
    "폭포": "waterfall_valley", "계곡": "waterfall_valley", "강": "waterfall_valley",
    "도시": "city_night", "야경": "city_night", "야시장": "city_night",
    "산업지대": "city_night", "강변도시": "city_night",
    "역사": "heritage_traditional", "역사도시": "heritage_traditional",
    "전통마을": "heritage_traditional", "사원": "heritage_traditional",
    "궁궐": "heritage_traditional", "성곽": "heritage_traditional",
    "고성": "heritage_traditional", "고성 도시": "heritage_traditional",
    "유적": "heritage_traditional", "고산 유적": "heritage_traditional",
    "섬 수도원": "heritage_traditional",
    "항구": "harbor_canal", "항구도시": "harbor_canal", "운하도시": "harbor_canal",
    "운하 도시": "harbor_canal", "운하 마을": "harbor_canal",
    "계단식 논": "rural_terrace", "계단식": "rural_terrace",
    "산골마을": "rural_terrace", "산비탈마을": "rural_terrace",
}


def place_categories() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """여행지별 지원 카테고리와 지원하지 않는 원본 태그를 반환한다."""
    places = pd.read_csv(sc.PLACES_CSV)
    supported, unsupported = {}, {}
    for row in places.itertuples():
        raw = [x.strip() for x in str(row.vibe_tags).split(",") if x.strip()]
        mapped = []
        missing = []
        for tag in raw:
            category = TAG_TO_CATEGORY.get(tag)
            if category and category not in mapped:
                mapped.append(category)
            elif not category:
                missing.append(tag)
        supported[row.place_id] = mapped
        unsupported[row.place_id] = missing
    return supported, unsupported


def category_text_vectors() -> tuple[list[str], np.ndarray]:
    """카테고리별 프롬프트 평균 CLIP 텍스트 임베딩을 생성하거나 캐시에서 읽는다."""
    names = list(CATEGORIES)
    if TEXT_EMB_PATH.exists():
        cached = np.load(TEXT_EMB_PATH)
        if list(cached["names"].astype(str)) == names:
            return names, cached["vecs"]

    import torch
    from transformers import CLIPModel, CLIPProcessor

    model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
    processor = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
    vectors = []
    with torch.no_grad():
        for name in names:
            inputs = processor(text=CATEGORIES[name], return_tensors="pt", padding=True)
            out = model.get_text_features(**inputs)
            features = out if isinstance(out, torch.Tensor) else out.pooler_output
            features = torch.nn.functional.normalize(features, dim=-1)
            mean = features.mean(0)
            mean = torch.nn.functional.normalize(mean, dim=0)
            vectors.append(mean.numpy())
    vecs = np.stack(vectors)
    np.savez(TEXT_EMB_PATH, names=np.array(names), vecs=vecs)
    return names, vecs


def rank_percentile(values: np.ndarray) -> np.ndarray:
    """값이 클수록 1에 가까운 순위 백분위로 바꾼다."""
    order = np.argsort(-values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values))
    return 1.0 - ranks / max(len(values) - 1, 1)


def domestic_category_scores(index: dict, text_vecs: np.ndarray) -> np.ndarray:
    """시군구 × 카테고리 점수. 지역별 상위 사진 3장의 텍스트 유사도 평균."""
    image_scores = index["kv"] @ text_vecs.T
    result = np.zeros((len(index["regions"]), text_vecs.shape[0]), dtype=float)
    for region_i in range(len(index["regions"])):
        rows = image_scores[index["img_region"] == region_i]
        k = min(CATEGORY_TOP_N, len(rows))
        result[region_i] = np.sort(rows, axis=0)[-k:].mean(axis=0)
    return np.stack([rank_percentile(result[:, j]) for j in range(result.shape[1])], axis=1)


def load_ground_truth(index: dict) -> dict[str, set[int]]:
    name_to_region = defaultdict(list)
    for region in index["regions"]:
        name_to_region[region[1]].append(region)
    gt = defaultdict(set)
    for path in cp.GT_FILES:
        rows = pd.read_csv(path)
        for row in rows[rows.use_for_eval == 1].itertuples():
            for sigungu in row.sigungu.split("|"):
                candidates = name_to_region[sigungu]
                if len(candidates) > 1:
                    candidates = [r for r in candidates if index["name"][r].startswith(row.sido)]
                gt[row.overseas_id].update(index["rpos"][r] for r in candidates)
    return gt


def combine_scores(image_scores: np.ndarray, categories: list[str], category_names: list[str],
                   category_scores: np.ndarray, weight: float) -> np.ndarray:
    image_rank = rank_percentile(image_scores)
    if weight == 0 or not categories:
        return image_rank
    positions = [category_names.index(c) for c in categories]
    # 여러 카테고리를 고른 경우 모두 어느 정도 만족하도록 평균한다.
    selected = category_scores[:, positions].mean(axis=1)
    return (1.0 - weight) * image_rank + weight * selected


def summarize(ranks: dict[str, int]) -> dict:
    values = np.array(list(ranks.values()))
    return {
        "n": len(values),
        "hit5": int((values <= 5).sum()),
        "hit10": int((values <= 10).sum()),
        "hit20": int((values <= 20).sum()),
        "mrr": float(np.mean(1 / values)),
        "median_rank": float(np.median(values)),
        "worst_rank": int(values.max()),
    }


def main() -> None:
    index = sc.domestic_index()
    query_vectors, by_scene = sc.scene_vectors()
    scene_rows = sc.ok_rows()
    scenes_of = scene_rows.groupby("place_id").scene_id.unique().to_dict()
    categories_of, unsupported_of = place_categories()
    category_names, text_vectors = category_text_vectors()
    category_scores = domestic_category_scores(index, text_vectors)
    gt = load_ground_truth(index)
    places = [p for p in gt if gt[p] and p in scenes_of]
    n_regions = len(index["regions"])

    place_vectors = {}
    for place in places:
        vectors = [v for sid in scenes_of[place] for v in by_scene.get(sid, [])]
        mean = np.mean(vectors, axis=0)
        place_vectors[place] = mean / np.linalg.norm(mean)

    category_modes = {
        "primary": lambda place: categories_of.get(place, [])[:1],
        "all": lambda place: categories_of.get(place, []),
    }
    results = {}
    print(f"[평가] 해외지 {len(places)}곳, 국내 {n_regions}개 시군구, 카테고리 {len(category_names)}개")
    fallback = [p for p in places if not categories_of.get(p)]
    print(f"  지원 카테고리가 없어 CLIP 단독으로 fallback: {len(fallback)}곳 ({', '.join(fallback) or '없음'})")
    for mode, select_categories in category_modes.items():
        print(f"\n[{mode}: {'대표 카테고리 1개' if mode == 'primary' else '지원 카테고리 전체'}]")
        print("| 카테고리 가중치 | Hit@5 | Hit@10 | Hit@20 | MRR | 중앙 순위 | 최악 |")
        print("|---:|---:|---:|---:|---:|---:|---:|")
        results[mode] = {}
        for weight in WEIGHTS:
            ranks = {}
            for place in places:
                image_scores = sc.vote_scores(index, place_vectors[place])[0]
                final = combine_scores(image_scores, select_categories(place), category_names,
                                       category_scores, weight)
                position = np.empty(n_regions, dtype=int)
                position[np.argsort(-final, kind="stable")] = np.arange(1, n_regions + 1)
                ranks[place] = int(min(position[target] for target in gt[place]))
            summary = summarize(ranks)
            results[mode][str(weight)] = {"summary": summary, "best_ranks": ranks}
            print(f"| {weight:.1f} | {summary['hit5']} | {summary['hit10']} | {summary['hit20']} | "
                  f"{summary['mrr']:.3f} | {summary['median_rank']:.0f} | {summary['worst_rank']} |")

    # 실제 UI에 가까운 대표 카테고리 1개 조건으로 전체 213개 장면의 쏠림을 계산한다.
    hubness = {}
    place_of_scene = scene_rows.drop_duplicates("scene_id").set_index("scene_id").place_id.to_dict()
    print("\n[쏠림] 전체 장면의 상위 5 추천")
    print("| 카테고리 가중치 | 추천에 나온 시군구 | 상위 10개 지역 비중 |")
    print("|---:|---:|---:|")
    for weight in WEIGHTS:
        appearances = Counter()
        for scene_id, vector in query_vectors.items():
            place = place_of_scene[scene_id]
            image_scores = sc.vote_scores(index, vector)[0]
            final = combine_scores(image_scores, categories_of.get(place, [])[:1], category_names,
                                   category_scores, weight)
            for region_i in np.argsort(-final, kind="stable")[:sc.TOP_N]:
                appearances[index["name"][index["regions"][region_i]]] += 1
        top10_share = sum(v for _, v in appearances.most_common(10)) / (len(query_vectors) * sc.TOP_N)
        hubness[str(weight)] = {
            "n_regions": len(appearances),
            "top10_share": float(top10_share),
            "most_common": appearances.most_common(10),
        }
        print(f"| {weight:.1f} | {len(appearances)} / {n_regions} | {top10_share:.0%} |")

    base = results["primary"]["0.0"]["best_ranks"]
    print("\n[여행지별 변화: 대표 카테고리 1개, 가중치 0.4]")
    print("| 해외지 | 적용 카테고리 | 기존 | 결합 | 변화 |")
    print("|---|---|---:|---:|---:|")
    for place in places:
        new = results["primary"]["0.4"]["best_ranks"][place]
        selected = categories_of.get(place, [])[:1]
        print(f"| {place} | {','.join(selected) or 'fallback'} | "
              f"{base[place]} | {new} | {base[place] - new:+d} |")

    payload = {
        "model": cp.MODEL_NAME,
        "image_method": f"vote{sc.VOTE_K}",
        "category_top_n": CATEGORY_TOP_N,
        "weights": list(WEIGHTS),
        "category_prompts": CATEGORIES,
        "tag_to_category": TAG_TO_CATEGORY,
        "unsupported_tags": sorted({tag for values in unsupported_of.values() for tag in values}),
        "places": places,
        "place_categories": {p: categories_of.get(p, []) for p in places},
        "results": results,
        "hubness": hubness,
        "limitations": [
            "실제 사용자 입력 대신 카탈로그 vibe_tags를 사용했다.",
            "같은 20개 평가셋으로 가중치를 비교했으므로 최적 가중치는 별도 검증이 필요하다.",
            "국내 카테고리 점수는 TourAPI 분류가 아니라 CLIP 텍스트-이미지 유사도다.",
        ],
    }
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {RESULT_PATH}")


if __name__ == "__main__":
    main()
