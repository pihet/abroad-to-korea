"""Copy newly discovered, reusable TourAPI images into MinIO."""

import hashlib
import io
import os
import urllib.request

import psycopg
from minio import Minio
from PIL import Image

ALLOWED_LICENSES = ("Type1", "Type3")
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def db_url() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


def download(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "abroad-to-korea/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        data = response.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("20MB를 넘는 이미지")
    if not content_type.startswith("image/"):
        raise ValueError(f"이미지가 아닌 응답: {content_type}")
    Image.open(io.BytesIO(data)).verify()
    return data, content_type


def main() -> None:
    limit = int(os.getenv("IMAGE_CACHE_DAILY_LIMIT", "1000"))
    client = Minio(os.environ["MINIO_ENDPOINT"], access_key=os.environ["MINIO_ACCESS_KEY"],
                   secret_key=os.environ["MINIO_SECRET_KEY"], secure=os.getenv("MINIO_SECURE", "false").lower() == "true")
    bucket = os.getenv("MINIO_BUCKET", "abroad-to-korea")
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    copied = failed = 0
    with psycopg.connect(db_url()) as conn:
        rows = conn.execute(
            "SELECT id, place_id, source_url FROM place_images "
            "WHERE object_key IS NULL AND is_active=true AND fetch_failures < 3 AND license_code = ANY(%s) "
            "ORDER BY fetch_failures,created_at LIMIT %s",
            (list(ALLOWED_LICENSES), limit),
        ).fetchall()
        for image_id, place_id, source_url in rows:
            try:
                data, content_type = download(source_url)
                digest = hashlib.sha256(data).digest()
                object_key = f"place-images/{place_id}/{image_id}"
                client.put_object(bucket, object_key, io.BytesIO(data), len(data), content_type=content_type)
                conn.execute("UPDATE place_images SET object_key=%s,sha256=%s,fetch_failures=0,last_fetch_error=NULL,last_fetch_at=now(),updated_at=now() WHERE id=%s",
                             (object_key, digest, image_id))
                copied += 1
            except Exception as exc:
                failed += 1
                conn.execute("UPDATE place_images SET fetch_failures=fetch_failures+1,last_fetch_error=%s,last_fetch_at=now(),updated_at=now() WHERE id=%s",
                             (str(exc)[:1000], image_id))
                print(f"사진 저장 실패 {image_id}: {exc}", flush=True)
        conn.commit()
    print(f"사진 MinIO 저장 {copied}건, 실패 {failed}건", flush=True)


if __name__ == "__main__":
    main()
