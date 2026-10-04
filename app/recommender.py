"""추천 엔진: Stage A(시각 후보) + Stage B(조건 재정렬).

Stage A  질의 사진 → CLIP ViT-B/32 → 국내 관광지 대표사진과 코사인 → 관광지별 최고 1장
         → 상위 100개 관광지 유사도를 시군구별 합산(vote100) → 시군구 상위 30곳
Stage B  30곳 안에서만 재정렬. visual 은 Stage A 순서 그대로, 그 밖은 0.5·시각 + 0.5·조건 백분위
         (시각 가중치는 0.5 아래로 내리지 않는다)

기존 평가 코드(src/prototype)의 인덱스·사진 목록을 읽기만 한다.
"""

import io
import uuid
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageOps

from .context import Context, ORIGINS, cp  # noqa: F401  (cp: clip_proto)
from .tags import Tagger

import scene_catalog as sc  # noqa: E402  (context 가 sys.path 를 맞춘다)

VOTE_K = 100
N_CAND = 30
VISUAL_WEIGHT = 0.5
PRIORITIES = ("visual", "crowd", "near", "season")
KOGL = {"Type1": "공공누리 제1유형 (출처표시)", "Type3": "공공누리 제3유형 (출처표시·변경금지)"}
CACHE_SIZE = 200


class Engine:
    def __init__(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        torch.set_num_threads(8)
        self.model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
        self.proc = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
        self.I = sc.domestic_index()
        self.cid = np.array([str(c) for c in self.I["cid"]])
        self.ok = self.I["img_region"] >= 0
        self.region_keys = [f"{r[0]}_{r[1]}" for r in self.I["regions"]]
        self.ctx = Context([(r[0], r[1]) for r in self.I["regions"]])
        self.tagger = Tagger(self.model, self.proc)
        self.cache = OrderedDict()
        self._demo = None

    # ---------------- 입력
    def embed(self, img):
        import torch
        with torch.no_grad():
            f = self.model.get_image_features(**self.proc(images=[img.convert("RGB")], return_tensors="pt"))
            f = f if isinstance(f, torch.Tensor) else f.pooler_output
        return torch.nn.functional.normalize(f, dim=-1).numpy()[0]

    @staticmethod
    def open_image(data, crop=None):
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))  # 휴대폰 사진 회전 반영
        img = img.convert("RGB")
        w, h = img.size
        cropped = False
        if crop:
            x, y, cw, ch = (int(round(crop[k])) for k in ("x", "y", "w", "h"))
            x, y = max(0, x), max(0, y)
            cw, ch = min(cw, w - x), min(ch, h - y)
            if cw >= 16 and ch >= 16:  # 너무 작은 영역은 무시하고 전체를 쓴다
                img, cropped = img.crop((x, y, x + cw, y + ch)), True
        return img, {"width": w, "height": h, "cropped": cropped}

    def analyze(self, img):
        v = self.embed(img)
        qid = uuid.uuid4().hex[:12]
        self.cache[qid] = {"vec": v, "tags": self.tagger.top(v), "stage_a": self.stage_a(v)}
        while len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)
        return qid, self.cache[qid]["tags"]

    # ---------------- Stage A
    def stage_a(self, v, allowed=None):
        """allowed: 조건 필터를 통과한 시군구 인덱스 집합 (None 이면 전체). 필터는 후보를 고르기 전에 건다."""
        sims = self.I["kv"] @ v
        ok = self.ok if allowed is None else self.ok & np.isin(self.I["img_region"], list(allowed))
        idx = np.where(ok)[0]
        if not len(idx):
            return []
        # 관광지 단위 통합: 유사도 내림차순으로 놓고 관광지마다 처음 나온 사진(= 최고 1장)만 남긴다
        o = idx[np.argsort(-sims[idx], kind="stable")]
        _, first = np.unique(self.cid[o], return_index=True)
        best_img = o[first]                       # 관광지당 대표 사진 1장
        best = sims[best_img]
        reg = self.I["img_region"][best_img]
        top = np.argsort(-best, kind="stable")[:VOTE_K]
        vote = np.bincount(reg[top], weights=best[top], minlength=len(self.I["regions"]))
        vote = vote + 1e-3 * (self.I["reg_mean"] @ v)  # 표 없는 시군구 순서 (기존 vote100 과 같은 처리)
        if allowed is not None:
            vote[[i for i in range(len(vote)) if i not in allowed]] = -np.inf
        n = N_CAND if allowed is None else min(N_CAND, len(allowed))
        out = []
        for ri in np.argsort(-vote, kind="stable")[:n]:
            in_reg = np.where(reg == ri)[0]
            if not len(in_reg):  # 필터 안의 시군구 중 사진이 덜 닮아 상위 관광지가 없는 곳
                continue
            a = in_reg[np.argmax(best[in_reg])]  # 이 시군구에서 가장 닮은 관광지
            out.append({"ri": int(ri), "visual_rank": len(out) + 1, "vote": float(vote[ri]),
                        "img_index": int(best_img[a]), "similarity": float(best[a])})
        return out

    # ---------------- Stage B
    def stage_b(self, cands, month, priority, origin):
        n = len(cands)
        keys = [tuple(self.region_keys[c["ri"]].split("_", 1)) for c in cands]
        if priority == "crowd":
            vals = [None if (cg := self.ctx.congestion(k, month)) is None else -cg["index"] for k in keys]
        elif priority == "near":
            vals = [None if (d := self.ctx.distance(k, origin or "서울")) is None else -d for k in keys]
        elif priority == "season":
            vals = [None if (cl := self.ctx.climate(k, month)) is None else cl["comfort"] for k in keys]
        else:
            vals = [None] * n
        ok = [x for x in vals if x is not None]

        def pct(x):  # 후보 30곳 안 백분위 (높을수록 좋음), 결측은 0.5
            if x is None or len(ok) < 2:
                return 0.5
            return (sum(y < x for y in ok) + 0.5 * (sum(y == x for y in ok) - 1)) / (len(ok) - 1)
        scored = []
        for c, x in zip(cands, vals):
            vis = 1 - (c["visual_rank"] - 1) / max(n - 1, 1)
            if priority == "visual":
                score, cond = vis, None
            else:
                cond = pct(x)
                score = VISUAL_WEIGHT * vis + (1 - VISUAL_WEIGHT) * cond
            scored.append((score, -c["visual_rank"], c, vis, cond, x))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [{**c, "visual_component": round(vis, 3), "condition_component": None if cond is None else round(cond, 3),
                 "condition_value": x} for _, _, c, vis, cond, x in scored]

    # ---------------- 응답 조립
    def recommend(self, qid, month, priority, origin, kept_tags, limit, offset, allowed=None):
        q = self.cache[qid]
        cands = q["stage_a"] if allowed is None else self.stage_a(q["vec"], allowed)
        if not cands:
            return {"total": 0, "candidates": []}
        ranked = self.stage_b(cands, month, priority, origin)
        out = []
        for rank, c in enumerate(ranked[offset:offset + limit], offset + 1):
            sido, sgg = self.region_keys[c["ri"]].split("_", 1)
            key = (sido, sgg)
            it = self.I["items"][self.cid[c["img_index"]]]
            similar, different = self.tagger.compare(q["vec"], self.I["kv"][c["img_index"]], kept_tags)
            lat, lon = _float(it.get("mapy")), _float(it.get("mapx"))
            out.append({
                "rank": rank, "visual_rank": c["visual_rank"],
                "sigungu": {"key": f"{sido}_{sgg}", "name": sgg, "sido": self.I["name"][self.I["regions"][c["ri"]]].rsplit(" ", 1)[0]},
                "attraction": {"id": it["contentid"], "name": it["title"], "address": it.get("addr1") or None,
                               "latitude": lat, "longitude": lon, "image_url": f"/images/kr/{it['contentid']}",
                               "license": KOGL.get(it["cpyrhtDivCd"], it["cpyrhtDivCd"]),
                               "source": "한국관광공사 TourAPI"},
                "visual": {"similarity": round(c["similarity"], 4), "vote": round(c["vote"], 3)},
                "similar_tags": similar, "different_tags": different,
                "congestion": self.ctx.congestion(key, month),
                "climate": self.ctx.climate(key, month),
                "distance_km": self.ctx.distance(key, origin) if origin else None,
                "map_links": _map_links(it["title"], lat, lon),
                "rerank": {"visual_component": c["visual_component"], "condition_component": c["condition_component"],
                           "condition_value": c["condition_value"]},
            })
        return {"total": len(ranked), "candidates": out}

    # ---------------- 시군구 대표 사진 (그 시군구 사진 평균에 가장 가까운 관광지 = 가장 그 지역다운 사진)
    def region_photo(self, ri):
        if not hasattr(self, "_rep"):
            self._rep = {}
            sims = self.I["kv"] @ self.I["reg_mean"].T
            for i in range(len(self.I["regions"])):
                ix = np.where((self.I["img_region"] == i) & self.ok)[0]
                if len(ix):
                    self._rep[i] = int(ix[np.argmax(sims[ix, i])])
        k = self._rep.get(ri)
        if k is None:
            return None
        it = self.I["items"][self.cid[k]]
        return {"attraction_id": it["contentid"], "name": it["title"], "image_url": f"/images/kr/{it['contentid']}",
                "license": KOGL.get(it["cpyrhtDivCd"], it["cpyrhtDivCd"])}

    # ---------------- 데모 사진 (카탈로그 장면당 첫 사진)
    def demo_photos(self):
        if self._demo is None:
            import pandas as pd
            rows = sc.ok_rows()
            places = pd.read_csv(sc.PLACES_CSV).set_index("place_id")
            first = rows.sort_values("photo_rank").drop_duplicates("scene_id")
            self._demo = [{"photo_id": r.file, "place_name": places.loc[r.place_id, "name_ko"], "scene_label": r.scene_label_ko,
                           "image_url": f"/images/overseas/{r.file}", "artist": str(r.artist), "license": str(r.license),
                           "license_url": str(r.license_url), "source_page": str(r.commons_page)}
                          for r in first.itertuples()]
        return self._demo


def _float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _map_links(name, lat, lon):
    from urllib.parse import quote
    if lat is None or lon is None:
        return {"kakao": None, "naver": None}
    return {"kakao": f"https://map.kakao.com/link/map/{quote(name)},{lat},{lon}",
            "naver": f"https://map.naver.com/v5/search/{quote(name)}"}
