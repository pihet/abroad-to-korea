"""Create the artifact bucket, then start the local MLflow tracking server."""

import os
import subprocess
import time

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def ensure_bucket() -> None:
    endpoint = os.environ["MLFLOW_S3_ENDPOINT_URL"]
    bucket = os.environ.get("MLFLOW_ARTIFACT_BUCKET", "mlflow-artifacts")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"),
    )
    for attempt in range(60):
        try:
            client.head_bucket(Bucket=bucket)
            return
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchBucket", "NotFound"}:
                client.create_bucket(Bucket=bucket)
                return
        except BotoCoreError:
            pass
        if attempt == 59:
            raise RuntimeError(f"MinIO bucket 준비 실패: {bucket}")
        time.sleep(2)


if __name__ == "__main__":
    ensure_bucket()
    subprocess.run(
        [
            "mlflow", "server",
            "--backend-store-uri", os.environ["MLFLOW_BACKEND_STORE_URI"],
            "--serve-artifacts",
            "--artifacts-destination", f"s3://{os.environ.get('MLFLOW_ARTIFACT_BUCKET', 'mlflow-artifacts')}",
            "--host", "0.0.0.0",
            "--port", "5000",
            "--workers", "1",
            "--allowed-hosts", "localhost:*,127.0.0.1:*,mlflow:*",
        ],
        check=True,
    )
