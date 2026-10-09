"""CLIP 질의용 해외 사진 정리: 수동 검토로 뺀 사진을 같은 검색어의 다음 결과로 채워 'curated' 세트를 만든다.

기준 (정답과 무관): 그 여행지를 여행자 시점에서 보여주는 실외 실사 사진만 남긴다.
    제외 = 그림·소묘 / 위성·항공사진 / 사물·동물·인물 클로즈업 / 실내·행사 / 중복
    국내 정답 지역과 닮았는지는 보지 않는다 (보면 평가가 부풀려진다).

실행:
    .venv/bin/python src/model/curate_overseas.py fill     # 빈자리 채우기 (data/interim/clip/overseas_curated/)
    .venv/bin/python src/model/curate_overseas.py sheets   # 새로 채운 사진 확인용 모음 이미지
그다음 CLIP_OV_SET=curated 로 clip_proto.py embed evaluate 를 실행한다.
"""

import json
import shutil
import sys
import time

import numpy as np

import clip_proto as cp

SRC = cp.WORK / "overseas"
DST = cp.WORK / "overseas_curated"

# 2026-10-02 수동 검토 결과 (원본 세트의 파일 번호)
REMOVE = {
    "kyoto": {2: "사물 클로즈업(물받이)", 3: "식별 어려운 가지 클로즈업", 4: "사물 클로즈업(물받이)",
              6: "사물 클로즈업(울타리)", 7: "불상 클로즈업"},
    "naples": {0: "그림", 1: "그림", 2: "소묘", 3: "그림", 5: "그림", 6: "그림", 7: "그림(전시 사진)"},
    "uyuni": {1: "자동차 중심", 6: "인물 사진", 7: "자동차 중심(1번과 거의 같음)"},
    "kotakinabalu": {2: "항공사진", 3: "항공사진(2번과 중복)", 5: "시장 가판대 클로즈업", 7: "모래 클로즈업"},
    "honolulu": {1: "그림", 3: "2번과 중복", 5: "그림"},
    "niagara": {4: "벤치 그림자(장소와 무관)"},
    "interlaken": {4: "그림"},
    "zhangjiajie": {5: "동상 중심"},
    "serengeti": {3: "사자 클로즈업"},
    "maldives": {7: "항공사진"},
    "galapagos": {0: "위성사진"},
    "etretat": {6: "인물과 갈매기 중심", 7: "항공사진"},
    "machupicchu": {5: "0번과 중복"},
    "montmartre": {0: "그림", 1: "그림(0번과 중복)", 2: "그림(0번과 중복)", 5: "그림", 6: "소묘", 7: "3번과 중복"},
    "brooklyn": {0: "자동차 경주", 3: "실내(유리공방)", 7: "조각 클로즈업"},
}
DUP_SIM = 0.95

# 1차로 채운 사진 중 수동 검토에서 다시 뺀 것 (같은 기준)
REJECT_NEW = {
    "naples": {"new0": "그림", "new1": "그림", "new2": "그림(액자)", "new3": "도판", "new4": "그림", "new5": "판화"},
    "uyuni": {"new0": "그림자 클로즈업"},
    "kotakinabalu": {"new0": "모래 클로즈업", "new1": "모래 클로즈업", "new2": "모래 클로즈업", "new3": "모래 클로즈업"},
    "honolulu": {"new0": "항공사진"},
    "montmartre": {"new0": "인물(악사)", "new1": "인물(악사)", "new3": "옛 흑백 사진", "new5": "그림"},
    "brooklyn": {"new0": "갈매기 클로즈업", "new1": "자동차 경주장", "new2": "자동차 경주장"},
}
# 2차 보충용 일반 검색어 (정답 지역과 무관한 일반 표현만 쓴다)
ALT_QUERIES = {
    "naples": ["Naples Italy panorama", "Naples waterfront"],
    "uyuni": ["Salar de Uyuni landscape"],
    "kotakinabalu": ["Kota Kinabalu waterfront", "Kota Kinabalu city"],
    "honolulu": ["Waikiki beach"],
    "montmartre": ["Montmartre Paris streets", "Montmartre hill Paris"],
    "brooklyn": ["Brooklyn New York streets", "Brooklyn neighborhood"],
}
OUTDOOR_MIN = 0.6
LABELS = ["an outdoor landscape or street photograph", "a painting or drawing", "a map or satellite image",
          "an indoor photograph", "a close-up photo of an animal", "a close-up photo of an object or texture",
          "a photo of cars or a race", "a portrait photo of people", "an aerial photograph"]


def fill():
    import re
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    DST.mkdir(parents=True, exist_ok=True)
    meta = json.loads((SRC / "attribution.json").read_text())
    model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
    proc = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
    emb = np.load(cp.WORK / "emb_overseas.npz")
    vec = {str(n): v for n, v in zip(emb["names"], emb["vecs"])}

    def embed(path):
        with torch.no_grad():
            f = model.get_image_features(**proc(images=[Image.open(path).convert("RGB")], return_tensors="pt"))
            f = f if isinstance(f, torch.Tensor) else f.pooler_output
        return torch.nn.functional.normalize(f, dim=-1).numpy()[0]

    out, log = [], []
    bad_name = re.compile(r"map|logo|flag|diagram|plan|chart|stamp|coat|seal|painting|drawing|MODIS|satellite", re.I)
    for oid, query in cp.OVERSEAS_QUERIES.items():
        rows = [m for m in meta if m["overseas_id"] == oid]
        removed = REMOVE.get(oid, {})
        kept = [m for m in rows if int(m["file"].rsplit("_", 1)[1][:-4]) not in removed]
        kept_vecs = [vec[m["file"][:-4]] for m in kept]
        used_titles = {m["title"] for m in rows}
        for m in kept:
            shutil.copy(SRC / m["file"], DST / m["file"])
            out.append({**m, "curation": "원본 유지"})
        need, n_new = cp.OV_PER_PLACE - len(kept), 0
        if need > 0:
            for p in cp.commons_search(query, limit=80):
                if n_new >= need:
                    break
                if "imageinfo" not in p:  # 이미지 정보가 없는 결과는 건너뛴다
                    continue
                ii = p["imageinfo"][0]
                em = ii.get("extmetadata", {})
                lic = em.get("LicenseShortName", {}).get("value", "")
                if (p["title"] in used_titles or ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 800
                        or bad_name.search(p["title"]) or not (lic.startswith("CC") or "Public domain" in lic)):
                    continue
                path = DST / f"{oid}_new{n_new}.jpg"
                if not cp.download(ii["thumburl"], path):
                    continue
                v = embed(path)
                if kept_vecs and max(float(v @ k) for k in kept_vecs) > DUP_SIM:  # 거의 같은 사진
                    path.unlink()
                    continue
                kept_vecs.append(v)
                artist = re.sub("<[^>]+>", "", em.get("Artist", {}).get("value", ""))[:80]
                out.append({"overseas_id": oid, "file": path.name, "title": p["title"], "license": lic,
                            "artist": artist, "page": ii.get("descriptionurl", ""), "curation": "새로 채움"})
                n_new += 1
                time.sleep(0.3)
        log.append(f"{oid}: 유지 {len(kept)} / 제외 {len(removed)} / 채움 {n_new}")
    (DST / "attribution.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    (DST / "removed.json").write_text(json.dumps(REMOVE, ensure_ascii=False, indent=1))
    print("\n".join(log))


def fill2():
    """2차: REJECT_NEW 를 지우고 ALT_QUERIES 로 다시 채운다. 실외 사진 확률(제로샷) OUTDOOR_MIN 이상만 받는다."""
    import re
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
    proc = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
    with torch.no_grad():
        t = model.get_text_features(**proc(text=LABELS, return_tensors="pt", padding=True))
        t = t if isinstance(t, torch.Tensor) else t.pooler_output
    t = torch.nn.functional.normalize(t, dim=-1).numpy()

    def embed(path):
        with torch.no_grad():
            f = model.get_image_features(**proc(images=[Image.open(path).convert("RGB")], return_tensors="pt"))
            f = f if isinstance(f, torch.Tensor) else f.pooler_output
        return torch.nn.functional.normalize(f, dim=-1).numpy()[0]

    meta = json.loads((DST / "attribution.json").read_text())
    for oid, rej in REJECT_NEW.items():
        for tag in rej:
            (DST / f"{oid}_{tag}.jpg").unlink(missing_ok=True)
    meta = [m for m in meta if m["file"][:-4].rsplit("_", 1)[-1] not in REJECT_NEW.get(m["overseas_id"], {})]
    used = {m["title"] for m in json.loads((SRC / "attribution.json").read_text())} | {m["title"] for m in meta}
    bad_name = re.compile(r"map|logo|flag|diagram|plan|chart|stamp|coat|seal|painting|drawing|MODIS|satellite|engraving|lithograph", re.I)
    log = []
    for oid, queries in ALT_QUERIES.items():
        have = [m for m in meta if m["overseas_id"] == oid]
        kept_vecs = [embed(DST / m["file"]) for m in have]
        need, n_new = cp.OV_PER_PLACE - len(have), 0
        for q in queries:
            for p in cp.commons_search(q, limit=80):
                if n_new >= need:
                    break
                if "imageinfo" not in p:
                    continue
                ii = p["imageinfo"][0]
                em = ii.get("extmetadata", {})
                lic = em.get("LicenseShortName", {}).get("value", "")
                if (p["title"] in used or ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 800
                        or bad_name.search(p["title"]) or not (lic.startswith("CC") or "Public domain" in lic)):
                    continue
                path = DST / f"{oid}_alt{n_new}.jpg"
                if not cp.download(ii["thumburl"], path):
                    continue
                v = embed(path)
                pr = np.exp(100 * (t @ v)); pr /= pr.sum()
                dup = kept_vecs and max(float(v @ k) for k in kept_vecs) > DUP_SIM
                if pr[0] < OUTDOOR_MIN or dup:
                    path.unlink()
                    continue
                used.add(p["title"])
                kept_vecs.append(v)
                artist = re.sub("<[^>]+>", "", em.get("Artist", {}).get("value", ""))[:80]
                meta.append({"overseas_id": oid, "file": path.name, "title": p["title"], "license": lic, "artist": artist,
                             "page": ii.get("descriptionurl", ""), "curation": f"2차 보충 ({q}, 실외확률 {pr[0]:.2f})"})
                n_new += 1
                time.sleep(0.3)
        log.append(f"{oid}: 보유 {len(have)} / 2차 보충 {n_new} / 부족 {need - n_new}")
    (DST / "attribution.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    (DST / "removed_round2.json").write_text(json.dumps(REJECT_NEW, ensure_ascii=False, indent=1))
    print("\n".join(log))


def sheets(out_dir):
    from PIL import Image, ImageDraw
    tag = sys.argv[3] if len(sys.argv) > 3 else "새로 채움"
    meta = [m for m in json.loads((DST / "attribution.json").read_text()) if m["curation"].startswith(tag)]
    per = 10
    for s in range(0, len(meta), per):
        chunk = meta[s:s + per]
        sheet = Image.new("RGB", (per * 160, 160), "white")
        d = ImageDraw.Draw(sheet)
        for c, m in enumerate(chunk):
            im = Image.open(DST / m["file"]).convert("RGB")
            im.thumbnail((156, 130))
            sheet.paste(im, (c * 160 + 2, 26))
            d.text((c * 160 + 4, 4), m["file"][:-4], fill="black")
        sheet.save(f"{out_dir}/{'alt' if tag.startswith('2차') else 'new'}_{s // per:02d}.jpg", quality=80)
    print(f"새로 채운 사진 {len(meta)}장")


if __name__ == "__main__":
    if sys.argv[1] == "fill":
        fill()
    elif sys.argv[1] == "fill2":
        fill2()
    else:
        sheets(sys.argv[2])
