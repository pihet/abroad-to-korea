"""Delete expired user uploads from MinIO, then mark their rows deleted."""

import os
from datetime import datetime, timezone

import psycopg
from minio import Minio


def database_url() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    client = Minio(os.environ["MINIO_ENDPOINT"], access_key=os.environ["MINIO_ACCESS_KEY"],
                   secret_key=os.environ["MINIO_SECRET_KEY"], secure=os.getenv("MINIO_SECURE", "false").lower() == "true")
    bucket, now = os.getenv("MINIO_BUCKET", "abroad-to-korea"), datetime.now(timezone.utc)
    with psycopg.connect(database_url()) as conn:
        rows = conn.execute(
            "SELECT id, object_key FROM media_assets WHERE deleted_at IS NULL AND delete_after IS NOT NULL AND delete_after <= %s FOR UPDATE SKIP LOCKED",
            (now,),
        ).fetchall()
        for asset_id, object_key in rows:
            try:
                client.remove_object(bucket, object_key)
            except Exception as exc:
                print(f"삭제 실패 {asset_id}: {exc}", flush=True)
                continue
            conn.execute("UPDATE media_assets SET deleted_at = %s WHERE id = %s", (now, asset_id))
        conn.commit()
    print(f"만료 사진 {len(rows)}건 확인", flush=True)


if __name__ == "__main__":
    main()
