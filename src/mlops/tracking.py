"""Small MLflow adapter shared by standalone experiment scripts."""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def _param_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def log_runs(experiment: str, runs: list[dict[str, Any]], result: dict[str, Any]) -> None:
    """Log completed results. Tracking failures never discard the local result file."""
    load_dotenv(ROOT / ".env", override=False)
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        print("[MLflow] MLFLOW_TRACKING_URI가 없어 기록을 건너뜁니다.")
        return

    try:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment)
        commit = _git_commit()
        for run in runs:
            with mlflow.start_run(run_name=run["name"]):
                params = {key: _param_value(value) for key, value in run.get("params", {}).items()}
                metrics = {
                    key: float(value)
                    for key, value in run.get("metrics", {}).items()
                    if isinstance(value, (int, float)) and math.isfinite(float(value))
                }
                if params:
                    mlflow.log_params(params)
                if metrics:
                    mlflow.log_metrics(metrics)
                if commit:
                    mlflow.set_tag("git_commit", commit)
                mlflow.set_tag("project", "abroad-to-korea")
                mlflow.log_dict(result, "result.json")
        print(f"[MLflow] {experiment}: {len(runs)}개 run 기록 완료")
    except Exception as exc:  # The result is already durable locally; tracking can be retried later.
        print(f"[MLflow] 기록 실패, 로컬 결과는 유지됩니다: {exc}")
