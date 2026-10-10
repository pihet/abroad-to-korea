from datetime import timedelta

import pendulum

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator


KST = "Asia/Seoul"  # 스케줄은 한국 시각 (2026-10-11 UTC 에서 바꿈, 실행 시각은 그대로)


with DAG(
    "user_media_cleanup_hourly",
    start_date=pendulum.datetime(2026, 10, 8, tz=KST),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "platform", "retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["privacy", "media"],
) as dag:
    BashOperator(task_id="delete_expired_media", bash_command="cd $PROJECT_ROOT && python src/ops/cleanup_media.py")


with DAG(
    "regional_metrics_monthly",
    start_date=pendulum.datetime(2026, 11, 1, tz=KST),
    schedule="0 12 2 * *",  # 매월 2일 12:00 KST
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "data", "retries": 3, "retry_delay": timedelta(minutes=30)},
    tags=["metrics", "monthly"],
) as monthly_dag:
    visitors = BashOperator(task_id="collect_visitors", bash_command="cd $PROJECT_ROOT && python src/collect/datalab_visitors.py")
    population = BashOperator(task_id="collect_population", bash_command="cd $PROJECT_ROOT && python src/collect/population.py")
