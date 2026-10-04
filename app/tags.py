"""장면 태그: 고정 태그 목록을 CLIP 텍스트로 임베딩하고, 사진과의 유사도(softmax)로 상위 태그를 고른다.

- 업로드 사진의 태그 칩, 원본·후보의 "비슷한 점 / 다른 점" 설명에 쓴다
- 평가하지 않은 설명 기능이므로 화면에 "자동 비교(참고용)"로 표시한다
- 검색 순위에는 쓰지 않는다 (텍스트 조건과 함께 P1)
"""

import numpy as np

# (한국어 태그, CLIP 영어 설명)
TAGS = [
    ("모래 해변", "a sandy beach by the sea"), ("에메랄드빛 바다", "clear emerald turquoise sea water"),
    ("해안 절벽", "rocky sea cliffs on the coast"), ("항구·어촌", "a harbor with fishing boats"),
    ("섬", "a small island in the sea"), ("산 능선", "mountain ridges and peaks"),
    ("설산", "snow-capped mountains"), ("계곡·폭포", "a waterfall in a rocky valley"),
    ("호수", "a calm lake surrounded by nature"), ("강과 다리", "a river with a bridge"),
    ("울창한 숲", "a dense green forest"), ("대나무숲", "a bamboo forest"),
    ("초원·목장", "rolling green grassland and pasture"), ("꽃밭", "a field of colorful flowers"),
    ("논·계단식 논", "rice terraces and paddy fields"), ("모래언덕", "sand dunes"),
    ("협곡·암석 지형", "a rocky canyon with layered cliffs"), ("화산·용암 지형", "volcanic rocks and lava landscape"),
    ("동굴", "inside a cave"), ("사찰·신사", "an East Asian temple or shrine"),
    ("전통 목조 가옥", "traditional wooden houses with tiled roofs"), ("성·궁궐", "a historic castle or palace"),
    ("유럽풍 건축", "European style historic buildings"), ("흰색 건축물", "white-washed buildings"),
    ("알록달록한 마을", "a colorful hillside village"), ("교회·성당", "a church or cathedral"),
    ("고층 빌딩", "skyscrapers and a modern city skyline"), ("번화가·네온", "a busy shopping street with neon signs"),
    ("시장·먹거리 골목", "a crowded street market with food stalls"), ("오래된 골목길", "a narrow old alley"),
    ("공원·정원", "a landscaped garden or park"), ("데크 산책로", "a wooden boardwalk walking trail"),
    ("야경", "a city at night with lights"), ("노을", "a sunset sky"),
    ("눈 풍경", "a snowy winter landscape"), ("단풍", "autumn foliage with red and yellow leaves"),
    ("벚꽃", "cherry blossoms in bloom"), ("리조트·수영장", "a resort with a swimming pool"),
    ("야자수·열대", "tropical palm trees"),
]
TOP_QUERY = 6
TOP_COMPARE = 8
MIN_PROB = 0.05


class Tagger:
    def __init__(self, model, processor):
        import torch
        prompts = [f"a photo of {en}" for _, en in TAGS]
        with torch.no_grad():
            t = model.get_text_features(**processor(text=prompts, return_tensors="pt", padding=True))
            t = t if isinstance(t, torch.Tensor) else t.pooler_output
        self.text = torch.nn.functional.normalize(t, dim=-1).numpy()
        self.labels = [ko for ko, _ in TAGS]

    def probs(self, v):
        z = 100 * (self.text @ v)
        z = np.exp(z - z.max())
        return z / z.sum()

    def top(self, v, k=TOP_QUERY):
        p = self.probs(v)
        return [{"tag": self.labels[i], "score": round(float(p[i]), 3)} for i in np.argsort(-p)[:k]]

    def compare(self, query_vec, cand_vec, kept=None):
        """원본과 후보의 상위 태그 비교. kept: 사용자가 남긴 태그(있으면 원본 쪽 태그를 그 안으로 한정)."""
        pq, pc = self.probs(query_vec), self.probs(cand_vec)
        # 확률 MIN_PROB 이상인 태그만 그 사진에 "있다"고 본다 (확률 0.5% 같은 꼬리 태그로 설명하지 않기 위해)
        q_top = [self.labels[i] for i in np.argsort(-pq)[:TOP_COMPARE] if pq[i] >= MIN_PROB]
        c_top = [self.labels[i] for i in np.argsort(-pc)[:TOP_COMPARE] if pc[i] >= MIN_PROB]
        if kept is not None:
            q_top = [t for t in q_top if t in kept]
        idx = {t: i for i, t in enumerate(self.labels)}
        similar = sorted([t for t in q_top if t in c_top], key=lambda t: -min(pq[idx[t]], pc[idx[t]]))[:3]
        only_q = [t for t in q_top if t not in c_top][:2]
        only_c = [t for t in c_top if t not in q_top and (kept is None or t not in kept)][:2]
        different = [f"원본에는 {t}" for t in only_q] + [f"후보에는 {t}" for t in only_c]
        return similar, different
