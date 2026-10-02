"""홀드아웃 보강 장면 사진을 별도로 내려받고 CLIP 임베딩을 만든다.

이 스크립트는 추천이나 정답 순위 평가를 하지 않는다. 홀드아웃이 30곳 이상
모이고 평가 설정이 동결될 때까지, 결과를 보지 않고 입력 특징만 준비하기 위한
도구다.

실행:
    .venv/bin/python src/prototype/holdout_scene_embeddings.py validate
    .venv/bin/python src/prototype/holdout_scene_embeddings.py download validate embed
"""

import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

import numpy as np

import clip_proto as cp

METADATA_CSV = cp.ROOT / "data/external/overseas_scenes_holdout_additions_20261002.csv"
IMAGE_DIR = cp.WORK / "scenes_holdout"
EMBEDDINGS_NPZ = cp.WORK / "emb_scenes_holdout.npz"
REQUIRED_COLUMNS = {
    "scene_id",
    "place_id",
    "photo_rank",
    "qa_status",
    "thumb_url_800",
}


def load_rows() -> list[dict[str, str]]:
    """검수 완료된 메타데이터를 읽고 행·파일 키의 유일성을 확인한다."""
    if not METADATA_CSV.exists():
        raise FileNotFoundError(f"메타데이터 CSV가 없습니다: {METADATA_CSV}")

    with METADATA_CSV.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"필수 컬럼이 없습니다: {', '.join(sorted(missing))}")
        rows = [row for row in reader if row["qa_status"].strip().lower() == "ok"]

    if not rows:
        raise ValueError("qa_status=ok인 홀드아웃 사진이 없습니다")

    keys = [(row["scene_id"], row["photo_rank"]) for row in rows]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise ValueError(f"중복된 (scene_id, photo_rank)가 있습니다: {duplicates}")

    for row in rows:
        if not row["scene_id"] or not row["place_id"] or not row["thumb_url_800"]:
            raise ValueError(f"필수 값이 빈 행입니다: {row}")
        try:
            rank = int(row["photo_rank"])
        except ValueError as exc:
            raise ValueError(f"photo_rank가 정수가 아닙니다: {row['photo_rank']}") from exc
        if rank < 1:
            raise ValueError(f"photo_rank는 1 이상이어야 합니다: {rank}")
        row["file"] = f"{row['scene_id']}_{rank}.jpg"

    filenames = [row["file"] for row in rows]
    if len(filenames) != len(set(filenames)):
        raise ValueError("메타데이터에서 생성된 파일명이 중복됩니다")
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def step_download() -> None:
    """CSV URL에서 누락된 파일만 홀드아웃 전용 폴더로 받는다."""
    rows = load_rows()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for row in rows:
        path = IMAGE_DIR / row["file"]
        if path.exists():
            continue
        if not cp.download(row["thumb_url_800"], path):
            raise RuntimeError(f"사진 다운로드 실패: {row['file']}")
        downloaded += 1
    print(f"[download] 신규 {downloaded}장, 전체 {len(rows)}장")


def validate_inputs() -> tuple[list[dict[str, str]], list[Path]]:
    """메타데이터와 로컬 JPEG가 정확히 1:1로 대응하고 디코딩되는지 확인한다."""
    from PIL import Image

    rows = load_rows()
    paths = [IMAGE_DIR / row["file"] for row in rows]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"홀드아웃 사진 {len(missing)}장이 없습니다: {missing}")

    expected = {path.name for path in paths}
    actual = {path.name for path in IMAGE_DIR.glob("*.jpg")}
    extras = sorted(actual - expected)
    if extras:
        raise ValueError(f"CSV에 없는 JPEG가 홀드아웃 폴더에 있습니다: {extras}")

    dimensions = []
    for path in paths:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.format != "JPEG":
                    raise ValueError(f"JPEG가 아닙니다: {path.name} ({image.format})")
                dimensions.append((image.width, image.height))
        except Exception as exc:
            raise ValueError(f"이미지 검증 실패: {path.name}: {exc}") from exc

    n_scenes = len({row["scene_id"] for row in rows})
    print(
        f"[validate] {len(paths)}장 / {n_scenes}개 장면, JPEG 디코딩 성공, "
        f"크기 {min(dimensions)}~{max(dimensions)}"
    )
    return rows, paths


def step_embed() -> None:
    """검증된 홀드아웃 사진만 CLIP으로 임베딩해 별도 NPZ에 저장한다."""
    import torch
    from transformers import CLIPModel, CLIPProcessor

    rows, paths = validate_inputs()
    torch.set_num_threads(12)
    model = CLIPModel.from_pretrained(cp.MODEL_NAME).eval()
    processor = CLIPProcessor.from_pretrained(cp.MODEL_NAME)
    vecs, kept = cp.embed_files(paths, model, processor)

    if kept != paths or len(vecs) != len(rows):
        kept_names = {path.name for path in kept}
        failed = [path.name for path in paths if path.name not in kept_names]
        raise RuntimeError(f"임베딩에서 누락된 사진이 있습니다: {failed}")

    EMBEDDINGS_NPZ.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        EMBEDDINGS_NPZ,
        vecs=vecs,
        names=np.array([path.name for path in paths]),
        scene_ids=np.array([row["scene_id"] for row in rows]),
        place_ids=np.array([row["place_id"] for row in rows]),
        photo_ranks=np.array([int(row["photo_rank"]) for row in rows], dtype=np.int16),
        model_name=np.array(cp.MODEL_NAME),
        source_csv_sha256=np.array(sha256(METADATA_CSV)),
        image_sha256=np.array([sha256(path) for path in paths]),
    )
    print(f"[embed] {len(vecs)}장 × {vecs.shape[1]}차원 → {EMBEDDINGS_NPZ}")


STEPS = {"download": step_download, "validate": validate_inputs, "embed": step_embed}


def main(args: list[str]) -> None:
    names = args or ["validate"]
    unknown = [name for name in names if name not in STEPS]
    if unknown:
        raise SystemExit(f"알 수 없는 단계: {unknown}. 선택: {list(STEPS)}")
    for name in names:
        STEPS[name]()


if __name__ == "__main__":
    main(sys.argv[1:])
