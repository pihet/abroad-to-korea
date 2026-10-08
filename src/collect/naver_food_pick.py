"""2차 네이버 이미지 검색 결과(data/raw/naver_image2)에서 음식점마다 쓸 사진 한 장을 고른다.

1차(naver_image)는 출처를 네이버 플레이스·메뉴판닷컴·관광공사로 좁혀 규칙만으로 고르지만(app/activities.py naver_pick),
2차는 블로그·식신 같은 출처까지 넓히는 대신 CLIP으로 사진을 확인한다.
    - 제목에 가게 이름이 있고 출처가 HOSTS 인 결과만, 위에서부터
    - 썸네일을 메모리로만 받아 "음식·식당 안·간판·메뉴판" 문장 확률 합이 MIN_FOOD 이상이면 채택
      (사람·행사·상품·지도 사진은 떨어진다). 사진 파일은 저장하지 않는다
    - 2026-10-08 무작위 60곳 시험: 10곳 채택, 10장 모두 음식·메뉴판, 인물 없음

실행: python src/collect/naver_food_pick.py
결과: data/interim/app/naver_picks.json  {contentid: 썸네일 주소}
"""

import io
import json
import re
import sys
import urllib.parse
import urllib.request

from tour_attractions import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
from app.activities import _norm  # noqa: E402

IN_DIR = PROJECT_ROOT / "data/raw/naver_image2"
FOOD_LIST = PROJECT_ROOT / "data/raw/tourapi/areaBasedList2_ct39_20261006"
OUT = PROJECT_ROOT / "data/interim/app/naver_picks.json"
HOSTS = ("ldb-phinf.pstatic.net", "menupan.com", "visitkorea.or.kr", "siksinhot.com",  # triple.guide 는 여행자 인물 사진이 섞여 뺌
         "blogthumb.pstatic.net", "postfiles.pstatic.net", "blogfiles.naver.net", "mblogthumb-phinf.pstatic.net",
         "dthumb-phinf.pstatic.net")
GOOD = ["a photo of korean food dishes on a table", "a photo of a restaurant interior",
        "a photo of a restaurant storefront sign", "a photo of a restaurant menu board"]
BAD = ["a photo of people posing", "a photo of a person's face", "a news photo of officials at an event",
       "a photo of a product for sale", "a map", "a photo of scenery or a landscape", "a photo of a person"]
# 풍경 문장이 없으면 풍경 속 작은 인물 사진이 '식당 간판' 쪽으로 분류돼 통과했다 (2026-10-08 표본)
MIN_FOOD = 0.6
# 사람이 나온 사진은 따로 한 번 더 거른다 (음식 문장 확률만으로는 풍경 속 인물 사진이 통과함, 2026-10-08 표본 24장 중 1장)
PERSON = ["a photo with a person in it", "a photo of food or a place with no people"]
MAX_PERSON = 0.2  # 표본: 인물 사진 0.34, 음식 사진 0.00~0.08
UA = "Mozilla/5.0"


def main() -> None:
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    def embed_text(texts):
        with torch.no_grad():
            t = model.get_text_features(**proc(text=texts, return_tensors="pt", padding=True))
            return torch.nn.functional.normalize(t if isinstance(t, torch.Tensor) else t.pooler_output, dim=-1)
    text, person = embed_text(GOOD + BAD), embed_text(PERSON)

    def food_score(url: str) -> float:
        """음식·식당 문장 확률 합. 사람이 나온 사진이면 0."""
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15).read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        with torch.no_grad():
            v = model.get_image_features(**proc(images=img, return_tensors="pt"))
            v = torch.nn.functional.normalize(v if isinstance(v, torch.Tensor) else v.pooler_output, dim=-1)
            if float((100 * v @ person.T).softmax(-1)[0, 0]) > MAX_PERSON:
                return 0.0
            return float((100 * v @ text.T).softmax(-1)[0, :len(GOOD)].sum())

    titles = {}
    for p in sorted(FOOD_LIST.glob("page_*.json")):
        for it in json.loads(p.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]:
            titles[it["contentid"]] = it["title"]
    picks = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() and "--resume" in sys.argv else {}
    files = sorted(IN_DIR.glob("*.json"))
    print(f"2차 검색 원문 {len(files)}곳, 이미 고른 곳 {len(picks)}곳")
    for k, f in enumerate(files, 1):
        cid = f.stem
        if cid in picks or cid not in titles:
            continue
        name = _norm(re.sub(r"\(.*?\)", "", titles[cid]))
        for it in json.loads(f.read_text(encoding="utf-8")).get("items", []):
            host = urllib.parse.urlparse(it.get("link", "")).hostname or ""
            if not (name and name in _norm(it.get("title", "")) and host.endswith(HOSTS)):
                continue
            try:
                if food_score(it["thumbnail"]) >= MIN_FOOD:
                    picks[cid] = it["thumbnail"]
                    break
            except Exception:
                continue
        if k % 200 == 0:
            OUT.write_text(json.dumps(picks, ensure_ascii=False), encoding="utf-8")
            print(f"  {k}곳 확인, 채택 {len(picks)}곳")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(picks, ensure_ascii=False), encoding="utf-8")
    print(f"채택 {len(picks)}곳 → {OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
